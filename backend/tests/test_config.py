from fastapi.testclient import TestClient

from app.main import CONFIG_LAYOUT, app

client = TestClient(app)


def test_config_defaults_to_com_in_canapp_min():
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "canapp-min"
    assert body["module"] == "Com"
    assert body["data"]["class"] == "Com"
    # Sanity: real vendor/as Com.json declares at least one network
    assert isinstance(body["data"]["networks"], list)
    assert len(body["data"]["networks"]) >= 1


def test_config_loads_every_known_module():
    for module in CONFIG_LAYOUT:
        response = client.get("/api/config", params={"module": module})
        assert response.status_code == 200, (module, response.text)
        assert response.json()["data"]["class"] == module


def test_config_unknown_module_returns_400():
    response = client.get("/api/config", params={"module": "Bogus"})
    assert response.status_code == 400
    assert "unknown module" in response.json()["detail"]


def test_config_unknown_project_returns_404():
    response = client.get("/api/config", params={"project": "does-not-exist"})
    assert response.status_code == 404
