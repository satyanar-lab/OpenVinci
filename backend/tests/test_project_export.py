"""STM32H7 project export (backend/gen/project_export.py, PROMPT C4).

Covers the structural guarantees an exported project must hold for
the user to be able to `cd` into it and run `make` with no extra
setup:

  - Every file Makefile.export's link command references is present.
  - No path inside the export points back at the OpenVinci repo
    (no `../`, no absolute paths into the source tree). If this ever
    regresses the exported project would silently rely on artefacts
    living outside its own folder.
  - The README mentions the project name and walks through `make`
    + `make flash`.
  - The Makefile has the project slug substituted (so `build/<name>.elf`
    is named after the project, not literally `{project}`).
  - The exported Can_Cfg / EcuM glue come from the same generators
    /api/generate uses; their content is covered by the per-generator
    tests, so here we just check they're present and named right.

We deliberately do NOT cross-compile in this test. CI does that via
`.github/workflows/firmware-export-build.yml`.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from engine import load_project
from gen import project_export

REPO_ROOT = Path(__file__).resolve().parents[2]
H7_PROJECT = REPO_ROOT / "examples" / "h7-loopback"


# ----------------------------- layout -------------------------------


def test_export_layout_self_contained(tmp_path: Path):
    project = load_project(H7_PROJECT)
    out = tmp_path / "export"
    result = project_export.assemble_h7_project(project, out, source_dir=H7_PROJECT)

    # Files the Makefile.export's link line references — all must
    # exist relative to the export root.
    must_exist = [
        out / "Makefile",
        out / "README.md",
        out / "linker" / "stm32h753xx_flash.ld",
        out / "src" / "Can_H7.c",
        out / "src" / "system_init.c",
        out / "src" / "board.c",
        out / "include" / "board.h",
        # Generated config (vendor + can_h7).
        out / "generated" / "Com_Cfg.c",
        out / "generated" / "PduR_Cfg.c",
        out / "generated" / "CanIf_Cfg.c",
        out / "generated" / "Can_Cfg.c",
        # Generated glue (ecu_glue).
        out / "generated" / "EcuM.c",
        out / "generated" / "Sched.c",
        out / "generated" / "App_Demo.c",
        out / "generated" / "App.h",
        # BSW sources.
        out / "bsw" / "communication" / "Com" / "Com.c",
        out / "bsw" / "communication" / "PduR" / "PduR.c",
        out / "bsw" / "communication" / "PduR" / "PduR_Com.c",
        out / "bsw" / "communication" / "PduR" / "PduR_CanIf.c",
        out / "bsw" / "communication" / "CanIf" / "CanIf.c",
        out / "bsw" / "mcal" / "Can" / "Can.c",
        out / "bsw" / "libraries" / "stdbit" / "src" / "std_bit.c",
        out / "bsw" / "libraries" / "mempool" / "mempool.c",
        # CMSIS startup + system.
        out / "third_party" / "cmsis-device-h7" / "Source" / "Templates"
            / "gcc" / "startup_stm32h753xx.s",
        out / "third_party" / "cmsis-device-h7" / "Source" / "Templates"
            / "system_stm32h7xx.c",
        out / "third_party" / "cmsis-device-h7" / "Include" / "stm32h753xx.h",
        out / "third_party" / "CMSIS_5" / "CMSIS" / "Core" / "Include" / "core_cm7.h",
    ]
    for path in must_exist:
        assert path.is_file(), f"export missing {path.relative_to(out)}"

    assert result.project_label == "h7-loopback"


def test_no_paths_escape_the_export_root(tmp_path: Path):
    """Every file written must sit inside output_dir. A bug that
    started writing into the host repo (e.g. via an unresolved symlink
    target) would catch here."""
    project = load_project(H7_PROJECT)
    out = tmp_path / "export"
    result = project_export.assemble_h7_project(project, out, source_dir=H7_PROJECT)
    for p in result.written:
        # Path.is_relative_to landed in 3.9 — REPO_ROOT does have ".."
        # off of `out`, so this excludes any leak.
        assert p.is_relative_to(out), f"escaped export root: {p}"


def test_makefile_references_no_repo_paths(tmp_path: Path):
    """The export's Makefile must not reference the host OpenVinci
    repo. A `../../vendor/as/...` in there means the exported folder
    isn't actually self-contained."""
    project = load_project(H7_PROJECT)
    out = tmp_path / "export"
    project_export.assemble_h7_project(project, out, source_dir=H7_PROJECT)
    body = (out / "Makefile").read_text()
    forbidden = ("../", "/home/", "/Users/", "vendor/as/")
    for token in forbidden:
        assert token not in body, (
            f"exported Makefile references {token!r} — not self-contained"
        )


def test_makefile_substitutes_project_slug(tmp_path: Path):
    """`PROJECT := {project}` should become the real project name so
    the binaries are named `h7-loopback.elf` etc."""
    project = load_project(H7_PROJECT)
    out = tmp_path / "export"
    project_export.assemble_h7_project(project, out, source_dir=H7_PROJECT)
    body = (out / "Makefile").read_text()
    assert "PROJECT     := h7-loopback" in body
    assert "{project}" not in body, "unresolved template placeholder"


# ----------------------------- README -------------------------------


def test_readme_mentions_project_name_and_build_flow(tmp_path: Path):
    project = load_project(H7_PROJECT)
    out = tmp_path / "export"
    project_export.assemble_h7_project(project, out, source_dir=H7_PROJECT)
    body = (out / "README.md").read_text()
    assert "h7-loopback" in body
    assert "make " in body
    assert "make flash" in body
    assert "115200" in body
    # The signal names should show up so a reader sees what the demo
    # actually drives.
    assert "TxSignal" in body
    assert "RxSignal" in body


# ------------------------- zip wrapper ------------------------------


def test_write_zip_arcnames_rooted_at_project_label(tmp_path: Path):
    """Unzipping must produce a single top-level dir named after the
    project — not a loose-file dump in the user's CWD."""
    project = load_project(H7_PROJECT)
    payload, label = project_export.write_zip(project, source_dir=H7_PROJECT)
    assert label == "h7-loopback"
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
    assert names, "zip is empty"
    for name in names:
        assert name.startswith("h7-loopback/"), name


# ------------------------------ CLI guards --------------------------


def test_cli_rejects_unknown_project(tmp_path: Path, capsys, monkeypatch):
    """`python -m gen.project_export missing` should fail loudly,
    not silently produce an empty folder."""
    monkeypatch.setattr(
        "sys.argv",
        ["project_export", "definitely-not-a-real-example"],
    )
    rc = project_export._cli()
    assert rc != 0
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_cli_rejects_non_h7_project(tmp_path: Path, capsys, monkeypatch):
    """com-minimal has no project.json target. The CLI should refuse
    rather than emit a broken project."""
    monkeypatch.setattr("sys.argv", ["project_export", "com-minimal"])
    rc = project_export._cli()
    assert rc != 0
    captured = capsys.readouterr()
    assert "target=stm32h753zi" in captured.err
