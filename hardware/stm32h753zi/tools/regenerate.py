#!/usr/bin/env python3
"""Regenerate examples/h7-loopback's *_Cfg.{h,c} into
hardware/stm32h753zi/generated/.

This is the same generator OpenVinci's web/desktop app calls
(backend/gen/generate.run_generators against a staged project tree).
We just discard the compile step and copy the produced .c/.h verbatim
into the firmware tree so the cross-build pulls in identical bytes.

The default example is `h7-loopback` because the firmware in this
directory runs FDCAN1 in internal-loopback mode and needs an Rx PDU
that matches the Tx canid — see examples/h7-loopback/README.md.

Run via `make generate` from hardware/stm32h753zi/ or directly:

    python3 hardware/stm32h753zi/tools/regenerate.py
    python3 hardware/stm32h753zi/tools/regenerate.py com-minimal
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARDWARE_DIR = HERE.parent
REPO_ROOT = HARDWARE_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
EXAMPLES_DIR = REPO_ROOT / "examples"
GENERATED = HARDWARE_DIR / "generated"
DEFAULT_EXAMPLE = "h7-loopback"

# Allow imports from the backend package without installing it.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine import load_project  # noqa: E402
from gen import can_h7, ecu_glue  # noqa: E402
from gen.generate import run_generators  # noqa: E402
from gen.stage import stage_project  # noqa: E402


def main() -> int:
    example_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXAMPLE
    example_dir = EXAMPLES_DIR / example_name
    if not example_dir.is_dir():
        print(
            f"examples/{example_name} not found at {example_dir}",
            file=sys.stderr,
        )
        return 2

    GENERATED.mkdir(parents=True, exist_ok=True)
    # Wipe stale outputs so a previously-generated file we no longer
    # need can't sneak into the firmware build.
    for stale in GENERATED.glob("*"):
        if stale.is_file():
            stale.unlink()

    project = load_project(example_dir)

    with tempfile.TemporaryDirectory(prefix="openvinci-h7-gen-") as raw_workdir:
        workdir = Path(raw_workdir)
        stage_project(project, workdir, source_dir=example_dir)
        written = run_generators(workdir)

        copied: list[str] = []
        for src in written:
            if src.suffix in {".c", ".h"}:
                dst = GENERATED / src.name
                # The vendor generator stamps a `* Generated at <ctime>` line
                # into every output. We strip it so re-running `make generate`
                # produces a clean (empty) git diff when the inputs haven't
                # changed — otherwise the committed generated/ would churn on
                # every regeneration and obscure real config changes.
                text = src.read_text()
                text = re.sub(
                    r"^\s*\*\s*Generated at .*\r?\n",
                    "",
                    text,
                    count=1,
                    flags=re.MULTILINE,
                )
                dst.write_text(text)
                copied.append(src.name)

    if not copied:
        print(
            f"generator produced no .c/.h files — check examples/{example_name} "
            "is still a valid project.",
            file=sys.stderr,
        )
        return 1

    # Run the OpenVinci STM32H7 FDCAN driver-config generator (PROMPT
    # C2). Only fires when the project opts in via project.json's
    # target field. Output lands next to the vendor *_Cfg.* files so
    # the Makefile's $(wildcard generated/*.c) picks it up too.
    if can_h7.is_h7_target(example_dir):
        h7_written = can_h7.generate(project, GENERATED)
        copied.extend(p.name for p in h7_written)

        # PROMPT C3: also emit the integration glue (EcuM startup +
        # SysTick scheduler + App seam + a "REPLACE ME" demo). Same
        # opt-in gate — host-only projects keep their hand-written
        # main and never see these files.
        glue_written = ecu_glue.generate(project, GENERATED)
        copied.extend(p.name for p in glue_written)

    print(f"wrote {len(copied)} file(s) from examples/{example_name} to {GENERATED}:")
    for name in sorted(copied):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
