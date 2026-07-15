import json

from backend.app.services.demo_store import DemoStore
from scripts.export_graph_json import export_graph_json
from scripts.seed_demo_data import seed_demo_data


def test_import_document_skips_duplicate_doc_id_and_content_hash_without_changing_existing(tmp_path):
    store = DemoStore(tmp_path / "db.sqlite", seed_demo=False)
    document = {
        "doc_id": "doc-1",
        "target_group": "APT28",
        "source_url": "https://example.com/doc-1",
        "source_type": "news",
        "source_name": "Example",
        "title": "Doc 1",
        "language": "en",
        "clean_text": "APT28 uses malware.",
        "content_hash": "sha256:hash-1",
        "retrieved_at": "2026-07-15T00:00:00Z",
    }

    assert store.import_document(document)["status"] == "imported"
    assert store.import_document({**document, "title": "Changed"})["status"] == "skipped"
    assert store.import_document({**document, "doc_id": "doc-2"})["status"] == "skipped"

    with store.connect() as connection:
        row = connection.execute(
            "SELECT doc_id, title FROM documents WHERE content_hash = ?",
            (document["content_hash"],),
        ).fetchone()
    assert tuple(row) == ("doc-1", "Doc 1")


def test_import_document_returns_existing_id_for_duplicate_content_hash(tmp_path):
    store = DemoStore(tmp_path / "db.sqlite", seed_demo=False)
    first = {
        "doc_id": "doc-original",
        "target_group": "APT28",
        "source_url": "https://example.com/original",
        "source_type": "news",
        "source_name": "Example",
        "title": "Original",
        "language": "en",
        "clean_text": "same content",
        "content_hash": "sha256:duplicate",
        "retrieved_at": "2026-07-15T00:00:00Z",
    }

    assert store.import_document(first)["status"] == "imported"
    result = store.import_document({**first, "doc_id": "doc-new"})

    assert result == {
        "doc_id": "doc-original",
        "status": "skipped",
        "message": "文档已存在",
    }


def test_initialize_keeps_existing_duplicate_hash_rows_usable(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    store = DemoStore(db_path, seed_demo=False)
    with store.connect() as connection:
        connection.execute("DROP INDEX IF EXISTS ux_documents_content_hash")
        connection.execute(
            "INSERT INTO documents (doc_id, target_group, source_url, source_type, title, language, clean_text, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-1", "APT28", "", "news", "一", "zh", "same", "legacy-hash", "now"),
        )
        connection.execute(
            "INSERT INTO documents (doc_id, target_group, source_url, source_type, title, language, clean_text, content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-2", "APT28", "", "news", "二", "zh", "same", "legacy-hash", "now"),
        )

    reopened = DemoStore(db_path, seed_demo=False)
    result = reopened.import_document({
        "doc_id": "legacy-3",
        "target_group": "APT28",
        "clean_text": "same",
        "content_hash": "legacy-hash",
        "language": "zh",
    })

    assert result["status"] == "skipped"
    assert result["doc_id"] == "legacy-1"


    db_path = tmp_path / "threatgraph_osint.db"

    seed_demo_data(db_path)
    seed_demo_data(db_path)

    graph = DemoStore(db_path).get_graph(target="APT28")
    assert len(graph["nodes"]) >= 4
    assert len(graph["edges"]) == 3
    assert {item["id"] for item in graph["evidence"]} >= {
        "ev_apt28_profile_001",
        "ev_apt28_t1566_001",
    }


def test_export_graph_json_writes_contract_shape(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    output_path = tmp_path / "graph.json"
    seed_demo_data(db_path)

    export_graph_json(db_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["version"] == "2.0"
    assert payload["schema_version"] == "1.0"
    assert payload["exported_from"] == "sqlite"
    assert payload["nodes"]
    assert payload["edges"]
    assert payload["evidence"]


def test_graph_nodes_and_edges_include_evidence_ids(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    seed_demo_data(db_path)

    graph = DemoStore(db_path).get_graph(target="APT28")
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {edge["id"]: edge for edge in graph["edges"]}

    assert nodes["apt_group:apt28"]["evidence_ids"] == ["ev_apt28_profile_001"]
    assert nodes["apt_group:apt28"]["tags"]
    assert nodes["apt_group:apt28"]["first_seen"]
    assert edges["rel:apt_group:apt28:USES:technique:t1566"]["evidence_ids"] == [
        "ev_apt28_t1566_001"
    ]
    assert edges["rel:apt_group:apt28:USES:technique:t1566"]["validation_status"] == "valid"


def test_graph_evidence_includes_source_and_quote_contract_fields(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    seed_demo_data(db_path)

    graph = DemoStore(db_path).get_graph(target="APT28")
    evidence = {item["id"]: item for item in graph["evidence"]}

    item = evidence["ev_apt28_t1566_001"]
    assert item["source_type"] == "knowledge_base"
    assert item["source_name"] == "MITRE ATT&CK"
    assert item["evidence_type"] == "summary"
    assert item["retrieved_at"]
    assert item["source_reliability"] == "A"
