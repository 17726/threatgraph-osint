import json

from backend.app.services.demo_store import DemoStore
from scripts.export_graph_json import export_graph_json
from scripts.seed_demo_data import seed_demo_data


def test_seed_demo_data_creates_reproducible_graph(tmp_path):
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
