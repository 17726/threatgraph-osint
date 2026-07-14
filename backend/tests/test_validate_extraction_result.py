import copy
import hashlib

from pathlib import Path

import pytest

from scripts.validate_extraction_result import load_json, validate_payload


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/schemas/extraction-result.schema.json"
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.thn.beardshell.example.json"
EXTRACTION_PATH = (
    ROOT
    / "data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json"
)


def _load_valid_payload():
    return load_json(EXTRACTION_PATH), load_json(DOCUMENT_PATH)


def _refresh_document_hash(document):
    document["content_hash"] = "sha256:" + hashlib.sha256(
        document["clean_text"].encode("utf-8")
    ).hexdigest()


def test_extraction_result_v1_matches_schema_matrix_and_document_text():
    payload, document = _load_valid_payload()

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert report.ok, report.errors
    assert report.warnings == []


def test_validator_rejects_duplicate_chunk_ids():
    payload, document = _load_valid_payload()
    payload["chunks"].append(copy.deepcopy(payload["chunks"][0]))

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("重复 chunk_id" in error for error in report.errors)


def test_validator_rejects_relation_outside_matrix():
    payload, document = _load_valid_payload()
    invalid_payload = copy.deepcopy(payload)
    invalid_payload["chunks"][0]["relations"][0]["head_type"] = "COUNTRY"
    invalid_payload["chunks"][0]["relations"][0]["relation_type"] = "MEMBER_OF"

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


def test_validator_rejects_document_without_clean_text():
    payload, document = _load_valid_payload()
    document["raw_text"] = document.pop("clean_text")

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("clean_text" in error for error in report.errors)


def test_validator_rejects_document_hash_mismatch():
    payload, document = _load_valid_payload()
    document["content_hash"] = "sha256:" + "0" * 64

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("content_hash" in error for error in report.errors)


@pytest.mark.parametrize(
    "generated_at",
    ["not-a-date", "2026-07-15T12:00:00"],
)
def test_validator_rejects_generated_at_without_valid_timezone(generated_at):
    payload, document = _load_valid_payload()
    payload["generated_at"] = generated_at

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("generated_at" in error for error in report.errors)


def test_validator_accepts_crime_network_relationships():
    payload, document = _load_valid_payload()
    evidence = "APT28 member Operator One controls wallet Alpha and transfers funds to wallet Beta."
    document["clean_text"] += "\n" + evidence
    _refresh_document_hash(document)
    chunk = payload["chunks"][0]
    chunk["entities"].extend(
        [
            {
                "name": "Operator One",
                "type": "PERSON",
                "aliases": [],
                "description": "",
                "mention_text": "Operator One",
                "evidence_text": evidence,
                "char_start": None,
                "char_end": None,
                "confidence": 0.9,
                "candidate_status": "candidate",
                "validation_status": "unchecked",
                "validation_errors": [],
            },
            {
                "name": "Wallet Alpha",
                "type": "FINANCIAL_ACCOUNT",
                "aliases": [],
                "description": "",
                "mention_text": "wallet Alpha",
                "evidence_text": evidence,
                "char_start": None,
                "char_end": None,
                "confidence": 0.9,
                "candidate_status": "candidate",
                "validation_status": "unchecked",
                "validation_errors": [],
            },
            {
                "name": "Wallet Beta",
                "type": "FINANCIAL_ACCOUNT",
                "aliases": [],
                "description": "",
                "mention_text": "wallet Beta",
                "evidence_text": evidence,
                "char_start": None,
                "char_end": None,
                "confidence": 0.9,
                "candidate_status": "candidate",
                "validation_status": "unchecked",
                "validation_errors": [],
            },
        ]
    )
    for relation_type, head_name, head_type, tail_name, tail_type in [
        ("MEMBER_OF", "Operator One", "PERSON", "APT28", "APT_GROUP"),
        ("CONTROLS", "Operator One", "PERSON", "Wallet Alpha", "FINANCIAL_ACCOUNT"),
        ("TRANSFERS_TO", "Wallet Alpha", "FINANCIAL_ACCOUNT", "Wallet Beta", "FINANCIAL_ACCOUNT"),
    ]:
        chunk["relations"].append(
            {
                "head_name": head_name,
                "head_type": head_type,
                "relation_type": relation_type,
                "tail_name": tail_name,
                "tail_type": tail_type,
                "evidence_text": evidence,
                "char_start": None,
                "char_end": None,
                "confidence": 0.9,
                "candidate_status": "candidate",
                "validation_status": "unchecked",
                "validation_errors": [],
            }
        )

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert report.ok, report.errors


def test_validator_accepts_person_exploits_cve():
    payload, document = _load_valid_payload()
    payload["chunks"][0]["entities"][0]["type"] = "PERSON"
    relation = payload["chunks"][0]["relations"][6]
    relation["head_name"] = "CERT-UA"
    relation["head_type"] = "PERSON"
    relation["relation_type"] = "EXPLOITS"

    report = validate_payload(payload, schema_path=SCHEMA_PATH, document=document)

    assert report.ok, report.errors


def test_validator_rejects_invalid_relation_type_pairs():
    payload, document = _load_valid_payload()
    invalid_payload = copy.deepcopy(payload)
    relation = invalid_payload["chunks"][0]["relations"][0]
    relation["relation_type"] = "PART_OF"
    relation["head_type"] = "ORGANIZATION"
    relation["tail_type"] = "CAMPAIGN"

    report = validate_payload(invalid_payload, schema_path=SCHEMA_PATH, document=document)

    assert not report.ok
    assert any("不允许类型组合 ORGANIZATION -> PART_OF -> CAMPAIGN" in error for error in report.errors)
