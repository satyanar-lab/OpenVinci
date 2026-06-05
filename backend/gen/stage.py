"""Stage a Project to disk in the layout vendor/as expects.

Modeled modules are serialized through the model layer (so the round-trip
contract is exercised on every generate call). Ancillary files the engine
doesn't model (`*.dbc`, `E2E/E2E.json`, etc.) are copied verbatim from a
source directory so generation can still resolve them.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.model import dump
from engine.project import CLASS_TO_PATH, Project


def stage_project(
    project: Project,
    dest: Path,
    *,
    source_dir: Path | None = None,
) -> None:
    """Write the project into `dest` and pull ancillary files if given.

    `dest` should be empty or non-existent — we don't clean up after
    ourselves here; the caller owns the workdir lifecycle.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    written: set[Path] = set()
    for cls in ("Can", "Com", "CanIf", "CanTp", "PduR"):
        model = _model_for(project, cls)
        if model is None:
            continue
        path = dest / CLASS_TO_PATH[cls]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dump(model), indent=2) + "\n")
        written.add(path.resolve())

    if source_dir is None:
        return

    source_dir = Path(source_dir)
    for src in source_dir.rglob("*"):
        if not src.is_file():
            continue
        # Skip already-generated trees in the source (just in case).
        if "GEN" in src.parts:
            continue
        rel = src.relative_to(source_dir)
        target = (dest / rel).resolve()
        if target in written:
            continue  # model-serialized version wins
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(src, target)


def _model_for(project: Project, cls: str):
    return {
        "Can": project.can,
        "Com": project.com,
        "CanIf": project.canif,
        "CanTp": project.cantp,
        "PduR": project.pdur,
    }[cls]
