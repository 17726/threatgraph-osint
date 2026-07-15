import json
import sqlite3

from backend.app.core.document_contract import document_content_hash
from backend.app.services.demo_store import DemoStore
from scripts.export_graph_json import export_graph_json


def make_document(*, doc_id: str = "doc-1", clean_text: str = "APT28 使用恶意软件。") -> dict:
    return {
        "doc_id": doc_id,
        "schema_version": "1.0",
        "collection_item_id": "item-1",
        "target_group": "APT28",
        "target_groups": ["APT28", "Fancy Bear"],
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
        "tags": ["APT28", "report"],
        "metadata": {"collector": "data"},
    }


def test_new_store_creates_empty_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    graph = DemoStore(db_path).get_graph(target="APT28")
    assert graph == {
        "schema_version": "1.0",
        "nodes": [],
        "edges": [],
        "evidence": [],
    }


def test_new_store_creates_import_compatible_document_schema(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    DemoStore(db_path)

    with sqlite3.connect(db_path) as connection:
        document_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(documents)")
        }
        chunk_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(chunks)")
        }

    assert {
        "collection_item_id",
        "target_groups_json",
        "tlp",
        "tags_json",
        "metadata_json",
    } <= document_columns
    assert {"section_title", "token_count"} <= chunk_columns


def test_new_store_indexes_document_content_hash(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    DemoStore(db_path)

    with sqlite3.connect(db_path) as connection:
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(documents)")
        }

    assert "idx_documents_content_hash" in indexes


def test_import_document_persists_the_complete_document_contract(tmp_path):
    store = DemoStore(tmp_path / "db.sqlite")
    document = make_document()

    result = store.import_document(document)

    assert result == {"doc_id": "doc-1", "status": "imported", "chunks": 1}
    with store.connect() as connection:
        row = connection.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (document["doc_id"],)
        ).fetchone()
        chunk = connection.execute(
            "SELECT * FROM chunks WHERE doc_id = ?", (document["doc_id"],)
        ).fetchone()
    assert row["collection_item_id"] == "item-1"
    assert json.loads(row["target_groups_json"]) == ["APT28", "Fancy Bear"]
    assert row["tlp"] == "TLP:CLEAR"
    assert json.loads(row["tags_json"]) == ["APT28", "report"]
    assert json.loads(row["metadata_json"]) == {"collector": "data"}
    assert chunk["section_title"] == ""
    assert chunk["token_count"] == 2


def test_import_document_skips_duplicate_content_and_returns_original_id(tmp_path):
    store = DemoStore(tmp_path / "db.sqlite")
    original = make_document(doc_id="doc-original")

    assert store.import_document(original)["status"] == "imported"
    result = store.import_document(make_document(doc_id="doc-duplicate"))

    assert result == {
        "doc_id": "doc-original",
        "status": "skipped",
        "message": "文档已存在",
    }
    with store.connect() as connection:
        count = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
    assert count == 1


def test_export_graph_json_writes_contract_shape(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    output_path = tmp_path / "graph.json"
    export_graph_json(db_path, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["version"] == "2.0"
    assert payload["schema_version"] == "1.0"
    assert payload["exported_from"] == "sqlite"
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["evidence"] == []


def test_unknown_target_does_not_return_unrelated_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    DemoStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO entities (
              entity_id, name, type, aliases_json, description, confidence,
              source_count, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("apt_group:other", "Other", "APT_GROUP", "[]", "", 1.0, 1, "[]"),
        )

    graph = DemoStore(db_path).get_graph(target="APT28")
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["evidence"] == []


def test_graph_target_matches_entity_alias(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    DemoStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO entities (
              entity_id, name, type, aliases_json, description, confidence,
              source_count, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "apt_group:fancy-bear",
                "Fancy Bear",
                "APT_GROUP",
                '["APT28"]',
                "",
                1.0,
                1,
                "[]",
            ),
        )

    graph = DemoStore(db_path).get_graph(target="APT28")

    assert [node["id"] for node in graph["nodes"]] == ["apt_group:fancy-bear"]
