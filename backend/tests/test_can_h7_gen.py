"""STM32H7 FDCAN driver-config generator (backend/gen/can_h7.py).

Covers:
  - Bit-timing computation against the STM32CubeMX reference for
    500 kbit/s @ 80 MHz (the assumed FDCAN kernel clock).
  - The packed NBTP register value matches what the Can_Cfg.h
    CAN_H7_NBTP(...) macro produces, byte-for-byte.
  - End-to-end emit for examples/h7-loopback round-trips through the
    project loader and yields the same fields the PROMPT C1 table
    encoded by hand: one Rx filter (canid 0x100 → Hrh 0, std), one
    Tx slot (Hth 0 → buffer 0), MRAM sized to the message count.
"""

from __future__ import annotations

import re
from pathlib import Path

from engine import load_project
from gen import can_h7

REPO_ROOT = Path(__file__).resolve().parents[2]


# ----------------------------- bit timing --------------------------


def test_nbtp_matches_stm32cubemx_reference_500kbps_80mhz():
    """STM32CubeMX 6.x — FDCAN1 for STM32H753 at 80 MHz kernel clock,
    nominal 500 kbit/s, sample point 87.5 % — produces:
        Prescaler (NBRP)  = 10
        Seg1     (NTSEG1) = 13
        Seg2     (NTSEG2) = 2
        SJW      (NSJW)   = 1

    The PROMPT C1 hand-written Can_Cfg.c uses exactly these values
    (`CAN_H7_NBTP(9, 12, 1, 0)` — the M_CAN encoding subtracts one
    from each). This regression keeps any future BRP-search rewrite
    honest.
    """
    fields = can_h7._compute_nbtp_fields(
        kernel_clock_hz=80_000_000,
        baud_bps=500_000,
    )
    assert fields.brp == 10
    assert fields.tseg1 == 13
    assert fields.tseg2 == 2
    assert fields.sjw == 1
    assert fields.total_tq_per_bit == 16
    assert fields.sample_point_permille == 875


def test_packed_nbtp_register_value_matches_macro_layout():
    """The packed register value must exactly equal the bit pattern
    Can_Cfg.h's CAN_H7_NBTP(...) macro produces. We re-implement the
    macro here in Python and assert equality — if either drifts, the
    test catches it before the firmware does."""
    fields = can_h7._compute_nbtp_fields(80_000_000, 500_000)

    def macro_pack(nbrp_m1: int, ntseg1_m1: int, ntseg2_m1: int, nsjw_m1: int) -> int:
        return (
            (nsjw_m1 << 25)
            | (nbrp_m1 << 16)
            | (ntseg1_m1 << 8)
            | (ntseg2_m1 << 0)
        )

    expected = macro_pack(
        nbrp_m1=fields.brp - 1,
        ntseg1_m1=fields.tseg1 - 1,
        ntseg2_m1=fields.tseg2 - 1,
        nsjw_m1=fields.sjw - 1,
    )
    assert fields.register_value == expected
    # And the specific value the hand-written C1 commit encoded.
    assert fields.register_value == 0x00090C01


def test_nbtp_baud_must_divide_kernel_evenly():
    """Catch the easy mistake of asking for a baud the kernel can't
    hit exactly — the search must refuse rather than silently round."""
    import pytest

    with pytest.raises(ValueError, match="no NBTP fit"):
        # 80 MHz / 333 kbit/s = 240.24 — not integer for any BRP that
        # also leaves a sane TSEG1+TSEG2 sum.
        can_h7._compute_nbtp_fields(80_000_000, 333_000)


# ----------------------------- emit ---------------------------------


def test_h7_loopback_target_marker_present():
    """examples/h7-loopback opts into the H7 generator via project.json."""
    assert can_h7.is_h7_target(REPO_ROOT / "examples" / "h7-loopback")
    # Negative control — the host examples don't.
    assert not can_h7.is_h7_target(REPO_ROOT / "examples" / "com-minimal")


def test_h7_loopback_emit_is_equivalent_to_C1_handwritten_table(tmp_path: Path):
    """Loading examples/h7-loopback and running can_h7.generate should
    produce a Can_Cfg.c whose table contents match the values the
    PROMPT C1 hand-written file encoded (modulo MRAM sizing — see
    docstring at the bottom).
    """
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    written = can_h7.generate(project, tmp_path)
    names = {p.name for p in written}
    assert names == {"Can_Cfg.h", "Can_Cfg.c"}

    c_text = (tmp_path / "Can_Cfg.c").read_text()

    # Bit timing — same NBTP value the C1 hand-written table encoded.
    assert ".nbtp = 0x00090C01u" in c_text

    # Rx filter list: one entry, canid 0x100, std-id mask, Hrh 0.
    assert re.search(
        r"\.canid = 0x100u, \.mask = 0x7FFu, \.Hrh = 0u, \.isExtended = 0u",
        c_text,
    ), c_text

    # Tx slot list: one entry, Hth 0 → buffer 0.
    assert ".Hth = 0u, .bufferIndex = 0u" in c_text

    # MRAM layout sized to message count. h7-loopback has 1 Rx + 1 Tx
    # PDU, so:
    #   Rx FIFO 0 @ word 0, 1 element × 4 words
    #   Tx Buffer @ word 4, 1 element × 4 words
    # That's different from the C1 hand-written `rxFifo0Elements = 3u`
    # (which was a conservative-headroom choice, not a derived size).
    # The behaviour for h7-loopback is the same — the loopback frame
    # still round-trips — but the table is now derived from the spec.
    assert ".rxFifo0WordOffset = 0u" in c_text
    assert ".rxFifo0Elements   = 1u" in c_text
    assert ".rxFifo0ElemWords  = 4u" in c_text
    assert ".txBufWordOffset   = 4u" in c_text
    assert ".txBufElements     = 1u" in c_text
    assert ".txBufElemWords    = 4u" in c_text


def test_emitted_header_includes_kernel_clock_banner(tmp_path: Path):
    """The assumption (80 MHz) lives next to the code that depends on
    it, so a reader hitting the .h sees the contract immediately."""
    project = load_project(REPO_ROOT / "examples" / "h7-loopback")
    can_h7.generate(project, tmp_path)
    h_text = (tmp_path / "Can_Cfg.h").read_text()
    assert "80 MHz" in h_text
    assert "PLL2Q" in h_text


def test_emit_skips_when_canif_absent(tmp_path: Path):
    """A project with no CanIf is a host-only project; no Can_Cfg
    should be produced."""
    project = load_project(REPO_ROOT / "examples")  # not a project root
    written = can_h7.generate(project, tmp_path)
    assert written == []
