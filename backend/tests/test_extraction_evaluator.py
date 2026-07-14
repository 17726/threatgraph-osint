import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.services.extraction_evaluator import (
    _match_entities,
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


def test_evaluator_rejects_duplicate_chunk_ids():
    extraction = load_json(EXTRACTION_PATH)
    extraction["chunks"].append(copy.deepcopy(extraction["chunks"][0]))

    with pytest.raises(ValueError, match="重复 chunk_id"):
        evaluate_extraction(extraction, load_json(GOLDEN_PATH))

    golden = load_json(GOLDEN_PATH)
    golden["chunks"].append(copy.deepcopy(golden["chunks"][0]))
    assert any("重复 chunk_id" in error for error in validate_golden_payload(golden))


def test_entity_matching_maximizes_cardinality_before_score():
    extraction = {
        "doc_id": "doc",
        "chunks": [
            {
                "chunk_id": "doc_c001",
                "entities": [
                    {"name": "X", "type": "MALWARE", "aliases": ["A", "B"]},
                    {"name": "Y", "type": "MALWARE", "aliases": ["A"]},
                ],
                "relations": [],
            }
        ],
    }
    golden = {
        "doc_ids": ["doc"],
        "chunks": [
            {
                "chunk_id": "doc_c001",
                "doc_id": "doc",
                "entities": [
                    {"name": "A", "type": "MALWARE", "aliases": []},
                    {"name": "B", "type": "MALWARE", "aliases": []},
                ],
                "relations": [],
            }
        ],
    }

    result = evaluate_extraction(extraction, golden)

    assert result["entity_metrics"]["true_positive"] == 2
    assert result["entity_metrics"]["f1"] == 1.0


def test_entity_matching_maximizes_score_after_cardinality():
    predicted = [
        {"name": "A", "type": "MALWARE", "aliases": ["B"]},
        {"name": "X", "type": "MALWARE", "aliases": ["A", "C"]},
    ]
    golden = [
        {"name": "A", "type": "MALWARE", "aliases": []},
        {"name": "B", "type": "MALWARE", "aliases": []},
        {"name": "C", "type": "MALWARE", "aliases": []},
    ]

    matches = _match_entities(predicted, golden)

    assert matches == {0: 0, 1: 2}


def test_evaluator_filters_multi_document_golden_to_current_document():
    golden = load_json(GOLDEN_PATH)
    golden["doc_ids"].append("other_doc")
    golden["chunks"].append(
        {
            "chunk_id": "other_doc_c001",
            "doc_id": "other_doc",
            "entities": [{"name": "Other", "type": "MALWARE", "aliases": []}],
            "relations": [],
        }
    )

    result = evaluate_extraction(load_json(EXTRACTION_PATH), golden)

    assert result["entity_metrics"]["false_negative"] == 0
    assert result["entity_metrics"]["f1"] == 1.0


def test_golden_validation_rejects_evidence_outside_chunk_bounds():
    golden = load_json(GOLDEN_PATH)
    golden["chunks"][0]["char_start"] = 1

    errors = validate_golden_payload(golden, document=load_json(DOCUMENT_PATH))

    assert any("字符范围超出所属 chunk 范围" in error for error in errors)


def test_golden_schema_validation_rejects_missing_required_field():
    golden = copy.deepcopy(load_json(GOLDEN_PATH))
    del golden["schema_version"]

    errors = validate_golden_schema(golden)

    assert any("schema_version" in error for error in errors)


def test_golden_schema_validation_requires_language():
    golden = copy.deepcopy(load_json(GOLDEN_PATH))
    del golden["language"]

    errors = validate_golden_schema(golden)

    assert any("language" in error for error in errors)


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


def test_rejected_candidate_audit_items_count_as_false_positives():
    extraction = load_json(EXTRACTION_PATH)
    chunk_id = extraction["chunks"][0]["chunk_id"]
    candidate_audit = {
        "run_id": extraction["run_id"],
        "doc_id": extraction["doc_id"],
        "chunks": [
            {
                "chunk_id": chunk_id,
                "rejected_entities": [
                    {
                        "name": "Ungrounded malware",
                        "type": "MALWARE",
                        "validation_errors": ["evidence_text 不能为空"],
                        "audit_reason": "validation_failed",
                    }
                ],
                "rejected_relations": [
                    {
                        "head_name": "APT28",
                        "head_type": "APT_GROUP",
                        "relation_type": "USES",
                        "tail_name": "Ungrounded malware",
                        "tail_type": "MALWARE",
                        "validation_errors": ["tail 不在候选实体中"],
                        "audit_reason": "validation_failed",
                    }
                ],
            }
        ],
    }

    result = evaluate_extraction(
        extraction,
        load_json(GOLDEN_PATH),
        candidate_audit=candidate_audit,
    )

    assert result["entity_metrics"]["false_positive"] == 1
    assert result["relation_metrics"]["false_positive"] == 1
    assert result["candidate_audit"] == {
        "provided": True,
        "rejected_entities": 1,
        "rejected_relations": 1,
    }
    assert result["errors"]["extra_entities"][0]["source"] == "candidate_audit"


def test_evaluator_rejects_candidate_audit_from_another_run():
    extraction = load_json(EXTRACTION_PATH)
    candidate_audit = {
        "run_id": "extract-another-run",
        "doc_id": extraction["doc_id"],
        "chunks": [],
    }

    with pytest.raises(ValueError, match="run_id"):
        evaluate_extraction(
            extraction,
            load_json(GOLDEN_PATH),
            candidate_audit=candidate_audit,
        )


def test_normalize_name_is_case_and_whitespace_insensitive():
    assert normalize_name("  Fancy   BEAR ") == normalize_name("fancy bear")


def test_normalize_name_strips_http_prefix():
    assert normalize_name("http://bit.ly/37gAUoo") == normalize_name("bit.ly/37gAUoo")
    assert normalize_name("https://bit.ly/37gAUoo") == normalize_name("bit.ly/37gAUoo")


def test_normalize_name_normalizes_defang_brackets():
    assert normalize_name("103.224.82[.]154") == normalize_name("103.224.82.154")
    assert normalize_name("daedong.or[.]kr") == normalize_name("daedong.or.kr")


def test_normalize_name_combined_defang_and_http():
    assert normalize_name("http://daedong.or[.]kr") == normalize_name("daedong.or.kr")


def test_normalize_name_strips_file_extension():
    assert normalize_name("ElectronGold-1.1.1.exe") == normalize_name("ElectronGold-1.1.1")
    assert normalize_name("cdnver.dll") == normalize_name("cdnver")
    assert normalize_name("notepad.exe") == normalize_name("notepad")
    # 实体名本身不含扩展名时不受影响
    assert normalize_name("ElectronGold-1.1.1") == normalize_name("ElectronGold-1.1.1")


def test_evaluation_cli_validates_inputs_and_writes_report(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.extraction_evaluator.now_utc",
        lambda: datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC),
    )
    output_path = tmp_path / (
        "evaluation_result-apt28_049-manual-reviewed-1.0-1.0-1.0-"
        "20260715120000000000.json"
    )

    exit_code = main(
        [
            "--extraction-result",
            str(EXTRACTION_PATH),
            "--golden",
            str(GOLDEN_PATH),
            "--document",
            str(DOCUMENT_PATH),
            "--allow-legacy-artifacts",
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
    assert report["extraction"]["schema_version"] == "1.0"
    assert report["golden"]["golden_version"] == "1.0"


def test_evaluation_cli_counts_candidate_audit_in_f1_gate(tmp_path, monkeypatch):
    extraction = load_json(EXTRACTION_PATH)
    audit_path = tmp_path / "candidate-audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "schema_version": extraction["schema_version"],
                "run_id": extraction["run_id"],
                "doc_id": extraction["doc_id"],
                "model_name": extraction["model_name"],
                "prompt_version": extraction["prompt_version"],
                "generated_at": extraction["generated_at"],
                "chunks": [
                    {
                        "chunk_id": extraction["chunks"][0]["chunk_id"],
                        "rejected_entities": [
                            {
                                "name": "Rejected",
                                "type": "MALWARE",
                                "audit_reason": "validation_failed",
                                "validation_errors": ["invalid"],
                            }
                        ],
                        "rejected_relations": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "backend.app.services.extraction_evaluator.now_utc",
        lambda: datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC),
    )
    output_path = tmp_path / (
        "evaluation_result-apt28_049-manual-reviewed-1.0-1.0-1.0-"
        "20260715120000000000.json"
    )

    exit_code = main(
        [
            "--extraction-result",
            str(EXTRACTION_PATH),
            "--candidate-audit",
            str(audit_path),
            "--golden",
            str(GOLDEN_PATH),
            "--document",
            str(DOCUMENT_PATH),
            "--allow-legacy-artifacts",
            "--output",
            str(output_path),
            "--min-entity-f1",
            "1",
        ]
    )

    assert exit_code == 2
    report = load_json(output_path)
    assert report["entity_metrics"]["false_positive"] == 1
    assert report["entity_metrics"]["f1"] < 1.0


def test_evaluation_cli_defaults_to_versioned_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--extraction-result",
            str(EXTRACTION_PATH),
            "--golden",
            str(GOLDEN_PATH),
            "--document",
            str(DOCUMENT_PATH),
            "--allow-legacy-artifacts",
        ]
    )

    assert exit_code == 0
    outputs = list((tmp_path / "data/evaluation").glob("evaluation_result-*.json"))
    assert len(outputs) == 1
    assert outputs[0].name.startswith(
        "evaluation_result-apt28_049-manual-reviewed-1.0-1.0-1.0-"
    )


def test_evaluation_cli_rejects_legacy_filenames_without_explicit_opt_in(tmp_path):
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
        ]
    )

    assert exit_code == 1
    assert not output_path.exists()


def test_evaluation_cli_rejects_non_versioned_output_name_with_legacy_inputs(tmp_path):
    output_path = tmp_path / "evaluation.json"

    exit_code = main(
        [
            "--extraction-result",
            str(EXTRACTION_PATH),
            "--golden",
            str(GOLDEN_PATH),
            "--document",
            str(DOCUMENT_PATH),
            "--allow-legacy-artifacts",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 1
    assert not output_path.exists()
