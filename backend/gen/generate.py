"""Invoke vendor/as's code generators in-process.

We import `generator` from `vendor/as/tools/` (per docs/AUTOAS_NOTES.md
§2.1) and call `Generate(cfgs, force=True)` over the modules upstream
recognises. Outputs land in `<cfg>/GEN/` next to each input JSON.

`generator.RootDir` is monkeypatched so the `.gendb.pkl` cache lands
inside our workdir, not in `vendor/as/` (treating the submodule as
strictly read-only — see CLAUDE.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

from engine.project import CLASS_TO_PATH

# Classes vendor/as has a generator for. `Can` is in CLASS_TO_PATH but
# has no upstream generator — its config is the hand-written
# Can_Cfg.c in app/platform/simulator/src/config/. We just skip it
# here; the existing C file works fine for compile checks.
GENERATABLE_CLASSES: tuple[str, ...] = ("Com", "CanIf", "PduR", "CanTp")

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_AS_TOOLS = REPO_ROOT / "vendor" / "as" / "tools"


def run_generators(staged_dir: Path) -> list[Path]:
    """Run every applicable generator. Returns the list of files written."""
    staged_dir = Path(staged_dir)
    cfgs: list[str] = []
    for cls in GENERATABLE_CLASSES:
        path = staged_dir / CLASS_TO_PATH[cls]
        if path.is_file():
            cfgs.append(str(path))
    if not cfgs:
        return []

    # Snapshot what's already on disk so we can diff to discover outputs.
    before = set(staged_dir.rglob("*"))

    _ensure_vendor_tools_on_path()
    import generator  # type: ignore[import-not-found]

    saved_root = generator.RootDir
    generator.RootDir = str(staged_dir)
    try:
        generator.Generate(cfgs, force=True)
    finally:
        generator.RootDir = saved_root

    after = set(staged_dir.rglob("*"))
    new = sorted(
        p
        for p in (after - before)
        if p.is_file() and "GEN" in p.parts
        # ^ filters out the .gendb.pkl cache Generate() writes at staged_dir
    )
    return new


def _ensure_vendor_tools_on_path() -> None:
    tools = str(VENDOR_AS_TOOLS)
    if tools not in sys.path:
        sys.path.insert(0, tools)
