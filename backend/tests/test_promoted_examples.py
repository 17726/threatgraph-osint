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
GOLDEN_SCHEMA_PATH = ROOT / "docs/schemas/golden.schema.json"
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


def test_promoted_golden_example_matches_schema_document_and_evidence():
    document = load_json(DOCUMENT_PATH)
    golden = load_json(GOLDEN_PATH)
    schema = json.loads(GOLDEN_SCHEMA_PATH.read_text(encoding="utf-8"))
    clean_text = document["clean_text"]
    validator = Draft202012Validator(schema)

    errors = sorted(validator.iter_errors(golden), key=lambda item: list(item.path))
    assert errors == []
    assert golden["doc_ids"] == [document["doc_id"]]
    for chunk in golden["chunks"]:
        assert chunk["doc_id"] == document["doc_id"]
        assert chunk["chunk_id"] == f"{document['doc_id']}_c001"
        for entity in chunk["entities"]:
            assert entity["evidence_text"] in clean_text
        for relation in chunk["relations"]:
            assert relation["evidence_text"] in clean_text


def test_promoted_golden_entities_leave_identity_to_backend():
    golden = load_json(GOLDEN_PATH)
    schema = json.loads(GOLDEN_SCHEMA_PATH.read_text(encoding="utf-8"))
    entity_schema = schema["$defs"]["golden_entity"]

    assert "canonical_id" not in entity_schema["required"]
    assert "canonical_id" not in entity_schema["properties"]
    assert all(
        "canonical_id" not in entity
        for chunk in golden["chunks"]
        for entity in chunk["entities"]
    )


def test_promoted_golden_example_uses_extraction_relation_fields():
    extraction_result = load_json(EXTRACTION_PATH)
    golden = load_json(GOLDEN_PATH)

    extraction_entities = {
        (chunk["chunk_id"], entity["name"], entity["type"], entity["evidence_text"])
        for chunk in extraction_result["chunks"]
        for entity in chunk["entities"]
    }
    golden_entities = {
        (chunk["chunk_id"], entity["name"], entity["type"], entity["evidence_text"])
        for chunk in golden["chunks"]
        for entity in chunk["entities"]
    }
    extraction_relations = {
        (
            chunk["chunk_id"],
            relation["head_name"],
            relation["head_type"],
            relation["relation_type"],
            relation["tail_name"],
            relation["tail_type"],
            relation["evidence_text"],
        )
        for chunk in extraction_result["chunks"]
        for relation in chunk["relations"]
    }
    golden_relations = {
        (
            chunk["chunk_id"],
            relation["head_name"],
            relation["head_type"],
            relation["relation_type"],
            relation["tail_name"],
            relation["tail_type"],
            relation["evidence_text"],
        )
        for chunk in golden["chunks"]
        for relation in chunk["relations"]
    }

    assert golden_entities == extraction_entities
    assert golden_relations == extraction_relations


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
