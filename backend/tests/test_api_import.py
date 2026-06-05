"""POST /api/import/dbc — HTTP integration."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]

client = TestClient(app)


def test_import_returns_project_and_validation():
    response = client.post(
        "/api/import/dbc",
        params={"dbc": "examples/dbc/sample.dbc", "network": "CAN0", "me": "AS"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["network"] == "CAN0"
    assert body["me"] == "AS"
    assert set(body["project"]) == {"Com", "CanIf", "PduR", "Can"}
    assert body["validation"]["ok"] is True
    assert body["validation"]["errorCount"] == 0


def test_import_uses_query_me_to_determine_direction():
    response = client.post(
        "/api/import/dbc",
        params={"dbc": "examples/dbc/sample.dbc", "network": "CAN0", "me": "AS"},
    )
    tx_names = [
        p["name"]
        for n in response.json()["project"]["CanIf"]["networks"]
        for p in n["TxPdus"]
    ]
    assert "CAN0_STATUS_TX" in tx_names


def test_import_404s_on_missing_dbc():
    response = client.post(
        "/api/import/dbc", params={"dbc": "examples/dbc/nope.dbc"}
    )
    assert response.status_code == 404
