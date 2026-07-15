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


def test_graph_passes_query_filters_to_graph_query_service(monkeypatch):
    calls = {}

    def get_graph(**kwargs):
        calls.update(kwargs)
        return {"nodes": [], "edges": [], "evidence": []}

    monkeypatch.setattr("backend.app.main.graph_query_service.get_graph", get_graph)
    response = client.get(
        "/api/v1/graph",
        params=[
            ("entity_types", "APT_GROUP"),
            ("entity_ids", "technique:t1566"),
            ("relation_types", "USES"),
            ("tags", "apt"),
            ("source_types", "knowledge_base"),
            ("languages", "zh"),
            ("first_seen_from", "2015-01-01"),
            ("last_seen_to", "2026-01-01"),
            ("min_confidence", "0.8"),
            ("depth", "2"),
            ("limit", "10"),
        ],
    )

    assert response.status_code == 200
    assert calls == {
        "target": None,
        "entity_types": ["APT_GROUP"],
        "entity_ids": ["technique:t1566"],
        "relation_types": ["USES"],
        "tags": ["apt"],
        "source_types": ["knowledge_base"],
        "languages": ["zh"],
        "first_seen_from": "2015-01-01",
        "last_seen_to": "2026-01-01",
        "min_confidence": 0.8,
        "depth": 2,
        "limit": 10,
    }


def test_graph_path_falls_back_to_sqlite_when_neo4j_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "backend.app.main.neo4j_service.get_path",
        lambda **kwargs: {"source": kwargs["source"], "target": kwargs["target"], "engine": "sqlite", "paths": []},
    )
    calls = {}

    def get_path(**kwargs):
        calls.update(kwargs)
        return {"source": kwargs["source"], "target": kwargs["target"], "engine": "sqlite", "paths": []}

    monkeypatch.setattr("backend.app.main.graph_query_service.get_path", get_path)
    response = client.get(
        "/api/v1/graph/path",
        params={"source": "a", "target": "b", "max_depth": 3, "relation_types": "USES", "min_confidence": 0.7},
    )

    assert response.status_code == 200
    assert calls == {"source": "a", "target": "b", "max_depth": 3, "relation_types": ["USES"], "min_confidence": 0.7}


def test_health_reports_actual_neo4j_status(monkeypatch):
    monkeypatch.setattr("backend.app.main.neo4j_service.health", lambda: {"available": True, "status": "connected"})

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["data"]["components"]["neo4j"] == "connected"


def test_pipeline_run_returns_background_job_and_status(monkeypatch):
    monkeypatch.setattr(
        "backend.app.main.pipeline_service.submit_background",
        lambda **kwargs: {"job_id": "job-test", "status": "pending", **kwargs},
    )
    monkeypatch.setattr(
        "backend.app.main.pipeline_service.status",
        lambda job_id: {"job_id": job_id, "status": "succeeded"},
    )

    response = client.post(
        "/api/v1/pipeline/run",
        json={"doc_id": "doc-1", "target_group": "APT28", "use_cache": False, "steps": ["extract"]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["job_id"] == "job-test"
    assert client.get("/api/v1/pipeline/status/job-test").json()["data"]["status"] == "succeeded"


def test_import_adapts_document_and_auto_submits_pipeline(monkeypatch):
    monkeypatch.setenv("THREATGRAPH_AUTO_PIPELINE_ENABLED", "true")
    adapted = {
        "doc_id": "doc-2",
        "target_group": "APT28",
        "title": "标题",
        "language": "zh",
        "clean_text": "正文",
    }
    monkeypatch.setattr("backend.app.main.adapt_document", lambda payload: adapted)
    monkeypatch.setattr("backend.app.main.store.import_document", lambda payload: {"doc_id": payload["doc_id"], "status": "imported"})
    monkeypatch.setattr("backend.app.main.pipeline_service.submit_background", lambda **kwargs: {"job_id": "job-auto", **kwargs})

    response = client.post("/api/v1/documents/import", json={"doc_id": "doc-2", "target_group": "APT28", "title": "标题", "language": "zh", "text": "正文"})

    assert response.status_code == 200
    assert response.json()["data"]["job_id"] == "job-auto"


def test_import_skips_pipeline_for_existing_document(monkeypatch):
    monkeypatch.setenv("THREATGRAPH_AUTO_PIPELINE_ENABLED", "true")
    adapted = {"doc_id": "existing-id", "target_group": "APT28", "clean_text": "正文"}
    calls = []
    monkeypatch.setattr("backend.app.main.adapt_document", lambda payload: adapted)
    monkeypatch.setattr(
        "backend.app.main.store.import_document",
        lambda payload: {"doc_id": "existing-id", "status": "skipped", "message": "文档已存在"},
    )
    monkeypatch.setattr(
        "backend.app.main.pipeline_service.submit_background",
        lambda **kwargs: {"job_id": "job-new", "status": "pending"},
    )

    response = client.post("/api/v1/documents/import", json={"doc_id": "new-id"})

    assert response.status_code == 200
    assert response.json()["data"]["doc_id"] == "existing-id"
    assert "job_id" not in response.json()["data"]
    assert calls == []


def test_import_submits_pipeline_only_for_new_document(monkeypatch):
    monkeypatch.setenv("THREATGRAPH_AUTO_PIPELINE_ENABLED", "true")
    adapted = {"doc_id": "new-id", "target_group": "APT28", "clean_text": "正文"}
    calls = []
    monkeypatch.setattr("backend.app.main.adapt_document", lambda payload: adapted)
    monkeypatch.setattr(
        "backend.app.main.store.import_document",
        lambda payload: {"doc_id": "new-id", "status": "imported", "chunks": 1},
    )
    monkeypatch.setattr(
        "backend.app.main.pipeline_service.submit_background",
        lambda **kwargs: calls.append(kwargs) or {"job_id": "job-auto"},
    )

    response = client.post("/api/v1/documents/import", json={"doc_id": "new-id"})

    assert response.status_code == 200
    assert response.json()["data"]["job_id"] == "job-auto"
    assert calls == [{"doc_id": "new-id", "target_group": "APT28"}]


def test_graph_path_fallback_uses_split_relation_types(monkeypatch):
    monkeypatch.setattr(
        "backend.app.main.neo4j_service.get_path",
        lambda **kwargs: {"source": kwargs["source"], "target": kwargs["target"], "engine": "sqlite", "paths": []},
    )
    calls = {}

    def get_path(**kwargs):
        calls.update(kwargs)
        return {"source": kwargs["source"], "target": kwargs["target"], "engine": "sqlite", "paths": []}

    monkeypatch.setattr("backend.app.main.graph_query_service.get_path", get_path)
    response = client.get("/api/v1/graph/path?source=a&target=b&relation_types=USES,TARGETS")

    assert response.status_code == 200
    assert calls["relation_types"] == ["USES", "TARGETS"]


def test_neo4j_auth_prefers_neo4j_user(monkeypatch):
    monkeypatch.setenv("NEO4J_USER", "preferred")
    monkeypatch.setenv("NEO4J_USERNAME", "legacy")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    from backend.app.main import _neo4j_auth

    assert _neo4j_auth() == ("preferred", "secret")


def test_neo4j_auth_supports_legacy_username(monkeypatch):
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.setenv("NEO4J_USERNAME", "legacy")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    from backend.app.main import _neo4j_auth

    assert _neo4j_auth() == ("legacy", "secret")


def test_graph_path_passes_relation_types_to_neo4j(monkeypatch):
    calls = {}

    def get_path(**kwargs):
        calls.update(kwargs)
        return {"source": kwargs["source"], "target": kwargs["target"], "engine": "neo4j", "paths": []}

    monkeypatch.setattr("backend.app.main.neo4j_service.get_path", get_path)
    response = client.get(
        "/api/v1/graph/path?source=a&target=b&relation_types=USES,TARGETS"
    )

    assert response.status_code == 200
    assert calls["relation_types"] == ["USES", "TARGETS"]


def test_health_reports_unhealthy_when_sqlite_is_not_ok(monkeypatch):
    monkeypatch.setattr("backend.app.main.store.health", lambda: {"sqlite": "error"})

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["success"] is False
