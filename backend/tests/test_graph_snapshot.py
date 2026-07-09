import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "data/graph/graph.json"
GRAPH_SCHEMA_PATH = ROOT / "docs/schemas/graph.schema.json"


def test_committed_graph_snapshot_matches_schema():
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    schema = json.loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors = sorted(validator.iter_errors(graph), key=lambda item: list(item.path))

    assert errors == []
    assert graph["exported_from"] == "sqlite"
    assert graph["source_of_truth"]
