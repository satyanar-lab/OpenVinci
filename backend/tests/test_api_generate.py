"""/api/generate HTTP endpoint — integration test."""

from __future__ import annotations

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
