"""DBC import + auto-wire — unit + integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import validate
from gen import generate_and_compile
from importer import auto_wire_from_com, import_dbc_file, parse_dbc

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DBC = REPO_ROOT / "examples" / "dbc" / "sample.dbc"


# --- parse_dbc -------------------------------------------------------


def test_parse_sample_yields_two_messages():
    msgs = parse_dbc(SAMPLE_DBC)
    assert [m["name"] for m in msgs] == ["STATUS", "HEARTBEAT"]


def test_parse_preserves_id_as_hex_string():
    msgs = parse_dbc(SAMPLE_DBC)
    assert msgs[0]["id"] == "0x100"
    assert msgs[1]["id"] == "0x101"


def test_parse_preserves_dlc_and_cycle_time():
    msgs = parse_dbc(SAMPLE_DBC)
    assert msgs[0]["dlc"] == 8
    assert msgs[0]["CycleTime"] == 100
    assert msgs[1]["dlc"] == 4
    assert msgs[1]["CycleTime"] == 500


def test_parse_sender_node_lives_on_message():
    msgs = parse_dbc(SAMPLE_DBC)
    assert msgs[0]["node"] == "AS"
    assert msgs[1]["node"] == "Other"


def test_parse_signed_signal_uses_minus_sign_and_offset_passes_through():
    msgs = parse_dbc(SAMPLE_DBC)
    temp = msgs[1]["signals"][1]
    assert temp["name"] == "Temperature"
    assert temp["sign"] == "-"
    assert temp["offset"] == -40
    assert temp["min"] == -40
    assert temp["max"] == 215


def test_parse_scaled_signal_keeps_factor():
    msgs = parse_dbc(SAMPLE_DBC)
    speed = msgs[0]["signals"][1]
    assert speed["name"] == "Speed"
    assert speed["factor"] == 0.1


def test_parse_endian_mapping():
    msgs = parse_dbc(SAMPLE_DBC)
    for m in msgs:
        for s in m["signals"]:
            assert s["endian"] == "little"


def test_parse_receivers_become_node_list():
    msgs = parse_dbc(SAMPLE_DBC)
    counter = msgs[0]["signals"][0]
    assert counter["node"] == ["Other"]


# --- import_dbc_file ------------------------------------------------


def test_import_creates_all_four_modeled_modules():
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    for cls in ("Can", "Com", "CanIf", "PduR"):
        assert cls in project.raw
    assert project.com is not None
    assert project.canif is not None
    assert project.pdur is not None
    assert project.can is not None


def test_import_directs_messages_using_me():
    """STATUS is sent by AS → Tx. HEARTBEAT is sent by Other → Rx."""
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    rx = project.canif_rx_pdu_names()
    tx = project.canif_tx_pdu_names()
    assert "CAN0_STATUS_TX" in tx
    assert "CAN0_HEARTBEAT_RX" in rx


def test_import_emits_pdur_routines_for_both_directions():
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    routine_pairs = {(r.name, r.from_, r.to) for r in project.pdur.routines}
    assert ("CAN0_STATUS_TX", "Com", "CanIf") in routine_pairs
    assert ("CAN0_HEARTBEAT_RX", "CanIf", "Com") in routine_pairs


def test_import_creates_can_controller_with_network_name():
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    assert "CAN0" in project.can_controllers()


def test_import_swapping_me_flips_directions():
    """me=Other inverts every direction relative to me=AS."""
    proj_as = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    proj_other = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="Other")
    assert "CAN0_STATUS_TX" in proj_as.canif_tx_pdu_names()
    # With me=Other, STATUS becomes Rx so the derived name picks up `_RX`.
    assert "CAN0_STATUS_RX" in proj_other.canif_rx_pdu_names()


# --- auto_wire_from_com idempotency ---------------------------------


def test_auto_wire_is_idempotent():
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    canif_names_before = sorted(project.canif_pdu_names())
    routine_names_before = sorted(r.name for r in project.pdur.routines)
    project = auto_wire_from_com(project, network_name="CAN0")
    assert sorted(project.canif_pdu_names()) == canif_names_before
    assert sorted(r.name for r in project.pdur.routines) == routine_names_before


# --- end-to-end ------------------------------------------------------


def test_imported_project_validates_clean():
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    report = validate(project)
    assert report.ok, [(i.rule, i.message) for i in report.errors]


def test_imported_project_generates_and_compiles_clean(tmp_path: Path):
    """VERIFICATION LEVEL 1 after a DBC import — the whole point of
    auto-wire is that the result is generate+compile ready without
    any manual edits."""
    project = import_dbc_file(SAMPLE_DBC, network_name="CAN0", me="AS")
    result = generate_and_compile(project, tmp_path)
    assert result.compile_result is not None
    assert result.compile_result.status == "ok", (
        "compile failed after DBC import:\n"
        + "\n".join(
            f"  {m.severity.upper()} {m.file}:{m.line}: {m.message}"
            for m in result.compile_result.messages
        )
    )
    paths = {f.path for f in result.files}
    assert any(p.endswith("Com_Cfg.c") for p in paths)
    assert any(p.endswith("CanIf_Cfg.c") for p in paths)
    assert any(p.endswith("PduR_Cfg.c") for p in paths)
