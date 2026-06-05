"""Project listing, validate, apply-fix, generate-from-body."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]

client = TestClient(app)


# ----- /api/projects -------------------------------------------------


def test_list_projects_includes_known_examples():
    response = client.get("/api/projects")
    assert response.status_code == 200
    names = response.json()["projects"]
    assert "com-minimal" in names
    assert "canapp-min" in names


def test_get_project_returns_all_modeled_modules_for_com_minimal():
    response = client.get("/api/projects/com-minimal")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "com-minimal"
    project = body["project"]
    assert set(project) >= {"Com", "CanIf", "PduR"}
    assert project["Com"]["class"] == "Com"


def test_get_project_404_on_missing():
    assert client.get("/api/projects/nope").status_code == 404


# ----- /api/validate -------------------------------------------------


def test_validate_clean_project_returns_ok():
    proj = json.loads(
        (REPO_ROOT / "examples" / "com-minimal" / "config" / "Com" / "Com.json").read_text()
    )
    canif = json.loads(
        (REPO_ROOT / "examples" / "com-minimal" / "config" / "Com" / "CanIf.json").read_text()
    )
    pdur = json.loads(
        (REPO_ROOT / "examples" / "com-minimal" / "config" / "Com" / "PduR.json").read_text()
    )
    response = client.post(
        "/api/validate",
        json={"project": {"Com": proj, "CanIf": canif, "PduR": pdur}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["errorCount"] == 0


def test_validate_surfaces_issues_with_fix_payload():
    response = client.post(
        "/api/validate",
        json={
            "project": {
                "Can": {"class": "Can", "controllers": []},
                "CanIf": {
                    "class": "CanIf",
                    "networks": [{"name": "CAN0", "RxPdus": [], "TxPdus": []}],
                },
            }
        },
    )
    body = response.json()
    assert body["ok"] is False
    assert body["errorCount"] >= 1
    fixable = [i for i in body["issues"] if i["fix"] is not None]
    assert fixable, "expected at least one fixable issue"


# ----- /api/apply-fix ------------------------------------------------


def test_apply_fix_returns_updated_project_and_validation():
    response = client.post(
        "/api/validate",
        json={
            "project": {
                "Can": {"class": "Can", "controllers": []},
                "CanIf": {
                    "class": "CanIf",
                    "networks": [{"name": "CAN0", "RxPdus": [], "TxPdus": []}],
                },
            }
        },
    )
    issue = next(i for i in response.json()["issues"] if i["fix"])
    response = client.post(
        "/api/apply-fix",
        json={
            "project": {
                "Can": {"class": "Can", "controllers": []},
                "CanIf": {
                    "class": "CanIf",
                    "networks": [{"name": "CAN0", "RxPdus": [], "TxPdus": []}],
                },
            },
            "fix": issue["fix"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["validation"]["ok"] is True
    # Can controller was added by the fix
    assert any(c["name"] == "CAN0" for c in body["project"]["Can"]["controllers"])


# ----- /api/dbcs -----------------------------------------------------


def test_list_dbcs_finds_sample():
    response = client.get("/api/dbcs")
    assert "examples/dbc/sample.dbc" in response.json()["dbcs"]


# ----- /api/generate (body form) -------------------------------------


def test_generate_accepts_in_memory_project_body():
    proj = client.get("/api/projects/com-minimal").json()["project"]
    response = client.post("/api/generate", json={"project": proj})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["compileResult"]["status"] == "ok"
    assert any(f["path"].endswith("Com_Cfg.c") for f in body["files"])
