"""SPA serve + body-size guard contracts.

When the frontend has been built (`make build` ⇒ `frontend/dist/`),
the same uvicorn process should hand out index.html on `/`, real
static files under their normal paths, and index.html as a catch-all
for client-side routes so a refresh on a deep route doesn't 404.
Unknown `/api/...` paths must still 404 — we don't want a typo in an
API call to silently return HTML.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


def _build_app_with_dist(tmp_path, monkeypatch, *, write_index: bool):
    """Reimport app.main with OPENVINCI_FRONTEND_DIST pointed at a
    scratch dir so the tests don't depend on a real `npm run build`."""
    dist = tmp_path / "dist"
    dist.mkdir()
    if write_index:
        (dist / "index.html").write_text(
            "<!doctype html>\n<html><body data-test='spa'></body></html>\n"
        )
        (dist / "assets").mkdir()
        (dist / "assets" / "app.js").write_text("// vite-bundled\n")
        (dist / "favicon.ico").write_bytes(b"\x00\x00")
    monkeypatch.setenv("OPENVINCI_FRONTEND_DIST", str(dist))
    # Reload so create_app() picks up the env var in case the module
    # was imported earlier in the test session.
    import app.main as main_mod  # noqa: WPS433

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


@pytest.fixture
def client_with_dist(tmp_path, monkeypatch):
    yield _build_app_with_dist(tmp_path, monkeypatch, write_index=True)


@pytest.fixture
def client_without_dist(tmp_path, monkeypatch):
    # Point at a directory that doesn't exist so the SPA branch falls
    # to the friendly 503.
    missing = tmp_path / "no-dist"
    monkeypatch.setenv("OPENVINCI_FRONTEND_DIST", str(missing))
    import app.main as main_mod  # noqa: WPS433

    importlib.reload(main_mod)
    yield TestClient(main_mod.app)


# --- catch-all SPA serve ---------------------------------------------


def test_root_returns_index_html(client_with_dist):
    r = client_with_dist.get("/")
    assert r.status_code == 200
    assert "data-test='spa'" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_deep_route_falls_back_to_index_for_spa_refresh(client_with_dist):
    # A client-side route like /projects/foo isn't on the server, but a
    # browser refresh hits it; we want the SPA shell back so the React
    # router can take over.
    r = client_with_dist.get("/projects/foo/bar")
    assert r.status_code == 200
    assert "data-test='spa'" in r.text


def test_real_static_file_served_verbatim(client_with_dist):
    r = client_with_dist.get("/assets/app.js")
    assert r.status_code == 200
    assert "vite-bundled" in r.text


def test_favicon_served_when_present(client_with_dist):
    r = client_with_dist.get("/favicon.ico")
    assert r.status_code == 200


def test_unknown_api_path_404s_instead_of_spa_html(client_with_dist):
    # If /api/whatever isn't a real route, returning index.html would
    # mask a typo with an HTML payload. Must stay a 404.
    r = client_with_dist.get("/api/nope")
    assert r.status_code == 404


def test_unknown_schema_path_also_404s(client_with_dist):
    r = client_with_dist.get("/schemas/Bogus/Extra")
    assert r.status_code == 404


def test_existing_api_route_still_works_with_dist_mounted(client_with_dist):
    # Regression guard: registering the catch-all must NOT shadow the
    # earlier-registered /health or /api/projects.
    assert client_with_dist.get("/health").status_code == 200
    assert client_with_dist.get("/api/projects").status_code == 200


def test_missing_dist_returns_friendly_503(client_without_dist):
    r = client_without_dist.get("/")
    assert r.status_code == 503
    assert "frontend build missing" in r.json()["detail"]
    # API still works regardless of dist state.
    assert client_without_dist.get("/health").status_code == 200


def test_path_traversal_blocked(client_with_dist):
    # ../etc/passwd would escape dist if we didn't resolve+check.
    r = client_with_dist.get("/../../etc/passwd")
    # Either the URL is rewritten by the client (so we never see it)
    # OR the catch-all serves index.html as the safe default. Either
    # way, no /etc/passwd content.
    assert r.status_code == 200
    assert "root:" not in r.text


# --- max body size ----------------------------------------------------


def test_oversize_request_rejected_with_413(client_with_dist):
    # Synthesize a request larger than the (default 20 MB) cap by
    # overriding the env, then sending a body just over the new limit.
    os.environ["OPENVINCI_MAX_BODY_BYTES"] = "1024"
    try:
        import app.main as main_mod  # noqa: WPS433

        importlib.reload(main_mod)
        small_cap_client = TestClient(main_mod.app)
        payload = '{"project": {"x": "' + ("a" * 2000) + '"}}'
        r = small_cap_client.post(
            "/api/validate",
            content=payload,
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 413
        assert "exceeds limit" in r.json()["detail"]
    finally:
        del os.environ["OPENVINCI_MAX_BODY_BYTES"]
        # Restore the default for any later imports.
        import app.main as main_mod  # noqa: WPS433

        importlib.reload(main_mod)
