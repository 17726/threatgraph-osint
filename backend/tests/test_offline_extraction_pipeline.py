import json
import sqlite3
from pathlib import Path

from jsonschema import Draft202012Validator

from backend.app.services.demo_store import DemoStore
from backend.app.services.offline_extraction_pipeline import (
    OfflineExtractionPipeline,
    canonical_entity_id,
    relation_validation_errors,
)
from scripts.export_graph_json import export_graph_json
from scripts.import_extraction_result import import_extraction_result


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.thn.beardshell.example.json"
EXTRACTION_PATH = (
    ROOT
    / "data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760.json"
)
GRAPH_SCHEMA_PATH = ROOT / "docs/schemas/graph.schema.json"


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def test_offline_pipeline_imports_candidates_and_normalizes_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"

    summary = OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    assert summary.doc_id == "apt28_049"
    assert (
        summary.run_id
        == "extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760"
    )
    assert summary.chunks == 1
    assert summary.extracted_entities == 15
    assert summary.extracted_relations == 10
    assert summary.canonical_entities == 15
    assert summary.canonical_relations == 10
    assert summary.evidence == 25
    assert summary.behavior_patterns == 2

    with connect(db_path) as connection:
        document_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(documents)").fetchall()
        }
        assert "clean_text" in document_columns
        assert "raw_text" not in document_columns
        stored_document = connection.execute(
            "SELECT clean_text FROM documents WHERE doc_id = 'apt28_049'"
        ).fetchone()
        assert stored_document["clean_text"]

        run = connection.execute("SELECT * FROM extraction_runs").fetchone()
        assert run["validation_status"] == "valid"

        document_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(documents)")
        }
        assert "clean_text" in document_columns
        assert "raw_text" not in document_columns
        document = connection.execute(
            "SELECT clean_text, content_hash FROM documents WHERE doc_id = ?",
            ("apt28_049",),
        ).fetchone()
        assert "BEARDSHELL" in document["clean_text"]
        assert document["content_hash"] == (
            "sha256:9d88346c7c47ad3fd5cba03bdf1e266b90d51d820fd126cf5f5a8a233e4d6b13"
        )

        extracted_relation = connection.execute(
            """
            SELECT validation_status, normalized_relation_id, validation_errors_json
            FROM extracted_relations
            WHERE tail_name = 'Ukraine'
            """
        ).fetchone()
        assert extracted_relation["validation_status"] == "valid"
        assert extracted_relation["normalized_relation_id"] == (
            "rel:apt_group:apt28:TARGETS:country:ukraine"
        )
        assert json.loads(extracted_relation["validation_errors_json"]) == []

        beardshell = connection.execute(
            """
            SELECT entity_id, aliases_json
            FROM entities
            WHERE entity_id = 'malware:beardshell'
            """
        ).fetchone()
        assert beardshell is not None
        assert json.loads(beardshell["aliases_json"]) == []

        relation = connection.execute(
            """
            SELECT relation_id, evidence_count, source_count
            FROM relations
            WHERE relation_id = 'rel:apt_group:apt28:USES:malware:beardshell'
            """
        ).fetchone()
        assert relation["evidence_count"] == 1
        assert relation["source_count"] == 1

        evidence = connection.execute(
            """
            SELECT evidence_text, source_url, source_name, quote_start, quote_end
            FROM evidence
            WHERE relation_id = 'rel:apt_group:apt28:TARGETS:country:ukraine'
            """
        ).fetchone()
        assert evidence["source_url"] == "https://thehackernews.com/2025/06/apt28-uses-signal-chat-to-deploy.html"
        assert evidence["source_name"] == "The Hacker News"
        assert evidence["quote_start"] == 2362
        assert evidence["quote_end"] == 2672
        assert "Ukraine" in evidence["evidence_text"]


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
        "malware:beardshell",
        "tool:covenant",
        "country:ukraine",
    }
    assert "country:china" not in {node["id"] for node in graph["nodes"]}
    assert {edge["id"] for edge in graph["edges"]} >= {
        "rel:apt_group:apt28:USES:malware:beardshell",
        "rel:apt_group:apt28:USES:tool:covenant",
        "rel:apt_group:apt28:TARGETS:country:ukraine",
    }
    assert len(graph["analysis"]["behavior_patterns"]) == 2
    assert graph["analysis"]["inferred_relations"] == []


def test_offline_pipeline_updates_api_graph_store_when_seed_demo_disabled(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    graph = DemoStore(db_path, seed_demo=False).get_graph(target="APT28")

    assert len(graph["nodes"]) == 11
    assert len(graph["edges"]) == 10
    assert any(edge["target"] == "malware:beardshell" for edge in graph["edges"])
    assert any(item["relation_id"] == "rel:apt_group:apt28:TARGETS:country:ukraine" for item in graph["evidence"])


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
    payload["chunks"][0]["relations"][0]["relation_type"] = "MEMBER_OF"
    invalid_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    summary = OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, invalid_path)

    assert summary.extracted_relations == 10
    assert summary.canonical_relations == 9
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


def test_offline_pipeline_migrates_legacy_documents_raw_text_column(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE documents (
              doc_id TEXT PRIMARY KEY,
              schema_version TEXT NOT NULL DEFAULT '1.0',
              collection_item_id TEXT,
              target_group TEXT NOT NULL,
              target_groups_json TEXT NOT NULL DEFAULT '[]',
              source_url TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_name TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL,
              language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
              raw_text TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              published_at TEXT,
              retrieved_at TEXT,
              source_reliability TEXT NOT NULL DEFAULT 'unknown',
              tlp TEXT NOT NULL DEFAULT 'TLP:CLEAR',
              tags_json TEXT NOT NULL DEFAULT '[]',
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );
            INSERT INTO documents (
              doc_id, target_group, source_url, source_type, title, language,
              raw_text, content_hash, created_at
            ) VALUES (
              'legacy_doc', 'APT28', 'https://example.test/legacy', 'news',
              'Legacy document', 'en', 'Legacy cleaned body',
              'sha256:legacy', '2026-07-13T00:00:00Z'
            );
            """
        )

    OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, EXTRACTION_PATH)

    with connect(db_path) as connection:
        document_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(documents)")
        }
        legacy_document = connection.execute(
            "SELECT clean_text FROM documents WHERE doc_id = ?",
            ("legacy_doc",),
        ).fetchone()
        imported_document = connection.execute(
            "SELECT clean_text FROM documents WHERE doc_id = ?",
            ("apt28_049",),
        ).fetchone()

    assert "clean_text" in document_columns
    assert "raw_text" not in document_columns
    assert legacy_document["clean_text"] == "Legacy cleaned body"
    assert "BEARDSHELL" in imported_document["clean_text"]


def test_offline_pipeline_rerun_removes_stale_canonical_relation(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    modified_path = tmp_path / "modified_extraction.json"
    payload = json.loads(EXTRACTION_PATH.read_text(encoding="utf-8"))
    payload["chunks"][0]["relations"] = [
        relation
        for relation in payload["chunks"][0]["relations"]
        if relation["tail_name"] != "Ukraine"
    ]
    modified_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    pipeline = OfflineExtractionPipeline(db_path)
    first_summary = pipeline.run(DOCUMENT_PATH, EXTRACTION_PATH)
    second_summary = pipeline.run(DOCUMENT_PATH, modified_path)

    assert first_summary.canonical_relations == 10
    assert second_summary.extracted_relations == 9
    assert second_summary.canonical_relations == 9
    assert second_summary.evidence == 24
    with connect(db_path) as connection:
        stale_relation = connection.execute(
            """
            SELECT 1
            FROM relations
            WHERE relation_id = 'rel:apt_group:apt28:TARGETS:country:ukraine'
            """
        ).fetchone()
        stale_evidence = connection.execute(
            """
            SELECT 1
            FROM evidence
            WHERE relation_id = 'rel:apt_group:apt28:TARGETS:country:ukraine'
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


def test_relation_validation_rejects_invalid_type_pair():
    errors = relation_validation_errors(
        {
            "head_name": "CERT-UA",
            "head_type": "ORGANIZATION",
            "relation_type": "PART_OF",
            "tail_name": "Operation Blacksmith",
            "tail_type": "CAMPAIGN",
        },
        {("CERT-UA", "ORGANIZATION"), ("Operation Blacksmith", "CAMPAIGN")},
    )

    assert "不允许类型组合 ORGANIZATION -> PART_OF -> CAMPAIGN" in errors


def test_offline_pipeline_keeps_invalid_type_pair_out_of_canonical_graph(tmp_path):
    db_path = tmp_path / "threatgraph_osint.db"
    invalid_path = tmp_path / "invalid_pair_extraction.json"
    payload = json.loads(EXTRACTION_PATH.read_text(encoding="utf-8"))
    chunk = payload["chunks"][0]
    chunk["entities"].append(
        {
            "name": "Operation Blacksmith",
            "type": "CAMPAIGN",
            "aliases": [],
            "description": "",
            "mention_text": "Operation Blacksmith",
            "evidence_text": chunk["relations"][0]["evidence_text"],
            "char_start": chunk["relations"][0]["char_start"],
            "char_end": chunk["relations"][0]["char_end"],
            "confidence": 0.8,
            "candidate_status": "candidate",
            "validation_status": "unchecked",
            "validation_errors": [],
        }
    )
    relation = chunk["relations"][0]
    relation.update(
        {
            "head_name": "CERT-UA",
            "head_type": "ORGANIZATION",
            "relation_type": "PART_OF",
            "tail_name": "Operation Blacksmith",
            "tail_type": "CAMPAIGN",
        }
    )
    invalid_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    summary = OfflineExtractionPipeline(db_path).run(DOCUMENT_PATH, invalid_path)

    assert summary.canonical_relations == 9
    with connect(db_path) as connection:
        invalid_relation = connection.execute(
            """
            SELECT validation_status, normalized_relation_id, validation_errors_json
            FROM extracted_relations
            WHERE relation_type = 'PART_OF'
            """
        ).fetchone()
        canonical_relation = connection.execute(
            "SELECT 1 FROM relations WHERE relation_type = 'PART_OF'"
        ).fetchone()

    assert invalid_relation["validation_status"] == "invalid"
    assert invalid_relation["normalized_relation_id"] is None
    assert "不允许类型组合 ORGANIZATION -> PART_OF -> CAMPAIGN" in json.loads(
        invalid_relation["validation_errors_json"]
    )
    assert canonical_relation is None
