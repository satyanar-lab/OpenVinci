from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.model import SUPPORTED_CLASSES, UnknownConfigClassError, dump, load
from engine import (
    Project,
    Fix,
    apply_fix,
    load_project,
    project_from_raw,
    validate,
)
from gen import generate_and_compile
from importer import import_dbc_file

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLES = REPO_ROOT / "examples"
SCHEMAS_DIR = REPO_ROOT / "model"

# class -> on-disk path inside a project. Matches what vendor/as expects
# (docs/AUTOAS_NOTES.md §1.1).
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


def _project_to_raw(project: Project) -> dict[str, dict[str, Any]]:
    return project.raw


def _issues_to_json(report) -> list[dict[str, Any]]:
    return [
        {
            "rule": i.rule,
            "severity": i.severity.value,
            "message": i.message,
            "module": i.location.module,
            "path": list(i.location.path),
            "fix": (
                {"description": i.fix.description, "patches": i.fix.patches}
                if i.fix
                else None
            ),
        }
        for i in report.issues
    ]


def _project_from_request(raw: dict[str, dict[str, Any]] | None) -> Project:
    try:
        return project_from_raw(raw or {})
    except UnknownConfigClassError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid project: {e}")


class ProjectRequest(BaseModel):
    project: dict[str, dict[str, Any]]


class ApplyFixRequest(BaseModel):
    project: dict[str, dict[str, Any]]
    fix: dict[str, Any]


class GenerateRequest(BaseModel):
    project: dict[str, dict[str, Any]] | None = None
    sourceProject: str | None = None


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

    # --- schemas -----------------------------------------------------

    @app.get("/schemas")
    def list_schemas() -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cls, filename in SCHEMA_FILES.items():
            path = _schemas_dir() / filename
            if not path.is_file():
                raise HTTPException(status_code=500, detail=f"schema missing: {path}")
            out[cls] = json.loads(path.read_text())
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
        return json.loads((_schemas_dir() / SCHEMA_FILES[cls]).read_text())

    # --- projects (file-backed examples) -----------------------------

    @app.get("/api/projects")
    def list_projects() -> dict[str, Any]:
        root = _examples_dir()
        projects: list[str] = []
        if root.is_dir():
            for entry in sorted(root.iterdir()):
                # an OpenVinci project = a dir with at least one recognised module JSON
                if entry.is_dir() and any(
                    (entry / rel).is_file() for rel in CONFIG_LAYOUT.values()
                ):
                    projects.append(entry.name)
        return {"projects": projects}

    @app.get("/api/projects/{name}")
    def get_project(name: str) -> dict[str, Any]:
        project_dir = _examples_dir() / name
        if not project_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"project not found: {name}")
        try:
            project = load_project(project_dir)
        except UnknownConfigClassError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"name": name, "project": _project_to_raw(project)}

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

    # --- validate + apply-fix -----------------------------------------

    @app.post("/api/validate")
    def api_validate(body: ProjectRequest) -> dict[str, Any]:
        project = _project_from_request(body.project)
        report = validate(project)
        return {
            "ok": report.ok,
            "errorCount": len(report.errors),
            "warningCount": len(report.warnings),
            "issues": _issues_to_json(report),
        }

    @app.post("/api/apply-fix")
    def api_apply_fix(body: ApplyFixRequest) -> dict[str, Any]:
        project = _project_from_request(body.project)
        try:
            fix = Fix(
                description=body.fix.get("description", ""),
                patches=body.fix.get("patches", {}),
            )
            updated = apply_fix(project, fix)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        report = validate(updated)
        return {
            "project": _project_to_raw(updated),
            "validation": {
                "ok": report.ok,
                "errorCount": len(report.errors),
                "warningCount": len(report.warnings),
                "issues": _issues_to_json(report),
            },
        }

    # --- DBC import ---------------------------------------------------

    @app.post("/api/import/dbc")
    def api_import_dbc(
        dbc: str = Query(..., description="Path to a .dbc file (repo-relative OK)."),
        network: str = Query("CAN0"),
        me: str = Query("AS"),
        baudrate: int = Query(500000, ge=1),
    ) -> dict[str, Any]:
        dbc_path = Path(dbc)
        if not dbc_path.is_absolute():
            dbc_path = REPO_ROOT / dbc_path
        if not dbc_path.is_file():
            raise HTTPException(status_code=404, detail=f"dbc not found: {dbc}")
        project = import_dbc_file(
            dbc_path, network_name=network, me=me, baudrate=baudrate
        )
        report = validate(project)
        try:
            source = str(dbc_path.relative_to(REPO_ROOT))
        except ValueError:
            source = str(dbc_path)
        return {
            "source": source,
            "network": network,
            "me": me,
            "project": _project_to_raw(project),
            "validation": {
                "ok": report.ok,
                "errorCount": len(report.errors),
                "warningCount": len(report.warnings),
                "issues": _issues_to_json(report),
            },
        }

    @app.post("/api/import/dbc/upload")
    async def api_import_dbc_upload(
        file: UploadFile = File(..., description="A user-supplied .dbc file"),
        network: str = Query("CAN0"),
        me: str = Query("AS"),
        baudrate: int = Query(500000, ge=1),
    ) -> dict[str, Any]:
        """Same contract as `/api/import/dbc` but reads the DBC bytes from
        the request body — lets the UI accept files the user drops/picks
        from their local filesystem without exposing arbitrary server paths."""
        if not file.filename or not file.filename.lower().endswith(".dbc"):
            raise HTTPException(
                status_code=400,
                detail="upload must be a .dbc file (got "
                f"{file.filename!r})",
            )
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty upload")

        # cantools loads from a path, so persist to a tempfile briefly.
        # Cleaned up regardless of how the parse / wire pass goes.
        tmp = tempfile.NamedTemporaryFile(
            prefix="openvinci-dbc-", suffix=".dbc", delete=False
        )
        tmp_path = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.close()
            try:
                project = import_dbc_file(
                    tmp_path, network_name=network, me=me, baudrate=baudrate
                )
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"DBC parse failed: {e}")
            report = validate(project)
            return {
                "source": file.filename,
                "network": network,
                "me": me,
                "project": _project_to_raw(project),
                "validation": {
                    "ok": report.ok,
                    "errorCount": len(report.errors),
                    "warningCount": len(report.warnings),
                    "issues": _issues_to_json(report),
                },
            }
        finally:
            tmp_path.unlink(missing_ok=True)

    @app.get("/api/dbcs")
    def list_dbcs() -> dict[str, Any]:
        """Bundled DBC files the UI can offer as import sources."""
        root = REPO_ROOT / "examples" / "dbc"
        files: list[str] = []
        if root.is_dir():
            for p in sorted(root.rglob("*.dbc")):
                files.append(str(p.relative_to(REPO_ROOT)))
        return {"dbcs": files}

    # --- generate -----------------------------------------------------

    @app.post("/api/generate")
    def api_generate(
        project: str | None = Query(None, description="Named project on disk"),
        body: GenerateRequest | None = Body(None),
    ) -> dict[str, Any]:
        """Stage, generate, gcc-compile.

        Two call shapes:
        - `?project=NAME` — load NAME from /examples and generate (back-compat).
        - JSON body `{project: {...}, sourceProject?: "name"}` — generate from
          the UI's in-memory state; sourceProject lets the staging step pull
          in ancillary files (DBC, E2E.json, …) from a known on-disk project.
        """
        if body is not None and body.project is not None:
            proj = _project_from_request(body.project)
            source_dir = (
                _examples_dir() / body.sourceProject if body.sourceProject else None
            )
            label = body.sourceProject or "<in-memory>"
        elif project is not None:
            project_dir = _examples_dir() / project
            if not project_dir.is_dir():
                raise HTTPException(
                    status_code=404, detail=f"project not found: {project}"
                )
            try:
                proj = load_project(project_dir)
            except UnknownConfigClassError as e:
                raise HTTPException(status_code=400, detail=str(e))
            source_dir = project_dir
            label = project
        else:
            raise HTTPException(
                status_code=400,
                detail="provide ?project=<name> or a JSON body with `project`",
            )

        workdir = Path(tempfile.mkdtemp(prefix="openvinci-gen-"))
        try:
            result = generate_and_compile(proj, workdir, source_dir=source_dir)
            return {
                "project": label,
                "files": [asdict(f) for f in result.files],
                "compileResult": asdict(result.compile_result)
                if result.compile_result
                else None,
            }
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    return app


app = create_app()
