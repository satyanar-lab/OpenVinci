"""VERIFICATION LEVEL 3 — golden-file regression.

Regenerate every example project, strip timestamps, and assert the
output is byte-identical to a checked-in snapshot. Any unintended
diff fails the test; intentional changes are re-baselined with
`pytest tests/golden --update-golden`.

This is the test that protects against silent drift in the generator
chain when `vendor/as` moves, when the model layer's serialization
changes, or when a code-gen template gets a subtle edit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make backend importable without installing it (the CI/verify path
# may not pip-install before running this test).
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engine import load_project  # noqa: E402
from gen import generate_and_compile  # noqa: E402

from .normalize import normalize_bytes  # noqa: E402

EXAMPLES = REPO_ROOT / "examples"
GOLDEN = Path(__file__).parent

# Examples we snapshot. com-minimal is the L1 / L3 fixture — generation
# clean, compile clean. canfd-minimal is its CAN-FD sister (dlc=16,
# fd:true, UINT8N 16-byte signals) and gets the same byte-stable
# generator guarantee. canapp-min has DBC/E2E ancillaries that don't
# generate without the full vendor/as project tree, so skip it here.
SNAPSHOT_EXAMPLES = ["com-minimal", "canfd-minimal"]


@pytest.mark.parametrize("name", SNAPSHOT_EXAMPLES)
def test_golden_snapshot_matches(name: str, tmp_path: Path, request):
    update = request.config.getoption("--update-golden")
    expected_root = GOLDEN / name / "expected"

    project = load_project(EXAMPLES / name)
    result = generate_and_compile(project, tmp_path, source_dir=EXAMPLES / name)
    assert result.compile_result is not None
    assert result.compile_result.status == "ok", (
        "regenerated output failed the L1 compile check:\n"
        + "\n".join(
            f"  {m.severity}: {m.file}:{m.line} {m.message}"
            for m in result.compile_result.messages
        )
    )

    generated_files = {
        f.path: (tmp_path / f.path) for f in result.files if Path(f.path).suffix in {".c", ".h", ".json", ".py"}
    }

    if update:
        _refresh_expected(expected_root, generated_files)
        pytest.skip(f"updated {len(generated_files)} snapshots under {expected_root}")

    if not expected_root.is_dir():
        pytest.fail(
            f"no golden snapshots under {expected_root} — run with --update-golden "
            f"after the first generation to create them."
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
        "content drift in:\n  " + "\n  ".join(diffs)
        + "\nRun pytest with --update-golden after verifying the changes are intentional."
    )


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
