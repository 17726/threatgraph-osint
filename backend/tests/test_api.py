import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.services.demo_store import DemoStore


client = TestClient(main_module.app)


@pytest.fixture(autouse=True)
def empty_store(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "store", DemoStore(tmp_path / "empty.db"))


def test_health_reports_core_components():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    assert body["data"]["components"]["sqlite"] == "ok"


def test_graph_returns_empty_payload_when_database_has_no_graph_data():
    response = client.get("/api/v1/graph", params={"target": "APT28"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "1.0"
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["evidence"] == []


def test_report_returns_not_found_when_database_has_no_report():
    response = client.get("/api/v1/reports/APT28")

    assert response.status_code == 404


def test_generate_report_for_empty_target():
    response = client.post("/api/v1/reports/APT28/generate")

    assert response.status_code == 404
