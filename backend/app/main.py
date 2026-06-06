from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

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

log = logging.getLogger("openvinci.backend")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLES = REPO_ROOT / "examples"
SCHEMAS_DIR = REPO_ROOT / "model"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

# Conservative body-size ceiling. The two endpoints that take meaningful
# payloads are /api/generate (a JSON project — typical com-minimal is
# < 20 KB) and /api/import/dbc/upload (a .dbc — even the largest one we
# vendor, vehicle.dbc, is < 500 KB). 20 MB is roomy enough that the UI
# never trips it but tight enough that a hostile peer can't trivially
# OOM the process before we've added per-endpoint hardening.
MAX_BODY_BYTES_DEFAULT = 20 * 1024 * 1024

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


def _frontend_dist_dir() -> Path:
    return Path(os.environ.get("OPENVINCI_FRONTEND_DIST", FRONTEND_DIST))


def _max_body_bytes() -> int:
    raw = os.environ.get("OPENVINCI_MAX_BODY_BYTES")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return MAX_BODY_BYTES_DEFAULT


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds the cap.

    A first-line defence ahead of `/api/generate` (shells out to gcc) and
    `/api/import/dbc/upload` (loads the bytes into cantools). Pure
    front-door check — for chunked / unknown-size uploads we fall back
    to a streaming budget while consuming the body in the handler. The
    declared-length check still rejects the obvious abuse.
    """

    def __init__(self, app, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                n = int(cl)
            except ValueError:
                n = -1
            if n > self.max_bytes:
                return JSONResponse(
                    {
                        "detail": (
                            f"request body exceeds limit "
                            f"({n} > {self.max_bytes} bytes)"
                        )
                    },
                    status_code=413,
                )
        return await call_next(request)


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

    app.add_middleware(MaxBodySizeMiddleware, max_bytes=_max_body_bytes())

    # CORS only matters when the UI is served from a different origin —
    # i.e. the `npm run dev` flow on :5173 talking to :8000. Once we
    # ship a single-process build (make build / make run), the UI is
    # same-origin and this list is moot.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
            # Anchor relative paths at the bundle's examples parent so
            # the UI's "examples/dbc/foo.dbc" form (returned by
            # /api/dbcs) resolves identically in source mode AND in a
            # frozen PyInstaller bundle where REPO_ROOT is meaningless.
            dbc_path = _examples_dir().parent / dbc_path
        if not dbc_path.is_file():
            raise HTTPException(status_code=404, detail=f"dbc not found: {dbc}")
        project = import_dbc_file(
            dbc_path, network_name=network, me=me, baudrate=baudrate
        )
        report = validate(project)
        try:
            source = str(dbc_path.relative_to(_examples_dir().parent))
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
        """Bundled DBC files the UI can offer as import sources.

        Reads from the bundle's examples/dbc tree (or the source one,
        when running from the repo) so the desktop / PyInstaller flow
        finds the same files the hosted flow does.
        """
        examples = _examples_dir()
        root = examples / "dbc"
        files: list[str] = []
        if root.is_dir():
            for p in sorted(root.rglob("*.dbc")):
                # Paths shown to the UI stay relative to the examples
                # parent — same shape ("examples/dbc/foo.dbc") whether
                # we're in source or bundle mode.
                try:
                    rel = p.relative_to(examples.parent)
                except ValueError:
                    rel = p
                files.append(str(rel))
        return {"dbcs": files}

    # --- generate -----------------------------------------------------

    def _resolve_generate_inputs(
        project_query: str | None, body: GenerateRequest | None
    ) -> tuple[Project, Path | None, str]:
        """Shared input resolution for /api/generate and /api/generate/zip.

        Returns (project, source_dir, label). `source_dir` is None when the
        request is purely in-memory; otherwise it points at a named example
        so the stage step can pick up ancillary files (DBC, E2E.json, …).
        Same no-server-paths stance as /api/import/dbc — the label that
        comes back to the client is the project NAME, never an absolute
        path.
        """
        if body is not None and body.project is not None:
            proj = _project_from_request(body.project)
            source_dir = (
                _examples_dir() / body.sourceProject if body.sourceProject else None
            )
            label = body.sourceProject or "<in-memory>"
        elif project_query is not None:
            project_dir = _examples_dir() / project_query
            if not project_dir.is_dir():
                raise HTTPException(
                    status_code=404, detail=f"project not found: {project_query}"
                )
            try:
                proj = load_project(project_dir)
            except UnknownConfigClassError as e:
                raise HTTPException(status_code=400, detail=str(e))
            source_dir = project_dir
            label = project_query
        else:
            raise HTTPException(
                status_code=400,
                detail="provide ?project=<name> or a JSON body with `project`",
            )
        return proj, source_dir, label

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
        proj, source_dir, label = _resolve_generate_inputs(project, body)

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

    @app.post("/api/generate/zip")
    def api_generate_zip(
        project: str | None = Query(None, description="Named project on disk"),
        body: GenerateRequest | None = Body(None),
    ) -> StreamingResponse:
        """Same stage+generate as /api/generate, returned as a STORED .zip.

        STORED (no compression) so a tiny in-browser unzipper can decode
        the entries for the optional "Save to folder" path in the UI —
        the host-sim outputs are KB-scale C/H files that don't benefit
        from DEFLATE anyway. The arcnames mirror the same project-
        relative paths the JSON `files` field would carry, so the zip is
        a verbatim view of what /api/generate already returned.

        No server filesystem paths cross the wire; the only label the
        response carries is the project NAME (or "in-memory") embedded
        in the Content-Disposition filename.
        """
        proj, source_dir, label = _resolve_generate_inputs(project, body)

        workdir = Path(tempfile.mkdtemp(prefix="openvinci-gen-"))
        buf = io.BytesIO()
        try:
            result = generate_and_compile(proj, workdir, source_dir=source_dir)
            if not result.files:
                # Generation failed silently — surface that rather than
                # streaming a zero-entry zip the user would have to
                # debug. The browser flow hides the Download button in
                # this case, but a direct API caller deserves a real
                # response.
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "generation produced no files; check /api/generate "
                        "for diagnostics"
                    ),
                )
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
                for f in result.files:
                    src = workdir / f.path
                    if not src.is_file():
                        continue
                    zf.write(src, arcname=f.path)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        buf.seek(0)
        safe_label = re.sub(r"[^A-Za-z0-9._-]", "_", label) or "project"
        filename = f"openvinci-{safe_label}.zip"
        # Content-Length is omitted on purpose so the StreamingResponse
        # writer doesn't have to know the size up front; for KB-scale
        # zips the browser handles the streamed download fine.
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "content-disposition": f'attachment; filename="{filename}"',
                "x-openvinci-label": safe_label,
            },
        )

    # --- SPA serve (must register last) -------------------------------
    #
    # When `frontend/dist/` exists (i.e. after `make build`), serve the
    # SPA from the same process:
    #
    #   GET /             → dist/index.html
    #   GET /assets/foo  → dist/assets/foo
    #   GET /favicon.ico → dist/favicon.ico if present, else 404
    #   GET /<refresh>   → dist/index.html (so refresh on a deep route
    #                     hands the SPA back its own router)
    #   GET /api/junk    → 404 (don't mask unknown API misses as HTML)
    #
    # If dist/ is missing (e.g. running uvicorn before `make build`),
    # the catch-all returns a friendly 503. The dev flow (`make dev`)
    # remains unaffected because Vite serves the UI on :5173.

    @app.get("/{full_path:path}")
    async def spa_catch_all(full_path: str):
        # Don't hide unknown API/schema/health misses behind index.html;
        # those are real 404s the caller deserves to see.
        for reserved in ("api/", "schemas/", "schemas", "health"):
            if full_path == reserved.rstrip("/") or full_path.startswith(reserved):
                raise HTTPException(
                    status_code=404, detail=f"unknown route: /{full_path}"
                )

        dist_dir = _frontend_dist_dir()
        if not dist_dir.is_dir():
            return JSONResponse(
                {
                    "detail": (
                        "frontend build missing. Run `make build` (or "
                        "`make dev` to serve via Vite on :5173)."
                    )
                },
                status_code=503,
            )

        # Try to serve a real file from dist; fall back to index.html so
        # client-side routing survives a refresh.
        target = (dist_dir / full_path).resolve() if full_path else dist_dir
        dist_resolved = dist_dir.resolve()
        if full_path and target.is_file() and _is_under(target, dist_resolved):
            return FileResponse(target)

        index = dist_dir / "index.html"
        if not index.is_file():
            return JSONResponse(
                {"detail": "frontend dist/index.html missing"},
                status_code=503,
            )
        return FileResponse(index)

    return app


def _is_under(path: Path, root: Path) -> bool:
    """True iff `path` is inside `root`, after symlink resolution.

    Plain `path.is_relative_to` would do, but we want belt-and-braces
    safety against `..` segments before resolution: both are passed
    through Path.resolve() by the caller.
    """
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


app = create_app()
