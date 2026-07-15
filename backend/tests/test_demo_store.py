import json
import sqlite3

from backend.app.services.demo_store import DemoStore
from scripts.export_graph_json import export_graph_json


def test_new_store_creates_empty_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    graph = DemoStore(db_path).get_graph(target="APT28")
    assert graph == {
        "schema_version": "1.0",
        "nodes": [],
        "edges": [],
        "evidence": [],
    }


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
