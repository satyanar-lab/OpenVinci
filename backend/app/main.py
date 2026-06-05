from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.model import SUPPORTED_CLASSES, UnknownConfigClassError, dump, load

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLES = REPO_ROOT / "examples"
SCHEMAS_DIR = REPO_ROOT / "model"

# class -> on-disk path inside a project. Matches what vendor/as expects
# (docs/AUTOAS_NOTES.md §1.1). Hardcoded for now; Layer 2 will discover
# this from the project tree.
CONFIG_LAYOUT: dict[str, str] = {
    "Can": "config/Can/Can.json",
    "Com": "config/Com/Com.json",
    "CanIf": "config/Com/CanIf.json",
    "PduR": "config/Com/PduR.json",
    "CanTp": "config/CanTp/CanTp.json",
}

# class -> filename inside /model that the frontend should fetch.
SCHEMA_FILES: dict[str, str] = {
    "Can": "can.schema.json",
    "CanIf": "canif.schema.json",
    "CanTp": "cantp.schema.json",
    "PduR": "pdur.schema.json",
    "Com": "com.schema.json",
}


def _examples_dir() -> Path:
    return Path(os.environ.get("OPENVINCI_EXAMPLES_DIR", DEFAULT_EXAMPLES))


def _schemas_dir() -> Path:
    return Path(os.environ.get("OPENVINCI_SCHEMAS_DIR", SCHEMAS_DIR))


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
        # Round-trip the dict through the model layer so the API serves
        # only validated, typed data. Unknown extras still pass through
        # via extra="allow" (see app/model/common.py).
        try:
            model = load(data)
        except UnknownConfigClassError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {
            "project": project,
            "module": module,
            "source": str(path.relative_to(REPO_ROOT)),
            "data": dump(model),
        }

    @app.get("/schemas")
    def list_schemas() -> dict[str, Any]:
        """Bundle of Layer-1 JSON Schemas, keyed by class.

        The frontend fetches these at runtime (docs/ARCHITECTURE.md
        §"Layer 4") rather than bundling them into the JS, so a schema
        edit reaches the UI without a rebuild.
        """
        out: dict[str, Any] = {}
        for cls, filename in SCHEMA_FILES.items():
            path = _schemas_dir() / filename
            if not path.is_file():
                raise HTTPException(status_code=500, detail=f"schema missing: {path}")
            out[cls] = json.loads(path.read_text())
        # Sanity: backend's supported classes must match the schema set.
        assert set(SCHEMA_FILES) == set(SUPPORTED_CLASSES), (
            "schema dispatch and model dispatch are out of sync"
        )
        return out

    @app.get("/schemas/{cls}")
    def get_schema(cls: str) -> dict[str, Any]:
        if cls not in SCHEMA_FILES:
            raise HTTPException(
                status_code=404,
                detail=f"unknown class {cls!r}; known: {sorted(SCHEMA_FILES)}",
            )
        path = _schemas_dir() / SCHEMA_FILES[cls]
        return json.loads(path.read_text())

    return app


app = create_app()
