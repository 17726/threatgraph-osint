import copy
import json

from pathlib import Path

import pytest

from scripts.validate_extraction_result import (
    ValidationReport,
    load_json,
    validate_payload,
    validate_relation_matrix,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/schemas/extraction-result.schema.json"
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.thn.beardshell.example.json"
EXTRACTION_PATH = ROOT / "data/extracted/extraction_result.apt28.thn.beardshell.v1.json"
SCHEMA_PATHS = [
    ROOT / "docs/schemas/extraction-result.schema.json",
    ROOT / "docs/schemas/golden.schema.json",
    ROOT / "docs/schemas/graph.schema.json",
]


def _load_valid_payload():
    return load_json(EXTRACTION_PATH), load_json(DOCUMENT_PATH)


def test_extraction_result_v1_matches_schema_matrix_and_document_text():
    payload, document = _load_valid_payload()

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert report.ok, report.errors
    assert report.warnings == []


def test_validator_rejects_relation_outside_matrix():
    payload, document = _load_valid_payload()
    invalid_payload = copy.deepcopy(payload)
    invalid_payload["chunks"][0]["relations"][0]["head_type"] = "COUNTRY"

    report = validate_payload(invalid_payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("不允许主体类型 COUNTRY" in error for error in report.errors)


def test_validator_rejects_final_graph_ids_in_candidate_result():
    payload, document = _load_valid_payload()
    invalid_payload = copy.deepcopy(payload)
    invalid_payload["chunks"][0]["entities"][0]["entity_id"] = "apt_group:apt28"

    report = validate_payload(invalid_payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("Additional properties are not allowed" in error for error in report.errors)


def test_validator_rejects_evidence_text_not_in_document():
    payload, document = _load_valid_payload()
    invalid_payload = copy.deepcopy(payload)
    invalid_payload["chunks"][0]["entities"][0]["evidence_text"] = "not present in raw text"

    report = validate_payload(invalid_payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("未出现在 document.clean_text" in error for error in report.errors)


@pytest.mark.parametrize("schema_path", SCHEMA_PATHS)
def test_all_graph_payload_schemas_share_new_ontology_enums(schema_path):
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert {"LOCATION", "INFRASTRUCTURE"} <= set(schema["$defs"]["entity_type"]["enum"])
    assert {"PRECEDES", "INSTANCE_OF", "IN_INDUSTRY"} <= set(
        schema["$defs"]["relation_type"]["enum"]
    )


@pytest.mark.parametrize(
    ("head_type", "relation_type", "tail_type"),
    [
        ("MALWARE", "USES", "INFRASTRUCTURE"),
        ("APT_GROUP", "TARGETS", "LOCATION"),
        ("CAMPAIGN", "ATTRIBUTED_TO", "APT_GROUP"),
        ("EVENT", "PRECEDES", "EVENT"),
        ("ORGANIZATION", "INSTANCE_OF", "TARGET"),
        ("ORGANIZATION", "IN_INDUSTRY", "INDUSTRY"),
    ],
)
def test_relation_matrix_accepts_new_ontology_combinations(
    head_type, relation_type, tail_type
):
    payload = {
        "chunks": [
            {
                "chunk_id": "doc_c001",
                "entities": [
                    {"name": "主体", "type": head_type},
                    {"name": "客体", "type": tail_type},
                ],
                "relations": [
                    {
                        "head_name": "主体",
                        "head_type": head_type,
                        "relation_type": relation_type,
                        "tail_name": "客体",
                        "tail_type": tail_type,
                    }
                ],
            }
        ]
    }
    report = ValidationReport()

    validate_relation_matrix(payload, report)

    assert report.errors == []
