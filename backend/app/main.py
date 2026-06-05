from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLES = REPO_ROOT / "examples"

# The class -> on-disk path layout matches what vendor/as expects
# (docs/AUTOAS_NOTES.md §1.1). Hardcoded for the scaffold; Layer 2 will
# discover this from the project tree.
CONFIG_LAYOUT: dict[str, str] = {
    "Com": "config/Com/Com.json",
    "CanIf": "config/Com/CanIf.json",
    "PduR": "config/Com/PduR.json",
    "CanTp": "config/CanTp/CanTp.json",
}


def _examples_dir() -> Path:
    return Path(os.environ.get("OPENVINCI_EXAMPLES_DIR", DEFAULT_EXAMPLES))


def create_app() -> FastAPI:
    app = FastAPI(title="OpenVinci backend", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def get_config(
        project: str = Query("canapp-min"),
        module: str = Query("Com"),
    ) -> dict[str, Any]:
        if module not in CONFIG_LAYOUT:
            raise HTTPException(
                status_code=400,
                detail=f"unknown module {module!r}; known: {sorted(CONFIG_LAYOUT)}",
            )
        path = _examples_dir() / project / CONFIG_LAYOUT[module]
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"config not found: {path}")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"invalid JSON in {path}: {e}")
        return {
            "project": project,
            "module": module,
            "source": str(path.relative_to(REPO_ROOT)),
            "data": data,
        }

    return app


app = create_app()
