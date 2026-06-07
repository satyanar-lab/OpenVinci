#!/usr/bin/env python3
"""Regenerate examples/com-minimal's *_Cfg.{h,c} into
hardware/stm32h753zi/generated/.

This is the same generator OpenVinci's web/desktop app calls
(backend/gen/generate.run_generators against a staged project tree).
We just discard the compile step and copy the produced .c/.h verbatim
into the firmware tree so the cross-build pulls in identical bytes.

Run via `make generate` from hardware/stm32h753zi/ or directly:

    python3 hardware/stm32h753zi/tools/regenerate.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARDWARE_DIR = HERE.parent
REPO_ROOT = HARDWARE_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
EXAMPLE = REPO_ROOT / "examples" / "com-minimal"
GENERATED = HARDWARE_DIR / "generated"

# Allow imports from the backend package without installing it.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine import load_project  # noqa: E402
from gen.generate import run_generators  # noqa: E402
from gen.stage import stage_project  # noqa: E402


def main() -> int:
    if not EXAMPLE.is_dir():
        print(f"examples/com-minimal not found at {EXAMPLE}", file=sys.stderr)
        return 2

    GENERATED.mkdir(parents=True, exist_ok=True)
    # Wipe stale outputs so a previously-generated file we no longer
    # need can't sneak into the firmware build.
    for stale in GENERATED.glob("*"):
        if stale.is_file():
            stale.unlink()

    project = load_project(EXAMPLE)

    with tempfile.TemporaryDirectory(prefix="openvinci-h7-gen-") as raw_workdir:
        workdir = Path(raw_workdir)
        stage_project(project, workdir, source_dir=EXAMPLE)
        written = run_generators(workdir)

        copied: list[str] = []
        for src in written:
            if src.suffix in {".c", ".h"}:
                dst = GENERATED / src.name
                shutil.copyfile(src, dst)
                copied.append(src.name)

    if not copied:
        print(
            "generator produced no .c/.h files — check examples/com-minimal "
            "is still a valid project.",
            file=sys.stderr,
        )
        return 1

    print(f"wrote {len(copied)} file(s) to {GENERATED}:")
    for name in sorted(copied):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
