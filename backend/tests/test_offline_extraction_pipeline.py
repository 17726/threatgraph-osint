import json
import sqlite3
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.app.services.demo_store import DemoStore
from backend.app.services.offline_extraction_pipeline import (
    OfflineExtractionPipeline,
    canonical_entity_id,
)
from scripts.export_graph_json import export_graph_json
from scripts.import_extraction_result import import_extraction_result


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.securelist.example.json"
EXTRACTION_PATH = ROOT / "data/extracted/extraction_result.apt28.securelist.v1.json"
GRAPH_SCHEMA_PATH = ROOT / "docs/schemas/graph.schema.json"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def test_offline_pipeline_imports_candidates_and_normalizes_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    summary = OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    assert summary.doc_id == "apt28_securelist_masha_bears_001"
    assert summary.run_id == "extract_apt28_securelist_masha_bears_v1"
    assert summary.chunks == 1
    assert summary.extracted_entities == 6
    assert summary.extracted_relations == 5
    assert summary.canonical_entities == 6
    assert summary.canonical_relations == 5
    assert summary.evidence == 11
    assert summary.behavior_patterns == 2

    with connect(db_path) as connection:
        run = connection.execute("SELECT * FROM extraction_runs").fetchone()
        assert run["validation_status"] == "valid"

        extracted_relation = connection.execute(
            """
            SELECT validation_status, normalized_relation_id, validation_errors_json
            FROM extracted_relations
            WHERE tail_name = 'China'
            """
        ).fetchone()
        assert extracted_relation["validation_status"] == "valid"
        assert extracted_relation["normalized_relation_id"] == (
            "rel:apt_group:apt28:TARGETS:country:china"
        )
        assert json.loads(extracted_relation["validation_errors_json"]) == []

        xagent = connection.execute(
            """
            SELECT entity_id, aliases_json
            FROM entities
            WHERE entity_id = 'malware:x-agent'
            """
        ).fetchone()
        assert xagent is not None
        assert set(json.loads(xagent["aliases_json"])) == {"CHOPSTICK", "SPLM"}

        relation = connection.execute(
            """
            SELECT relation_id, evidence_count, source_count
            FROM relations
            WHERE relation_id = 'rel:apt_group:apt28:USES:malware:x-agent'
            """
        ).fetchone()
        assert relation["evidence_count"] == 1
        assert relation["source_count"] == 1

        evidence = connection.execute(
            """
            SELECT evidence_text, source_url, source_name, quote_start, quote_end
            FROM evidence
            WHERE relation_id = 'rel:apt_group:apt28:TARGETS:country:china'
            """
        ).fetchone()
        assert evidence["source_url"] == "https://securelist.com/masha-and-these-bears/84311/"
        assert evidence["source_name"] == "Kaspersky Securelist"
        assert evidence["quote_start"] == 327
        assert evidence["quote_end"] == 464
        assert "China" in evidence["evidence_text"]


def test_offline_pipeline_graph_export_uses_real_sample_without_demo_seed(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    output_path = tmp_path / "graph.json"

    import_extraction_result(DOCUMENT_PATH, EXTRACTION_PATH, db_path, output_path)

    graph = json.loads(output_path.read_text(encoding="utf-8"))
    schema = json.loads(GRAPH_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(graph), key=lambda item: list(item.path))

    assert errors == []
    assert graph["exported_from"] == "sqlite"
    assert {node["id"] for node in graph["nodes"]} >= {
        "apt_group:apt28",
        "malware:x-agent",
        "malware:zebrocy",
        "country:china",
    }
    assert "technique:t1566" not in {node["id"] for node in graph["nodes"]}
    assert {edge["id"] for edge in graph["edges"]} >= {
        "rel:apt_group:apt28:USES:malware:x-agent",
        "rel:apt_group:apt28:USES:malware:zebrocy",
        "rel:apt_group:apt28:TARGETS:country:china",
    }
    assert len(graph["analysis"]["behavior_patterns"]) == 2
    assert graph["analysis"]["inferred_relations"] == []


def test_offline_pipeline_updates_api_graph_store_when_seed_demo_disabled(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    graph = DemoStore(db_path, seed_demo=False).get_graph(target="APT28")

    assert len(graph["nodes"]) == 6
    assert len(graph["edges"]) == 5
    assert any(edge["target"] == "malware:x-agent" for edge in graph["edges"])
    assert any(item["relation_id"] == "rel:apt_group:apt28:TARGETS:country:china" for item in graph["evidence"])


def test_offline_pipeline_generates_report_cache(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    report = DemoStore(db_path, seed_demo=False).get_report("APT28")

    assert report is not None
    assert report["title"] == "APT28 离线候选抽取报告"
    assert "未调用真实 LLM API" in report["markdown"]
    assert "工具使用" in report["markdown"]


def test_offline_pipeline_keeps_invalid_relation_as_candidate(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    invalid_path = tmp_path / "invalid_extraction.json"
    payload = json.loads(EXTRACTION_PATH.read_text(encoding="utf-8"))
    payload["chunks"][0]["relations"][0]["head_type"] = "COUNTRY"
    invalid_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    summary = OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, invalid_path)

    assert summary.extracted_relations == 5
    assert summary.canonical_relations == 4
    with connect(db_path) as connection:
        run = connection.execute("SELECT validation_status FROM extraction_runs").fetchone()
        invalid_relation = connection.execute(
            """
            SELECT validation_status, normalized_relation_id, validation_errors_json
            FROM extracted_relations
            WHERE head_type = 'COUNTRY'
            """
        ).fetchone()

    assert run["validation_status"] == "invalid"
    assert invalid_relation["validation_status"] == "invalid"
    assert invalid_relation["normalized_relation_id"] is None
    assert "不允许主体类型 COUNTRY" in json.loads(
        invalid_relation["validation_errors_json"]
    )[0]


def test_offline_pipeline_rerun_removes_stale_canonical_relation(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    modified_path = tmp_path / "modified_extraction.json"
    payload = json.loads(EXTRACTION_PATH.read_text(encoding="utf-8"))
    payload["chunks"][0]["relations"] = [
        relation
        for relation in payload["chunks"][0]["relations"]
        if relation["tail_name"] != "China"
    ]
    modified_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    pipeline = OfflineExtractionPipeline(db_path)
    first_summary = pipeline.run(DOCUMENT_PATH, EXTRACTION_PATH)
    second_summary = pipeline.run(DOCUMENT_PATH, modified_path)

    assert first_summary.canonical_relations == 5
    assert second_summary.extracted_relations == 4
    assert second_summary.canonical_relations == 4
    assert second_summary.evidence == 10
    with connect(db_path) as connection:
        stale_relation = connection.execute(
            """
            SELECT 1
            FROM relations
            WHERE relation_id = 'rel:apt_group:apt28:TARGETS:country:china'
            """
        ).fetchone()
        stale_evidence = connection.execute(
            """
            SELECT 1
            FROM evidence
            WHERE relation_id = 'rel:apt_group:apt28:TARGETS:country:china'
            """
        ).fetchone()

    assert stale_relation is None
    assert stale_evidence is None


def test_technique_entity_id_preserves_mitre_subtechnique_dot():
    assert canonical_entity_id("TECHNIQUE", "T1566") == "technique:t1566"
    assert canonical_entity_id("TECHNIQUE", "T1566.001") == "technique:t1566.001"
    assert (
        canonical_entity_id("TECHNIQUE", "Spearphishing Attachment (T1566.001)")
        == "technique:t1566.001"
    )
