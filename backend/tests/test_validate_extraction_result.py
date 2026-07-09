import copy

from pathlib import Path

from scripts.validate_extraction_result import load_json, validate_payload


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/schemas/extraction-result.schema.json"
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.securelist.example.json"
EXTRACTION_PATH = ROOT / "data/extracted/extraction_result.apt28.securelist.v1.json"


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
