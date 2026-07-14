import json
from pathlib import Path

import pytest

from backend.app.services.artifact_naming import (
    SCHEMA_VERSION,
    canonical_doc_ids,
    evaluation_filename,
    golden_filename,
    timestamp_from_iso,
    validate_extraction_artifact_filename,
    validate_candidate_audit_filename,
    validate_golden_artifact_filename,
)


ROOT = Path(__file__).resolve().parents[2]


def test_extraction_filename_rejects_mismatched_payload_metadata(tmp_path):
    payload = {
        "schema_version": "1.0",
        "run_id": "extract-doc-model-1.0-1.0-20260713083926515108",
        "doc_id": "doc",
        "model_name": "model",
        "prompt_version": "1.0",
        "generated_at": "2026-07-13T08:39:26.515108+00:00",
        "chunks": [],
    }
    path = tmp_path / "extract-other-model-1.0-1.0-20260713083926515108.json"

    with pytest.raises(ValueError, match="文件名与抽取结果元数据不一致"):
        validate_extraction_artifact_filename(path, payload)


def test_golden_filename_rejects_missing_language_metadata(tmp_path):
    payload = {
        "schema_version": "1.0",
        "golden_version": "1.0",
        "target_group": "APT28",
        "doc_ids": ["apt28_080"],
        "chunks": [],
        "notes": "",
    }
    path = tmp_path / "golden-en-apt28_080-1.0-1.0.json"

    with pytest.raises(ValueError, match="language"):
        validate_golden_artifact_filename(path, payload)


def test_golden_filename_sorts_multiple_doc_ids():
    assert golden_filename(
        language="en",
        doc_ids=["apt28_081", "apt28_080"],
        schema_version="1.0",
        golden_version="1.0",
    ) == "golden-en-apt28_080+apt28_081-1.0-1.0.json"


def test_golden_filename_rejects_duplicate_doc_ids():
    with pytest.raises(ValueError, match="doc_ids"):
        golden_filename(
            language="en",
            doc_ids=["apt28_080", "apt28_080"],
            schema_version="1.0",
            golden_version="1.0",
        )


def test_golden_filename_rejects_empty_doc_ids():
    with pytest.raises(ValueError, match="doc_ids"):
        golden_filename(
            language="en",
            doc_ids=[],
            schema_version="1.0",
            golden_version="1.0",
        )


def test_golden_filename_validation_accepts_sorted_multi_document_filename(tmp_path):
    payload = {
        "schema_version": "1.0",
        "golden_version": "1.0",
        "language": "en",
        "target_group": "APT28",
        "doc_ids": ["apt28_081", "apt28_080"],
        "chunks": [],
        "notes": "",
    }
    path = tmp_path / "golden-en-apt28_080+apt28_081-1.0-1.0.json"

    validate_golden_artifact_filename(path, payload)


def test_golden_schema_requires_language():
    schema = json.loads(
        (ROOT / "docs/schemas/golden.schema.json").read_text(encoding="utf-8")
    )

    assert "language" in schema["required"]


def test_candidate_audit_filename_matches_run_id(tmp_path):
    from backend.app.services.artifact_naming import validate_candidate_audit_filename

    payload = {
        "run_id": "extract-doc-model-1.0-1.0-20260713083926515108",
        "doc_id": "doc",
    }
    path = tmp_path / "extract-doc-model-1.0-1.0-20260713083926515108-candidate-audit.json"

    validate_candidate_audit_filename(path, payload)


def test_legacy_candidate_audit_json_name_is_accepted(tmp_path):
    validate_candidate_audit_filename(
        tmp_path / "candidate-audit.json",
        {
            "run_id": "extract-doc-model-1.0-1.0-20260713083926515108",
            "doc_id": "doc",
        },
        allow_legacy=True,
    )


def test_canonical_doc_ids_reject_filename_collisions():
    with pytest.raises(ValueError, match="文件名"):
        canonical_doc_ids(["a b", "a-b"])


def test_formal_artifact_validators_reject_non_versioned_paths(tmp_path):
    with pytest.raises(ValueError, match="正式"):
        validate_extraction_artifact_filename(
            tmp_path / "extraction.json",
            {
                "schema_version": "1.0",
                "run_id": "extract-doc-model-1.0-1.0-20260713083926515108",
                "doc_id": "doc",
                "model_name": "model",
                "prompt_version": "1.0",
                "generated_at": "2026-07-13T08:39:26.515108+00:00",
            },
        )


def test_legacy_mode_only_accepts_known_example_or_legacy_names(tmp_path):
    payload = {
        "schema_version": "1.0",
        "run_id": "extract-doc-model-1.0-1.0-20260713083926515108",
        "doc_id": "doc",
        "model_name": "model",
        "prompt_version": "1.0",
        "generated_at": "2026-07-13T08:39:26.515108+00:00",
    }

    with pytest.raises(ValueError, match="正式"):
        validate_extraction_artifact_filename(tmp_path / "foo.json", payload, allow_legacy=True)

    with pytest.raises(ValueError, match="正式"):
        validate_candidate_audit_filename(
            tmp_path / "candidate-audit.json",
            {
                "run_id": "extract-doc-model-1.0-1.0-20260713083926515108",
                "doc_id": "doc",
            },
        )

    with pytest.raises(ValueError, match="正式"):
        from backend.app.services.artifact_naming import validate_evaluation_artifact_filename

        validate_evaluation_artifact_filename(
            tmp_path / "evaluation.json",
            {
                "evaluated_at": "2026-07-13T08:39:26.515108+00:00",
                "extraction": {
                    "doc_id": "doc",
                    "model_name": "model",
                    "prompt_version": "1.0",
                    "schema_version": "1.0",
                },
                "golden": {"golden_version": "1.0"},
            },
        )


def test_candidate_audit_validator_requires_extraction_run_binding(tmp_path):
    from backend.app.services.artifact_naming import validate_candidate_audit_filename

    path = tmp_path / "extract-other-model-1.0-1.0-20260713083926515108-candidate-audit.json"
    payload = {
        "run_id": "extract-other-model-1.0-1.0-20260713083926515108",
        "doc_id": "doc",
    }

    with pytest.raises(ValueError, match="extraction result"):
        validate_candidate_audit_filename(
            path,
            payload,
            extraction_run_id="extract-doc-model-1.0-1.0-20260713083926515108",
        )


def test_evaluation_filename_rejects_mismatched_payload_metadata(tmp_path):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": "2026-07-13T08:39:26.515108+00:00",
        "extraction": {
            "doc_id": "doc",
            "model_name": "model",
            "prompt_version": "1.0",
            "schema_version": SCHEMA_VERSION,
        },
        "golden": {"golden_version": "1.0"},
    }
    path = tmp_path / "evaluation_result-other-model-1.0-1.0-1.0-20260713083926515108.json"

    from backend.app.services.artifact_naming import validate_evaluation_artifact_filename

    with pytest.raises(ValueError, match="文件名与评测结果元数据不一致"):
        validate_evaluation_artifact_filename(path, payload)


def test_candidate_audit_filename_is_checked_by_evaluation_cli(tmp_path):
    from backend.app.services.artifact_naming import validate_candidate_audit_filename

    payload = {"run_id": "extract-doc-model-1.0-1.0-20260713083926515108"}
    path = tmp_path / "extract-doc-model-1.0-1.0-20260713083926515108-wrong-audit.json"

    with pytest.raises(ValueError, match="文件名与候选审计 run_id 不一致"):
        validate_candidate_audit_filename(path, payload)


def test_schema_version_uses_two_part_version_pattern():
    for schema_name in ("extraction-result.schema.json", "golden.schema.json"):
        schema = json.loads(
            (ROOT / "docs/schemas" / schema_name).read_text(encoding="utf-8")
        )
        assert schema["properties"]["schema_version"]["pattern"] == r"^\d+\.\d+$"


def test_filename_timestamp_is_always_20_digit_utc_value():
    assert timestamp_from_iso("2026-07-14T00:00:00+00:00") == "20260714000000000000"
    assert timestamp_from_iso("2026-07-14T00:00:00.123456+00:00") == "20260714000000123456"


def test_run_manifest_lists_formal_artifacts():
    manifest = json.loads(
        (ROOT / "data/runs/index.json").read_text(encoding="utf-8")
    )

    assert manifest["manifest_version"] == "1.0"
    assert "schema_version" not in manifest
    assert manifest["extractions"]
    assert manifest["goldens"]
    for artifact in [*manifest["extractions"], *manifest["goldens"]]:
        assert (ROOT / artifact["path"]).is_file()
