"""H7 golden snapshot — frozen byte content of the h7-loopback export.

Same kind of guarantee `test_golden.py` gives for the host-sim
examples, extended to the STM32H753ZI generator chain (PROMPTS C2 +
C3 + C4):

  - The vendor *_Cfg.{c,h} (Com / PduR / CanIf) the upstream
    generator emits.
  - Our `Can_Cfg.{c,h}` from `backend/gen/can_h7.py`.
  - The integration glue (EcuM / Sched / App.h / App_Demo.c) from
    `backend/gen/ecu_glue.py`.

All three are bundled into the `generated/` subdir of the assembled
firmware project, so we run the same `project_export.assemble_h7_project`
the CLI / `/api/generate/zip` already use, and snapshot just that
directory (the fixed templates + BSW + CMSIS copies inside the export
travel verbatim — they're not derived state worth pinning here).

Rebaseline with:

    pytest tests/golden/test_h7_golden.py --update-golden
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engine import load_project  # noqa: E402
from gen import can_h7, project_export  # noqa: E402

from .normalize import normalize_bytes  # noqa: E402

EXAMPLES = REPO_ROOT / "examples"
GOLDEN = Path(__file__).parent
H7_EXAMPLE = "h7-loopback"


def test_h7_loopback_generated_dir_matches_snapshot(tmp_path: Path, request):
    update = request.config.getoption("--update-golden")
    expected_root = GOLDEN / H7_EXAMPLE / "expected" / "generated"

    project = load_project(EXAMPLES / H7_EXAMPLE)
    out = tmp_path / "export"
    project_export.assemble_h7_project(
        project, out, source_dir=EXAMPLES / H7_EXAMPLE
    )
    generated_dir = out / "generated"

    generated_files = {
        str(p.relative_to(generated_dir)): p
        for p in generated_dir.rglob("*")
        if p.is_file()
    }
    assert generated_files, "export produced an empty generated/ dir"

    if update:
        _refresh_expected(expected_root, generated_files)
        pytest.skip(
            f"updated {len(generated_files)} snapshots under {expected_root}"
        )

    if not expected_root.is_dir():
        pytest.fail(
            f"no golden snapshots under {expected_root} — run with "
            f"--update-golden after the first generation to create them."
        )

    expected_files = {
        str(p.relative_to(expected_root)): p
        for p in expected_root.rglob("*")
        if p.is_file()
    }

    actual_normalized = {
        rel: normalize_bytes(path.read_bytes())
        for rel, path in generated_files.items()
    }
    expected_normalized = {
        rel: normalize_bytes(path.read_bytes())
        for rel, path in expected_files.items()
    }

    only_generated = sorted(set(actual_normalized) - set(expected_normalized))
    only_expected = sorted(set(expected_normalized) - set(actual_normalized))
    assert not only_generated and not only_expected, (
        "file set drift:\n"
        f"  only in generation: {only_generated}\n"
        f"  only in snapshot:   {only_expected}\n"
        f"Run pytest with --update-golden after intentional changes."
    )

    diffs: list[str] = []
    for rel in sorted(actual_normalized):
        if actual_normalized[rel] != expected_normalized[rel]:
            diffs.append(rel)
    assert not diffs, (
        "content drift in:\n  "
        + "\n  ".join(diffs)
        + "\nRun pytest with --update-golden after verifying the changes "
        "are intentional."
    )


def test_h7_loopback_nbtp_register_value_is_pinned(tmp_path: Path):
    """A reader of `tests/golden/` should see the bit-timing claim at
    a glance. The exact NBTP value (and its field decomposition) is
    spelled out here so that a generator change which silently shifts
    the on-the-wire bit rate trips a test even before the byte-diff
    catches it.

    Reference: STM32CubeMX 6.x for FDCAN1 on STM32H753 at 80 MHz
    nominal-bit-time → BRP=10, TSEG1=13, TSEG2=2, SJW=1 = 500 kbit/s
    at 87.5 % sample point.
    """
    project = load_project(EXAMPLES / H7_EXAMPLE)
    can_h7.generate(project, tmp_path)
    body = (tmp_path / "Can_Cfg.c").read_text()
    assert ".nbtp = 0x00090C01u" in body
    assert "BRP=10, TSEG1=13, TSEG2=2, SJW=1" in body
    assert "500 kbit/s" in body
    assert "80 MHz" in body


def _refresh_expected(
    expected_root: Path, generated_files: dict[str, Path]
) -> None:
    """Refresh the on-disk snapshot tree to match what was just generated.

    Removes any stale files from a prior run so the snapshot directory
    always reflects exactly the current generation output.
    """
    if expected_root.is_dir():
        for p in expected_root.rglob("*"):
            if p.is_file():
                p.unlink()
    for rel, path in generated_files.items():
        target = expected_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(normalize_bytes(path.read_bytes()))
