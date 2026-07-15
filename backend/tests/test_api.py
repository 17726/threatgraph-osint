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


def test_generate_report_creates_intelligent_report_with_sections():
    response = client.post("/api/v1/reports/APT28/generate")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_group"] == "APT28"
    assert isinstance(data["title"], str)
    assert "APT28" in data["title"]
    assert isinstance(data["markdown"], str)
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) >= 4  # 至少应有 4 个章节
    assert "generated_at" in data

    # 验证章节结构
    section_types = {s["section_type"] for s in data["sections"]}
    assert "profile" in section_types
    assert "behavior_patterns" in section_types
    assert "network" in section_types
    assert "timeline" in section_types
    assert "threat_assessment" in section_types

    # 验证每个章节包含必要字段
    for section in data["sections"]:
        assert "section_id" in section
        assert "section_type" in section
        assert "title" in section
        assert "markdown" in section
        assert "evidence_ids" in section
        assert "analysis_refs" in section
        assert "graph_refs" in section
        assert "sort_order" in section


def test_generate_report_then_get_returns_sections():
    """先生成报告，再 GET 应返回结构化章节。"""
    client.post("/api/v1/reports/APT28/generate")
    response = client.get("/api/v1/reports/APT28")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_group"] == "APT28"
    assert "sections" in data
    assert len(data["sections"]) >= 4


def test_generate_report_for_nonexistent_target():
    response = client.post("/api/v1/reports/NONEXISTENT/generate")

    assert response.status_code == 404
