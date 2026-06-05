"""Backend `/schemas` endpoint smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import SCHEMA_FILES, app
from app.model import SUPPORTED_CLASSES

client = TestClient(app)


def test_schemas_bundle_contains_every_supported_class():
    response = client.get("/schemas")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(SUPPORTED_CLASSES)
    for cls, schema in body.items():
        assert schema["title"] == cls
        assert schema["properties"]["class"]["const"] == cls


def test_individual_schema_endpoint():
    response = client.get("/schemas/Com")
    assert response.status_code == 200
    schema = response.json()
    assert schema["title"] == "Com"
    assert "$id" in schema


def test_unknown_schema_returns_404():
    response = client.get("/schemas/Bogus")
    assert response.status_code == 404


def test_dispatch_tables_in_sync():
    assert set(SCHEMA_FILES) == set(SUPPORTED_CLASSES), (
        "/schemas dispatch and model dispatch drifted"
    )
