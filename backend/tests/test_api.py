import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.core.document_contract import document_content_hash
from backend.app.services.demo_store import DemoStore


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
