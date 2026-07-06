from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_health_reports_core_components():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    assert body["data"]["components"]["sqlite"] == "ok"


def test_graph_returns_demo_nodes_edges_and_evidence():
    response = client.get("/api/v1/graph", params={"target": "APT28"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "1.0"
    assert {node["id"] for node in data["nodes"]} >= {
        "apt_group:apt28",
        "technique:t1566",
    }
    assert any(edge["source"] == "apt_group:apt28" for edge in data["edges"])
    assert data["evidence"]
    assert data["evidence"][0]["source_type"]


def test_report_returns_markdown_for_target_group():
    response = client.get("/api/v1/reports/APT28")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_group"] == "APT28"
    assert isinstance(data["title"], str)
    assert isinstance(data["markdown"], str)
