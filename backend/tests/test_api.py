import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.core.document_contract import document_content_hash
from backend.app.services.demo_store import DemoStore
from backend.app.services.graph_query_service import GraphQueryService
from backend.app.services.pipeline_service import PipelineService


client = TestClient(main_module.app)
error_client = TestClient(main_module.app, raise_server_exceptions=False)


def make_document(*, doc_id: str = "doc-1", clean_text: str = "APT28 使用恶意软件。") -> dict:
    return {
        "doc_id": doc_id,
        "schema_version": "1.0",
        "target_group": "APT28",
        "target_groups": ["APT28"],
        "source_url": "https://example.test/report",
        "source_type": "vendor_report",
        "source_name": "Example",
        "title": "测试报告",
        "language": "zh",
        "clean_text": clean_text,
        "content_hash": document_content_hash(clean_text),
        "published_at": None,
        "retrieved_at": "2026-07-16T00:00:00Z",
        "source_reliability": "B",
        "tlp": "TLP:CLEAR",
        "tags": ["APT28"],
        "metadata": {},
    }


@pytest.fixture(autouse=True)
def empty_store(tmp_path, monkeypatch):
    store = DemoStore(tmp_path / "empty.db")
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(
        main_module,
        "graph_query_service",
        GraphQueryService(store.db_path),
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "pipeline_service",
        PipelineService(store.db_path, runner=lambda **_context: {}),
        raising=False,
    )


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


def test_import_rejects_legacy_raw_text_without_clean_text():
    payload = make_document()
    payload.pop("clean_text")
    payload["raw_text"] = "未经显式清洗的正文"

    response = error_client.post("/api/v1/documents/import", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_VALIDATION"


def test_import_rejects_content_hash_mismatch():
    payload = make_document()
    payload["content_hash"] = "sha256:" + "0" * 64

    response = error_client.post("/api/v1/documents/import", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_VALIDATION"


def test_graph_passes_filters_and_keeps_default_depth(monkeypatch):
    calls = {}

    def get_graph(**kwargs):
        calls.update(kwargs)
        return {"nodes": [], "edges": [], "evidence": []}

    monkeypatch.setattr(main_module.graph_query_service, "get_graph", get_graph)

    response = client.get(
        "/api/v1/graph",
        params=[
            ("entity_types", "APT_GROUP,MALWARE"),
            ("entity_ids", "technique:t1566"),
            ("relation_types", "USES"),
            ("tags", "apt"),
            ("source_types", "knowledge_base"),
            ("languages", "zh"),
            ("first_seen_from", "2015-01-01"),
            ("last_seen_to", "2026-01-01"),
            ("min_confidence", "0.8"),
            ("limit", "10"),
        ],
    )

    assert response.status_code == 200
    assert calls == {
        "target": None,
        "entity_types": ["APT_GROUP", "MALWARE"],
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


def test_graph_neighbors_uses_explicit_one_hop_service(monkeypatch):
    calls = {}

    def get_neighbors(entity_id, **kwargs):
        calls["entity_id"] = entity_id
        calls.update(kwargs)
        return {"nodes": [], "edges": [], "evidence": []}

    monkeypatch.setattr(
        main_module.graph_query_service,
        "get_neighbors",
        get_neighbors,
    )

    response = client.get(
        "/api/v1/graph/neighbors",
        params={
            "entity_id": "technique:t1566",
            "relation_types": "USES,TARGETS",
            "min_confidence": "0.7",
            "limit": "20",
        },
    )

    assert response.status_code == 200
    assert calls == {
        "entity_id": "technique:t1566",
        "relation_types": ["USES", "TARGETS"],
        "source_types": [],
        "languages": [],
        "min_confidence": 0.7,
        "limit": 20,
    }


def test_graph_path_passes_sqlite_filters(monkeypatch):
    calls = {}

    def get_path(**kwargs):
        calls.update(kwargs)
        return {
            "source": kwargs["source"],
            "target": kwargs["target"],
            "engine": "sqlite",
            "paths": [],
        }

    monkeypatch.setattr(main_module.graph_query_service, "get_path", get_path)

    response = client.get(
        "/api/v1/graph/path",
        params={
            "source": "a",
            "target": "b",
            "max_depth": "3",
            "relation_types": "USES,TARGETS",
            "min_confidence": "0.7",
        },
    )

    assert response.status_code == 200
    assert calls == {
        "source": "a",
        "target": "b",
        "max_depth": 3,
        "relation_types": ["USES", "TARGETS"],
        "min_confidence": 0.7,
    }


def test_pipeline_run_submits_one_background_operation(monkeypatch):
    calls = {}

    def submit_background(**kwargs):
        calls.update(kwargs)
        return {
            "job_id": "job-test",
            "operation": "import_extraction_and_build",
            "status": "running",
        }

    monkeypatch.setattr(
        main_module.pipeline_service,
        "submit_background",
        submit_background,
    )

    response = client.post(
        "/api/v1/pipeline/run",
        json={"doc_id": "doc-1", "extraction_mode": "reviewed"},
    )

    assert response.status_code == 202
    assert calls == {
        "doc_id": "doc-1",
        "target_group": None,
        "extraction_mode": "reviewed",
    }
    assert response.json()["data"]["operation"] == "import_extraction_and_build"
    assert response.json()["data"]["status"] == "running"


def test_pipeline_run_rejects_ambiguous_use_cache_flag():
    response = client.post(
        "/api/v1/pipeline/run",
        json={"doc_id": "doc-1", "use_cache": False},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_VALIDATION"
    assert "extraction_mode" in response.json()["error"]["message"]


def test_pipeline_run_rejects_missing_scope_before_execution():
    response = client.post("/api/v1/pipeline/run", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_VALIDATION"


def test_pipeline_status_returns_not_found_for_unknown_job():
    response = client.get("/api/v1/pipeline/status/missing-job")

    assert response.status_code == 404
