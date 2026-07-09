import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.services.demo_store import DemoStore


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.thn.beardshell.example.json"
EXTRACTION_PATH = ROOT / "data/extracted/extraction_result.apt28.thn.beardshell.v1.json"


def client_with_store(monkeypatch, tmp_path, *, seed_demo=True):
    store = DemoStore(tmp_path / "threatgraph_osint.db", seed_demo=seed_demo)
    monkeypatch.setattr(main_module, "store", store)
    return TestClient(main_module.app), store


def test_graph_path_returns_sqlite_bfs_path(monkeypatch, tmp_path):
    client, _store = client_with_store(monkeypatch, tmp_path)

    response = client.get(
        "/api/v1/graph/path",
        params={"source": "apt_group:apt28", "target": "malware:x-agent"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["engine"] == "sqlite"
    assert data["paths"][0]["length"] == 1
    assert [node["id"] for node in data["paths"][0]["nodes"]] == [
        "apt_group:apt28",
        "malware:x-agent",
    ]
    assert data["paths"][0]["evidence_ids"] == ["ev_apt28_xagent_001"]


def test_entities_search_and_detail_use_canonical_graph(monkeypatch, tmp_path):
    client, _store = client_with_store(monkeypatch, tmp_path)

    search_response = client.get("/api/v1/entities/search", params={"q": "Fancy"})
    detail_response = client.get("/api/v1/entities/apt_group:apt28")

    assert search_response.status_code == 200
    assert any(item["id"] == "apt_group:apt28" for item in search_response.json()["data"]["items"])
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["id"] == "apt_group:apt28"
    assert detail["evidence"][0]["id"] == "ev_apt28_profile_001"


def test_documents_import_creates_document_and_chunks(monkeypatch, tmp_path):
    client, store = client_with_store(monkeypatch, tmp_path, seed_demo=False)
    document = json.loads(DOCUMENT_PATH.read_text(encoding="utf-8"))

    response = client.post("/api/v1/documents/import", json=document)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["doc_id"] == "apt28_049"
    assert data["chunk_count"] == 1
    assert store.count_rows("documents") == 1
    assert store.count_rows("chunks") == 1


def test_pipeline_run_imports_real_sample_and_exposes_analysis(monkeypatch, tmp_path):
    client, _store = client_with_store(monkeypatch, tmp_path, seed_demo=False)

    response = client.post(
        "/api/v1/pipeline/run",
        json={
            "target_group": "APT28",
            "document_path": str(DOCUMENT_PATH),
            "extraction_result_path": str(EXTRACTION_PATH),
            "export_graph": False,
        },
    )

    assert response.status_code == 200
    summary = response.json()["data"]["summary"]
    assert summary["doc_id"] == "apt28_049"
    assert summary["canonical_entities"] == 15
    assert summary["canonical_relations"] == 10

    graph = client.get("/api/v1/graph", params={"target": "APT28"}).json()["data"]
    assert any(node["id"] == "malware:beardshell" for node in graph["nodes"])

    analysis_response = client.get("/api/v1/analysis/APT28/behavior")
    assert analysis_response.status_code == 200
    patterns = analysis_response.json()["data"]["patterns"]
    assert {pattern["stage"] for pattern in patterns} >= {"工具使用", "目标偏好"}
