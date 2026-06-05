"""CLI entry point — uses argparse via the importer.cli.main() function."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importer.cli import main

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DBC = REPO_ROOT / "examples" / "dbc" / "sample.dbc"


def test_cli_writes_four_modeled_jsons(tmp_path: Path, capsys):
    rc = main([str(SAMPLE_DBC), "--out", str(tmp_path)])
    assert rc == 0
    for rel in (
        "config/Can/Can.json",
        "config/Com/Com.json",
        "config/Com/CanIf.json",
        "config/Com/PduR.json",
    ):
        assert (tmp_path / rel).is_file(), rel


def test_cli_writes_valid_json_with_class_field(tmp_path: Path):
    main([str(SAMPLE_DBC), "--out", str(tmp_path)])
    com = json.loads((tmp_path / "config/Com/Com.json").read_text())
    assert com["class"] == "Com"
    assert com["networks"][0]["name"] == "CAN0"
    assert com["networks"][0]["me"] == "AS"


def test_cli_respects_network_and_me_flags(tmp_path: Path):
    main(
        [
            str(SAMPLE_DBC),
            "--out",
            str(tmp_path),
            "--network",
            "FOO",
            "--me",
            "Other",
        ]
    )
    can = json.loads((tmp_path / "config/Can/Can.json").read_text())
    com = json.loads((tmp_path / "config/Com/Com.json").read_text())
    assert can["controllers"][0]["name"] == "FOO"
    assert com["networks"][0]["me"] == "Other"


def test_cli_refuses_to_overwrite_without_force(tmp_path: Path):
    main([str(SAMPLE_DBC), "--out", str(tmp_path)])
    rc = main([str(SAMPLE_DBC), "--out", str(tmp_path)])
    assert rc != 0


def test_cli_overwrites_with_force(tmp_path: Path):
    main([str(SAMPLE_DBC), "--out", str(tmp_path)])
    rc = main([str(SAMPLE_DBC), "--out", str(tmp_path), "--force"])
    assert rc == 0


def test_cli_missing_dbc_returns_nonzero(tmp_path: Path):
    rc = main([str(tmp_path / "nope.dbc"), "--out", str(tmp_path / "out")])
    assert rc != 0
