import copy
import json
from pathlib import Path

from backend.app.services.extraction_evaluator import (
    evaluate_extraction,
    normalize_name,
    validate_golden_payload,
    validate_golden_schema,
)
from scripts.evaluate_extraction_against_golden import main


ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_PATH = ROOT / "data/examples/extraction_result.apt28.thn.beardshell.example.json"
GOLDEN_PATH = ROOT / "data/examples/golden.apt28.thn.beardshell.example.json"
DOCUMENT_PATH = ROOT / "data/examples/document.apt28.thn.beardshell.example.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_promoted_extraction_scores_perfectly_against_promoted_golden():
    result = evaluate_extraction(load_json(EXTRACTION_PATH), load_json(GOLDEN_PATH))

    assert result["entity_metrics"]["precision"] == 1.0
    assert result["entity_metrics"]["recall"] == 1.0
    assert result["entity_metrics"]["f1"] == 1.0
    assert result["relation_metrics"]["f1"] == 1.0
    assert all(not errors for errors in result["errors"].values())


def test_promoted_golden_passes_relation_and_evidence_validation():
    assert validate_golden_payload(
        load_json(GOLDEN_PATH),
        document=load_json(DOCUMENT_PATH),
    ) == []


def test_golden_validation_rejects_relation_outside_matrix():
    golden = copy.deepcopy(load_json(GOLDEN_PATH))
    golden["chunks"][0]["relations"][0]["head_type"] = "MALWARE"

    errors = validate_golden_payload(golden)

    assert any("不允许类型组合" in error for error in errors)


def test_golden_schema_validation_rejects_missing_required_field():
    golden = copy.deepcopy(load_json(GOLDEN_PATH))
    del golden["schema_version"]

    errors = validate_golden_schema(golden)

    assert any("schema_version" in error for error in errors)


def test_entity_alias_matching_also_matches_relation_endpoints():
    extraction = load_json(EXTRACTION_PATH)
    golden = load_json(GOLDEN_PATH)
    predicted_apt = next(
        entity for entity in extraction["chunks"][0]["entities"] if entity["name"] == "APT28"
    )
    predicted_apt["name"] = "Fancy Bear"
    predicted_apt["aliases"] = ["APT28"]
    for relation in extraction["chunks"][0]["relations"]:
        if relation["head_name"] == "APT28":
            relation["head_name"] = "Fancy Bear"

    result = evaluate_extraction(extraction, golden)

    assert result["entity_metrics"]["f1"] == 1.0
    assert result["relation_metrics"]["f1"] == 1.0


def test_evaluator_reports_missing_and_extra_items():
    extraction = copy.deepcopy(load_json(EXTRACTION_PATH))
    golden = load_json(GOLDEN_PATH)
    extraction["chunks"][0]["entities"].pop()
    extraction["chunks"][0]["relations"].pop()
    extraction["chunks"][0]["entities"].append(
        {
            "name": "Extra malware",
            "type": "MALWARE",
            "aliases": [],
        }
    )

    result = evaluate_extraction(extraction, golden)

    assert result["entity_metrics"]["false_positive"] == 1
    assert result["entity_metrics"]["false_negative"] == 1
    assert result["relation_metrics"]["false_negative"] == 1
    assert result["errors"]["extra_entities"][0]["name"] == "Extra malware"


def test_normalize_name_is_case_and_whitespace_insensitive():
    assert normalize_name("  Fancy   BEAR ") == normalize_name("fancy bear")


def test_evaluation_cli_validates_inputs_and_writes_report(tmp_path):
    output_path = tmp_path / "evaluation.json"

    exit_code = main(
        [
            "--extraction-result",
            str(EXTRACTION_PATH),
            "--golden",
            str(GOLDEN_PATH),
            "--document",
            str(DOCUMENT_PATH),
            "--output",
            str(output_path),
            "--min-entity-f1",
            "1",
            "--min-relation-f1",
            "1",
        ]
    )

    assert exit_code == 0
    report = load_json(output_path)
    assert report["entity_metrics"]["f1"] == 1.0
    assert report["relation_metrics"]["f1"] == 1.0
