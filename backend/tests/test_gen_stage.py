"""Staging mechanics — the model serialization that feeds generation."""

from __future__ import annotations

import json
from pathlib import Path

from engine import load_project
from gen import stage_project

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_stage_writes_each_modeled_module(tmp_path: Path):
    project = load_project(REPO_ROOT / "examples" / "com-minimal")
    stage_project(project, tmp_path)
    assert (tmp_path / "config" / "Com" / "Com.json").is_file()
    assert (tmp_path / "config" / "Com" / "CanIf.json").is_file()
    assert (tmp_path / "config" / "Com" / "PduR.json").is_file()


def test_staged_json_round_trips_through_model(tmp_path: Path):
    """The staged JSON must equal the in-memory project's raw data."""
    src = REPO_ROOT / "examples" / "com-minimal"
    project = load_project(src)
    stage_project(project, tmp_path)
    for rel in (
        "config/Com/Com.json",
        "config/Com/CanIf.json",
        "config/Com/PduR.json",
    ):
        original = json.loads((src / rel).read_text())
        staged = json.loads((tmp_path / rel).read_text())
        assert staged == original, rel


def test_stage_copies_ancillary_files_from_source_dir(tmp_path: Path):
    """E2E.json / *.dbc / etc. are passed through verbatim."""
    src = tmp_path / "src"
    dest = tmp_path / "out"
    (src / "config" / "Com").mkdir(parents=True)
    (src / "config" / "Com" / "Com.json").write_text(
        '{"class": "Com", "networks": [{"name": "CAN0", "network": "CAN", "me": "AS"}]}'
    )
    (src / "config" / "Com" / "CAN0.dbc").write_text("VERSION \"\"\n")

    project = load_project(src)
    stage_project(project, dest, source_dir=src)

    assert (dest / "config" / "Com" / "Com.json").is_file()
    assert (dest / "config" / "Com" / "CAN0.dbc").is_file()


def test_stage_skips_GEN_dirs_in_source(tmp_path: Path):
    """Re-staging a previously generated tree must not copy stale GEN/."""
    src = tmp_path / "src"
    dest = tmp_path / "out"
    (src / "config" / "Com").mkdir(parents=True)
    (src / "config" / "Com" / "Com.json").write_text(
        '{"class": "Com", "networks": [{"name": "CAN0", "network": "CAN", "me": "AS"}]}'
    )
    (src / "config" / "Com" / "GEN").mkdir()
    (src / "config" / "Com" / "GEN" / "Com_Cfg.c").write_text("/* stale */\n")

    project = load_project(src)
    stage_project(project, dest, source_dir=src)
    assert not (dest / "config" / "Com" / "GEN").exists()
