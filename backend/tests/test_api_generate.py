"""/api/generate + /api/generate/zip HTTP endpoint — integration tests."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_generate_returns_files_and_compile_status_on_com_minimal():
    response = client.post("/api/generate", params={"project": "com-minimal"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"] == "com-minimal"
    assert isinstance(body["files"], list)
    assert any(f["path"].endswith("Com_Cfg.c") for f in body["files"])
    assert any(f["path"].endswith("CanIf_Cfg.c") for f in body["files"])
    assert any(f["path"].endswith("PduR_Cfg.c") for f in body["files"])
    assert body["compileResult"]["status"] == "ok", body["compileResult"][
        "messages"
    ]


def test_generate_404s_unknown_project():
    response = client.post("/api/generate", params={"project": "does-not-exist"})
    assert response.status_code == 404


# --- /api/generate/zip ------------------------------------------------


def test_generate_zip_streams_a_real_zip_for_named_project():
    response = client.post(
        "/api/generate/zip", params={"project": "com-minimal"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    cd = response.headers["content-disposition"]
    # Filename mirrors the project label so a saved download is
    # immediately recognisable.
    assert "openvinci-com-minimal.zip" in cd

    # Real, parseable zip. Mirror the L1 expected outputs we already
    # assert on /api/generate.
    z = zipfile.ZipFile(io.BytesIO(response.content))
    names = z.namelist()
    assert any(n.endswith("Com_Cfg.c") for n in names), names
    assert any(n.endswith("CanIf_Cfg.c") for n in names), names
    assert any(n.endswith("PduR_Cfg.c") for n in names), names

    # Arcnames are project-relative paths — no absolute server paths
    # leak through (matches the no-server-paths stance the rest of the
    # API takes; see /api/import/dbc).
    for n in names:
        assert not n.startswith("/"), n
        assert "/tmp" not in n, n
        assert "openvinci-gen-" not in n, n


def test_generate_zip_entries_are_stored_so_in_browser_unzip_works():
    """The frontend "Save to folder" path has a tiny inline STORED-only
    unzipper. Guard the encoding so a future change to ZIP_DEFLATED
    doesn't silently break that path."""
    response = client.post(
        "/api/generate/zip", params={"project": "com-minimal"}
    )
    assert response.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(response.content))
    for info in z.infolist():
        assert info.compress_type == zipfile.ZIP_STORED, (
            info.filename,
            info.compress_type,
        )


def test_generate_zip_404s_unknown_project():
    response = client.post(
        "/api/generate/zip", params={"project": "does-not-exist"}
    )
    assert response.status_code == 404


def test_generate_zip_400s_when_neither_query_nor_body_provided():
    response = client.post("/api/generate/zip")
    assert response.status_code == 400
    assert "project" in response.json()["detail"]
