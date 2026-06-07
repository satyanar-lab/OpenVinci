"""STM32H7 FDCAN driver-config generator (PROMPT C2).

Emits a `Can_Cfg.h` / `Can_Cfg.c` pair in the table shape PROMPT C1
locked down (`Can_H7_HwConfigType`). Same project tree the vendor
generators run against — we read `config/Com/CanIf.json` and
`config/Com/Com.json` straight from the staged dir.

What goes in:

  - Baud rate (Com.json's `networks[i].baudrate`, default 500 kbit/s)
  - Rx/Tx PDU list (CanIf.json's `RxPdus[]` / `TxPdus[]`)
  - Per-PDU `hoh` (the hardware-object-handle generated CanIf_Cfg.c
    already wires up — we carry it through verbatim so handles line
    up across the upper- and lower-layer configs)

What gets computed:

  - NBTP register value via the same `CAN_H7_NBTP(...)` macro
    Can_Cfg.h declares — see `_compute_nbtp_fields()` below.
  - Message-RAM layout sized to PDU count: Rx FIFO 0 holds one
    element per Rx PDU; Tx region holds one dedicated buffer per
    unique Tx `hoh`. Rx region sits at word 0, Tx immediately after.

Assumed FDCAN kernel clock: **80 MHz**. That's what
`hardware/stm32h753zi/src/system_init.c` programs via PLL2Q
(`pll2_enable_for_fdcan`). If a future board pins it elsewhere this
constant moves into the project target spec — but today there is
exactly one H7 target, so the assumption lives here and is documented
both in the emitted `Can_Cfg.h` and in the README.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine import Project

# Documented assumed FDCAN kernel-clock frequency for the STM32H753ZI
# build. Lives next to the math so the math + assumption travel
# together.
FDCAN_KERNEL_CLOCK_HZ: int = 80_000_000

# M_CAN NBTP register-field positions (RM0433 §57.6.2). Mirrored
# byte-for-byte by the CAN_H7_NBTP(...) packing macro in Can_Cfg.h —
# duplicated here only so the generator can sanity-check the packed
# value in the regression test.
NBTP_NSJW_POS: int = 25
NBTP_NBRP_POS: int = 16
NBTP_NTSEG1_POS: int = 8
NBTP_NTSEG2_POS: int = 0

# Default sample point we aim for at the start of the BRP search. M_CAN
# accepts a wide range here; 87.5 % is what STM32CubeMX picks for
# Classic CAN at 500 kbit/s on the H7 reference board and is what the
# C1 hand-written table encodes.
DEFAULT_SAMPLE_POINT_PERMILLE: int = 875


# ----------------------------- bit timing ---------------------------


@dataclass(frozen=True)
class NbtpFields:
    """Result of the bit-timing search — fields are the human values
    (BRP=10, TSEG1=13, ...), NOT the M_CAN encoding (which subtracts
    one). `register_value` is what the generator embeds via
    CAN_H7_NBTP(brp-1, tseg1-1, tseg2-1, sjw-1)."""

    brp: int
    tseg1: int
    tseg2: int
    sjw: int

    @property
    def total_tq_per_bit(self) -> int:
        return 1 + self.tseg1 + self.tseg2

    @property
    def sample_point_permille(self) -> int:
        return int(round((1 + self.tseg1) * 1000 / self.total_tq_per_bit))

    @property
    def register_value(self) -> int:
        """Pack into NBTP register layout — must equal what the
        Can_Cfg.h CAN_H7_NBTP(...) macro produces."""
        return (
            ((self.sjw - 1) & 0x7F) << NBTP_NSJW_POS
            | ((self.brp - 1) & 0x1FF) << NBTP_NBRP_POS
            | ((self.tseg1 - 1) & 0xFF) << NBTP_NTSEG1_POS
            | ((self.tseg2 - 1) & 0x7F) << NBTP_NTSEG2_POS
        )


# Bosch CAN bit-timing app note recommends 8..25 tq per bit, with a
# practical sweet spot near 16. STM32CubeMX 6.x converges on the same
# value for the H7 reference board, so picking total-tq closest to 16
# means our generator matches the CubeMX-derived numbers C1 hardcoded.
_IDEAL_TQ_PER_BIT = 16
_TQ_PER_BIT_MIN = 8
_TQ_PER_BIT_MAX = 25


def _compute_nbtp_fields(
    kernel_clock_hz: int,
    baud_bps: int,
    target_sample_point_permille: int = DEFAULT_SAMPLE_POINT_PERMILLE,
) -> NbtpFields:
    """Find NBTP fields that hit exactly `baud_bps` at `kernel_clock_hz`.

    Strategy: walk candidate `total_tq` values in [{TQ_MIN}, {TQ_MAX}]
    by distance from the ideal 16-tq-per-bit recommendation, picking
    the first one whose BRP divides cleanly. Then derive TSEG1/TSEG2
    from the requested sample point. We require an exact match on the
    baud rate (no rounding error on the wire) — every realistic CAN
    rate divides 80 MHz cleanly so this is fine in practice.

    Why "closest to 16" instead of "smallest BRP": both work for the
    bit time, but the 16-tq convention is what STM32CubeMX picks for
    the H7 (and what the Bosch CAN application note recommends for
    jitter tolerance). Matching CubeMX means our generator produces
    the same NBTP value the C1 hand-written table verified on real
    silicon, with no surprise drift on a future re-run.

    Field ranges (M_CAN, encoded as "value - 1" so the human values
    that survive the search are >= 1):
        BRP    : 1..512   (NBRP   : 0..511 in 9 bits)
        TSEG1  : 1..256   (NTSEG1 : 0..255 in 8 bits)
        TSEG2  : 1..128   (NTSEG2 : 0..127 in 7 bits)
        SJW    : 1..128   (NSJW   : 0..127 in 7 bits)
    """
    if baud_bps <= 0:
        raise ValueError(f"baud_bps must be positive (got {baud_bps})")
    if kernel_clock_hz <= 0:
        raise ValueError(f"kernel_clock_hz must be positive (got {kernel_clock_hz})")

    # Walk total-tq candidates by distance from the ideal value. Ties
    # resolve by larger-total-tq-first (gives more sample-point
    # resolution).
    candidates = sorted(
        range(_TQ_PER_BIT_MIN, _TQ_PER_BIT_MAX + 1),
        key=lambda n: (abs(n - _IDEAL_TQ_PER_BIT), -n),
    )
    for total_tq in candidates:
        if (kernel_clock_hz % (total_tq * baud_bps)) != 0:
            continue
        brp = kernel_clock_hz // (total_tq * baud_bps)
        if brp < 1 or brp > 512:
            continue
        # Pick TSEG1 to land closest to the requested sample point.
        ideal_tseg1 = (target_sample_point_permille * total_tq) // 1000 - 1
        tseg1 = max(1, min(256, ideal_tseg1))
        tseg2 = total_tq - 1 - tseg1
        if tseg2 < 1 or tseg2 > 128:
            continue
        # SJW gates how aggressively the controller can resync; the
        # CubeMX-derived value the C1 hand-written table verified on
        # real silicon is 1. The CAN spec allows up to min(TSEG2, 4),
        # but the conservative SJW=1 matches CubeMX's default exactly
        # and is what virtually every Classic-CAN cookbook recommends
        # — anything bigger only helps if the bus has noticeable
        # clock-drift between nodes, which doesn't apply here.
        sjw = max(1, min(tseg2, 1))
        return NbtpFields(brp=brp, tseg1=tseg1, tseg2=tseg2, sjw=sjw)

    raise ValueError(
        f"no NBTP fit for baud={baud_bps} at kernel={kernel_clock_hz} — "
        f"no total-tq in [{_TQ_PER_BIT_MIN}, {_TQ_PER_BIT_MAX}] divides "
        "kernel/baud evenly."
    )


# --------------------------- project parsing ------------------------


@dataclass(frozen=True)
class _PduEntry:
    name: str
    canid: int          # numeric, parsed from "0x100" or "256"
    hoh: int
    is_extended: bool


@dataclass(frozen=True)
class _ChannelPlan:
    """One CAN channel's worth of routing extracted from CanIf+Com."""

    network_name: str
    baud_bps: int
    rx_pdus: list[_PduEntry]
    tx_pdus: list[_PduEntry]


def _parse_canid(raw: str) -> tuple[int, bool]:
    """Parse the CanIf JSON's id field. Returns (canid, is_extended).

    CanIf.json encodes the id either as a plain string like "0x100"
    (standard) or with the extended-bit set via a "0x80000000 | id"
    convention (matches Can_IdType.AUTOSAR top-bit semantics). Numbers
    above 0x7FF that don't set the top bit are still treated as
    extended — that's how `examples/canfd-minimal` writes them.
    """
    val = int(raw, 0)
    if (val & 0x80000000) != 0:
        return val & 0x1FFFFFFF, True
    if val > 0x7FF:
        return val, True
    return val, False


def _build_channel_plans(project: Project) -> list[_ChannelPlan]:
    if project.canif is None:
        return []
    # Index Com baud by network for a quick lookup.
    com_baud: dict[str, int] = {}
    if project.com is not None:
        for net in project.com.networks:
            com_baud[net.name] = int(net.baudrate or 500_000)

    plans: list[_ChannelPlan] = []
    for net in project.canif.networks:
        rx = [
            _PduEntry(name=p.name, canid=cid, hoh=p.hoh, is_extended=ext)
            for p in net.RxPdus
            for cid, ext in [_parse_canid(p.id)]
        ]
        tx = [
            _PduEntry(name=p.name, canid=cid, hoh=p.hoh, is_extended=ext)
            for p in net.TxPdus
            for cid, ext in [_parse_canid(p.id)]
        ]
        baud = com_baud.get(net.name, 500_000)
        plans.append(
            _ChannelPlan(
                network_name=net.name,
                baud_bps=baud,
                rx_pdus=rx,
                tx_pdus=tx,
            )
        )
    return plans


# ------------------------------ codegen -----------------------------


_H_TEMPLATE = """\
/*
 * Can_Cfg.h — STM32H753ZI FDCAN backend driver config.
 *
 * GENERATED by backend/gen/can_h7.py for target stm32h753zi.
 * Do not edit by hand; regenerate via `make generate` in
 * hardware/stm32h753zi/.
 *
 * Vendor MCAL knobs that vendor/as `infras/mcal/Can/Can.c` reads
 * stay alongside the H7-backend driver-config table — the latter is
 * what src/Can_H7.c iterates on init and per Rx/Tx (PROMPT C1).
 *
 * Assumed FDCAN kernel clock: {kernel_clock_mhz} MHz (PLL2Q routed
 * via D2CCIP1R.FDCANSEL = 10, set up by src/system_init.c).
 */
#ifndef CAN_CFG_H
#define CAN_CFG_H

#include "Std_Types.h"
#include "Can_GeneralTypes.h"   /* Can_HwHandleType, Can_IdType */

#ifdef __cplusplus
extern "C" {{
#endif

/* ---------------- vendor MCAL knobs ----------------------------- */
#define CAN_USE_CTRL_AC_GLOBAL
#define CAN_NUM_CHANNELS  {num_channels}u

/* ---------------- H7 backend driver-config shape (PROMPT C1) ---- */

/* Pack a Nominal Bit Timing & Prescaler (FDCAN_NBTP) value. Fields
 * are the M_CAN encoded form (value - 1); see Can_GeneralTypes.h
 * commentary and RM0433 §57.6.2. */
#define CAN_H7_NBTP(nbrp_m1, ntseg1_m1, ntseg2_m1, nsjw_m1)                \\
    (((uint32_t)(nsjw_m1)   << 25) |                                       \\
     ((uint32_t)(nbrp_m1)   << 16) |                                       \\
     ((uint32_t)(ntseg1_m1) <<  8) |                                       \\
     ((uint32_t)(ntseg2_m1) <<  0))

typedef struct {{
    Can_IdType        canid;
    Can_IdType        mask;
    Can_HwHandleType  Hrh;
    uint8_t           isExtended;
}} Can_H7_RxFilterType;

typedef struct {{
    Can_HwHandleType  Hth;
    uint8_t           bufferIndex;
}} Can_H7_TxSlotType;

typedef struct {{
    uint16_t  rxFifo0WordOffset;
    uint8_t   rxFifo0Elements;
    uint8_t   rxFifo0ElemWords;
    uint16_t  txBufWordOffset;
    uint8_t   txBufElements;
    uint8_t   txBufElemWords;
}} Can_H7_MramLayoutType;

typedef struct {{
    uint32_t                       nbtp;
    uint32_t                       dbtp;
    Can_H7_MramLayoutType          mram;
    const Can_H7_RxFilterType     *rxFilters;
    uint8_t                        numRxFilters;
    const Can_H7_TxSlotType       *txSlots;
    uint8_t                        numTxSlots;
}} Can_H7_HwConfigType;

extern const Can_H7_HwConfigType Can_H7_Config;

#ifdef __cplusplus
}}
#endif

#endif /* CAN_CFG_H */
"""


_C_HEADER = """\
/*
 * Can_Cfg.c — STM32H753ZI FDCAN backend driver config (tables).
 *
 * GENERATED by backend/gen/can_h7.py for target stm32h753zi.
 * Do not edit by hand; regenerate via `make generate` in
 * hardware/stm32h753zi/.
 *
 * Bit timing computed for {baud_kbps} kbit/s nominal at
 * {kernel_clock_mhz} MHz FDCAN kernel clock:
 *   BRP={brp}, TSEG1={tseg1}, TSEG2={tseg2}, SJW={sjw}
 *   → sample point {sample_point_permille_one_decimal} % (target {target_sample_permille_one_decimal} %)
 *   → NBTP register value = 0x{nbtp_value:08X}
 */

#include "Can.h"
#include "Can_Priv.h"
#include "Can_Cfg.h"

/* ============================================================ vendor
 * The Can_ConfigType vendor/as Can.c dereferences via CAN_CONFIG. */

static Can_ChannelContextType s_can0_context;

static const Can_ChannelConfigType s_can0_cfg = {{
    .context = &s_can0_context,
#ifndef USE_PORT
    .CtrlPins = NULL,
    .numOfCtrlPins = 0,
    .TrcvPinSTB = 0,
#endif
    .baudrate = {baud_bps}u,
    .samplePoint = {sample_point_percent}u,
    .hwInstanceId = 0u,
    .NormalValueOfTrcvPinSTB = 0u,
}};

static const Can_ChannelConfigType s_channel_configs[1] = {{ s_can0_cfg }};
static const uint8_t s_hw_to_channel[1] = {{ 0u }};

Can_ConfigType Can_Config = {{
    .channelConfigs     = s_channel_configs,
    .hwIns2ChlMap       = s_hw_to_channel,
    .numOfChannels      = CAN_NUM_CHANNELS,
    .sizeOfhwIns2ChlMap = (uint8_t)(sizeof(s_hw_to_channel) /
                                    sizeof(s_hw_to_channel[0])),
}};

/* ====================================================== H7 backend */
"""


def _emit_rx_filter_table(plan: _ChannelPlan) -> str:
    if not plan.rx_pdus:
        return (
            "/* No Rx PDUs — table empty. */\n"
            "static const Can_H7_RxFilterType s_rx_filters[1] = {\n"
            "    { .canid = 0u, .mask = 0u, .Hrh = 0u, .isExtended = 0u },\n"
            "};\n"
            "#define S_RX_FILTERS_COUNT 0u\n"
        )
    lines = ["static const Can_H7_RxFilterType s_rx_filters[] = {"]
    for pdu in plan.rx_pdus:
        mask = 0x1FFFFFFF if pdu.is_extended else 0x7FF
        lines.append(
            f"    {{ .canid = 0x{pdu.canid:03X}u, .mask = 0x{mask:X}u, "
            f".Hrh = {pdu.hoh}u, .isExtended = {1 if pdu.is_extended else 0}u }},"
            f"   /* {pdu.name} */"
        )
    lines.append("};")
    lines.append(
        "#define S_RX_FILTERS_COUNT "
        "(uint8_t)(sizeof(s_rx_filters) / sizeof(s_rx_filters[0]))"
    )
    return "\n".join(lines) + "\n"


def _emit_tx_slot_table(plan: _ChannelPlan) -> tuple[str, int]:
    """Emit the Tx slot table + return the number of unique Tx hohs
    (which is what the M_CAN dedicated-Tx-buffer count needs to be)."""
    # Unique hohs in first-appearance order: each unique hoh is one
    # dedicated Tx buffer in MRAM; bufferIndex follows that order.
    seen: dict[int, int] = {}
    slot_lines: list[str] = []
    for pdu in plan.tx_pdus:
        if pdu.hoh in seen:
            continue
        idx = len(seen)
        seen[pdu.hoh] = idx
        slot_lines.append(
            f"    {{ .Hth = {pdu.hoh}u, .bufferIndex = {idx}u }},   /* {pdu.name} */"
        )
    if not slot_lines:
        body = (
            "/* No Tx PDUs — table empty. */\n"
            "static const Can_H7_TxSlotType s_tx_slots[1] = {\n"
            "    { .Hth = 0u, .bufferIndex = 0u },\n"
            "};\n"
            "#define S_TX_SLOTS_COUNT 0u\n"
        )
        return body, 0

    out = (
        "static const Can_H7_TxSlotType s_tx_slots[] = {\n"
        + "\n".join(slot_lines)
        + "\n};\n"
        "#define S_TX_SLOTS_COUNT "
        "(uint8_t)(sizeof(s_tx_slots) / sizeof(s_tx_slots[0]))\n"
    )
    return out, len(seen)


def _emit_config_aggregate(
    plan: _ChannelPlan,
    nbtp_value: int,
    num_tx_buffers: int,
) -> str:
    # Element size = 4 words = 2 header words + 2 data words (8 B
    # payload) = Classic CAN. FD bumps this to 18 words / 64 B.
    rx_elem_words = 4
    tx_elem_words = 4
    rx_elems = max(1, len(plan.rx_pdus))
    tx_elems = max(1, num_tx_buffers)
    rx_offset = 0
    tx_offset = rx_offset + rx_elems * rx_elem_words

    return (
        "\n"
        "const Can_H7_HwConfigType Can_H7_Config = {\n"
        f"    .nbtp = 0x{nbtp_value:08X}u,   /* see header banner for fields */\n"
        "    .dbtp = 0u,             /* FD off in this build */\n"
        "    .mram = {\n"
        f"        .rxFifo0WordOffset = {rx_offset}u,\n"
        f"        .rxFifo0Elements   = {rx_elems}u,\n"
        f"        .rxFifo0ElemWords  = {rx_elem_words}u,\n"
        f"        .txBufWordOffset   = {tx_offset}u,\n"
        f"        .txBufElements     = {tx_elems}u,\n"
        f"        .txBufElemWords    = {tx_elem_words}u,\n"
        "    },\n"
        "    .rxFilters    = s_rx_filters,\n"
        "    .numRxFilters = S_RX_FILTERS_COUNT,\n"
        "    .txSlots      = s_tx_slots,\n"
        "    .numTxSlots   = S_TX_SLOTS_COUNT,\n"
        "};\n"
    )


# ----------------------------- entrypoint ---------------------------


def is_h7_target(project_root: Path) -> bool:
    """True iff `<project_root>/project.json` selects target=stm32h753zi."""
    p = Path(project_root) / "project.json"
    if not p.is_file():
        return False
    import json

    raw = json.loads(p.read_text())
    return raw.get("target") == "stm32h753zi"


def generate(
    project: Project,
    output_dir: Path,
    *,
    kernel_clock_hz: int = FDCAN_KERNEL_CLOCK_HZ,
) -> list[Path]:
    """Emit Can_Cfg.h and Can_Cfg.c into `output_dir`. Returns the
    written paths.

    Project must have a CanIf; an absent Com is treated as 500 kbit/s
    default (matches what the host-sim L2 tests use)."""
    plans = _build_channel_plans(project)
    if not plans:
        return []
    # Multi-channel emit is on the roadmap; today the H7 build is
    # single-controller (FDCAN1 only — see hardware/stm32h753zi/
    # src/Can_Cfg.c's `numOfChannels = 1`).
    plan = plans[0]

    nbtp = _compute_nbtp_fields(kernel_clock_hz, plan.baud_bps)
    sample_pp = nbtp.sample_point_permille
    target_pp = DEFAULT_SAMPLE_POINT_PERMILLE

    h_text = _H_TEMPLATE.format(
        kernel_clock_mhz=kernel_clock_hz // 1_000_000,
        num_channels=len(plans),
    )

    rx_block = _emit_rx_filter_table(plan)
    tx_block, n_tx_bufs = _emit_tx_slot_table(plan)
    aggregate = _emit_config_aggregate(plan, nbtp.register_value, n_tx_bufs)

    c_text = (
        _C_HEADER.format(
            baud_kbps=plan.baud_bps // 1000,
            baud_bps=plan.baud_bps,
            kernel_clock_mhz=kernel_clock_hz // 1_000_000,
            brp=nbtp.brp,
            tseg1=nbtp.tseg1,
            tseg2=nbtp.tseg2,
            sjw=nbtp.sjw,
            sample_point_permille_one_decimal=f"{sample_pp / 10:.1f}",
            target_sample_permille_one_decimal=f"{target_pp / 10:.1f}",
            sample_point_percent=int(round(sample_pp / 10)),
            nbtp_value=nbtp.register_value,
        )
        + rx_block
        + "\n"
        + tx_block
        + aggregate
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, body in (("Can_Cfg.h", h_text), ("Can_Cfg.c", c_text)):
        p = output_dir / name
        p.write_text(body)
        written.append(p)
    return written
