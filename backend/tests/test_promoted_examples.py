import json
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from scripts.export_graph_json import export_graph_json
from scripts.validate_extraction_result import load_json, validate_payload


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.thn.beardshell.example.json"
EXTRACTION_PATH = ROOT / "data/examples/extraction_result.apt28.thn.beardshell.example.json"
GOLDEN_PATH = ROOT / "data/examples/golden.apt28.thn.beardshell.example.json"
GRAPH_PATH = ROOT / "data/examples/graph.apt28.thn.beardshell.example.json"
EXTRACTION_SCHEMA_PATH = ROOT / "docs/schemas/extraction-result.schema.json"
GRAPH_SCHEMA_PATH = ROOT / "docs/schemas/graph.schema.json"


def test_promoted_extraction_example_aligns_with_document_text():
    document = load_json(DOCUMENT_PATH)
    extraction_result = load_json(EXTRACTION_PATH)

    report = validate_payload(
        extraction_result,
        schema_path=EXTRACTION_SCHEMA_PATH,
        document=document,
    )

    assert report.ok, report.errors
    assert report.warnings == []


def test_promoted_example_imports_to_canonical_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    summary = OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    assert summary.doc_id == "apt28_049"
    assert summary.chunks == 1
    assert summary.canonical_entities >= 8
    assert summary.canonical_relations >= 6
    assert summary.evidence >= 14


def test_promoted_graph_example_matches_export_schema():
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    schema = json.loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors = sorted(validator.iter_errors(graph), key=lambda item: list(item.path))

    assert errors == []
    assert graph["exported_from"] == "sqlite"
    assert {node["id"] for node in graph["nodes"]} >= {
        "apt_group:apt28",
        "malware:beardshell",
        "tool:covenant",
        "country:ukraine",
    }
    assert {edge["id"] for edge in graph["edges"]} >= {
        "rel:apt_group:apt28:USES:malware:beardshell",
        "rel:apt_group:apt28:USES:tool:covenant",
        "rel:apt_group:apt28:TARGETS:country:ukraine",
    }


def test_promoted_golden_example_uses_same_document_and_evidence():
    document = load_json(DOCUMENT_PATH)
    golden = load_json(GOLDEN_PATH)
    clean_text = document["clean_text"]

    assert golden["doc_ids"] == [document["doc_id"]]
    for relation in golden["relations"]:
        assert relation["chunk_id"] == f"{document['doc_id']}_c001"
        assert relation["evidence_text"] in clean_text


def test_promoted_graph_example_can_be_regenerated(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    output_path = tmp_path / "graph.json"

    OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)
    export_graph_json(db_path, output_path, seed_demo=False)

    graph = json.loads(output_path.read_text(encoding="utf-8"))

    assert {edge["id"] for edge in graph["edges"]} >= {
        "rel:apt_group:apt28:USES:malware:beardshell",
        "rel:apt_group:apt28:USES:tool:covenant",
        "rel:apt_group:apt28:TARGETS:country:ukraine",
    }
