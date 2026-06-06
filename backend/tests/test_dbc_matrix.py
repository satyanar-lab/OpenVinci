"""Matrix coverage over every DBC in examples/dbc/.

For each file we assert the full importer chain:

  parse_dbc → import_dbc_file → engine.validate → gen.generate_and_compile

This is the breadth complement to `test_importer_dbc.py` (which goes
deep on a single fixture). When the importer regresses on a real-world
shape (CamelCase names, multi-sender messages, large message sets,
J1939 IDs, …), the failure surfaces here.

Slow-ish: ~1s per DBC × 11 DBCs = ~10-15s total. Still fast enough
to leave in the unit suite; lives separate from `test_importer_dbc.py`
so a fault in one DBC doesn't drown the per-feature assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import load_project, to_macro, validate
from gen import generate_and_compile
from importer import auto_wire_from_com, import_dbc_file, parse_dbc

REPO_ROOT = Path(__file__).resolve().parents[2]
DBC_DIR = REPO_ROOT / "examples" / "dbc"

DBC_FILES = sorted(DBC_DIR.glob("*.dbc"))
assert DBC_FILES, "expected at least one DBC under examples/dbc/"

# Per-file me/network mapping. Default `me="AS"` works for synthetic
# fixtures; real-world DBCs only have specific node names so the
# generator's `node not in network.me` direction logic needs an `me`
# that ACTUALLY corresponds to one of the senders for the wiring to be
# meaningful. The default still validates + compiles clean, but
# overriding produces a more realistic Tx/Rx split per fixture.
ME_OVERRIDES: dict[str, str] = {
    "motohawk.dbc": "PCM1",
    "motohawk_fd.dbc": "PCM1",
    "foobar.dbc": "FOO",
    "j1939.dbc": "Node1",
    "multiple_senders.dbc": "Node1",
    "socialledge.dbc": "DBG",
    "subaru_forester_2017.dbc": "EPB",
    "honda_civic_touring_2016.dbc": "EPS",
    "toyota_tnga_k_pt.dbc": "XXX",
    "vehicle.dbc": "UnusedNode",
}


def _me_for(path: Path) -> str:
    return ME_OVERRIDES.get(path.name, "AS")


@pytest.mark.parametrize("dbc", DBC_FILES, ids=lambda p: p.name)
class TestDbcMatrix:
    """One test class per DBC, each instance running every check."""

    def test_parse_yields_at_least_one_message(self, dbc: Path):
        messages = parse_dbc(dbc)
        assert len(messages) >= 1
        for m in messages:
            assert m["name"]
            assert m["id"].startswith("0x")
            assert isinstance(m["dlc"], int) and m["dlc"] >= 0
            assert isinstance(m["signals"], list)

    def test_import_produces_all_four_modeled_modules(self, dbc: Path):
        project = import_dbc_file(dbc, network_name="CAN0", me=_me_for(dbc))
        for cls in ("Can", "Com", "CanIf", "PduR"):
            assert cls in project.raw, f"{dbc.name}: missing {cls}"

    def test_imported_project_validates_clean(self, dbc: Path):
        project = import_dbc_file(dbc, network_name="CAN0", me=_me_for(dbc))
        report = validate(project)
        assert report.ok, (
            f"{dbc.name} validation errors:\n"
            + "\n".join(f"  [{i.rule}] {i.message}" for i in report.errors)
        )

    def test_auto_wire_is_idempotent(self, dbc: Path):
        project = import_dbc_file(dbc, network_name="CAN0", me=_me_for(dbc))
        before = (
            sorted(project.canif_pdu_names()),
            sorted(r.name for r in project.pdur.routines),
        )
        auto_wire_from_com(project, network_name="CAN0")
        after = (
            sorted(project.canif_pdu_names()),
            sorted(r.name for r in project.pdur.routines),
        )
        assert before == after

    def test_generates_and_compiles_clean_against_BSW(self, dbc: Path, tmp_path: Path):
        project = import_dbc_file(dbc, network_name="CAN0", me=_me_for(dbc))
        result = generate_and_compile(project, tmp_path)
        cr = result.compile_result
        assert cr is not None
        assert cr.status == "ok", (
            f"{dbc.name} compile failed:\n"
            + "\n".join(
                f"  [{m.severity}] {m.file}:{m.line} {m.message}"
                for m in cr.messages
            )
        )
        # The big sanity: every Com macro a PduR routine references must
        # appear in Com_Cfg.h. We've already proven this via the gcc
        # compile, but assert at least the canonical files exist too.
        paths = {f.path for f in result.files}
        for stem in ("Com_Cfg.c", "Com_Cfg.h", "CanIf_Cfg.c", "PduR_Cfg.c"):
            assert any(p.endswith(stem) for p in paths), f"missing {stem}"


# --- single sanity check for the toMacro port -------------------------


def test_to_macro_matches_known_vendor_as_outputs():
    """Spot-check vendor/as/tools/generator/helper.py::toMacro behaviour
    we have to mirror so `COM_<routine>` references resolve."""
    assert to_macro("ExampleMessage") == "EXAMPLE_MESSAGE"
    assert to_macro("TX_MSG") == "TX_MSG"
    assert to_macro("CAN0") == "CAN0"
    assert to_macro("Foo_RX") == "FOO_RX"
    # Abbreviation substitution kicks in after the CamelCase split:
    # CanTp → ["Can", "Tp"] → "CAN_TP" → "CANTP".
    assert to_macro("CanTp") == "CANTP"
    assert to_macro("PduR") == "PDUR"
    assert to_macro("CanIf") == "CANIF"
    assert to_macro("RT_SB_INS_Vel_Body_Axes") == "RT_SB_INS_VEL_BODY_AXES"
