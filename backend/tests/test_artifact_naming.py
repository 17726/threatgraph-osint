import re
from datetime import UTC, datetime

import pytest

from backend.app.services.artifact_naming import (
    extraction_run_id,
    filename_timestamp,
    iso_timestamp,
    timestamp_from_iso,
    validate_candidate_audit_artifact_filename,
    validate_evaluation_artifact_filename,
    validate_extraction_artifact_filename,
    validate_golden_artifact_filename,
)


@pytest.mark.parametrize(
    ("factory", "value"),
    [
        (iso_timestamp, datetime(2026, 7, 15, 12, 0, 0)),
        (filename_timestamp, datetime(2026, 7, 15, 12, 0, 0)),
        (timestamp_from_iso, "2026-07-15T12:00:00"),
    ],
)
def test_artifact_timestamp_rejects_datetime_without_timezone(factory, value):
    with pytest.raises(ValueError, match="时区"):
        factory(value)


def test_extraction_run_id_uses_timestamp_as_label_not_unique_identity():
    arguments = {
        "doc_id": "apt28_080",
        "model_name": "deepseek-v4-flash",
        "prompt_version": "1.0",
        "generated_at": iso_timestamp(datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)),
    }

    first = extraction_run_id(**arguments)
    second = extraction_run_id(**arguments)

    prefix = "extract-apt28_080-deepseek-v4-flash-1.0-1.0-20260715120000000000-"
    assert first.startswith(prefix)
    assert second.startswith(prefix)
    assert first != second
    assert re.fullmatch(r"extract-[A-Za-z0-9._-]+-\d{20}-[0-9a-f]{8}", first)


def _extraction_payload() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": (
            "extract-apt28_080-deepseek-v4-flash-1.0-1.0-"
            "20260715120000000000-1234abcd"
        ),
        "doc_id": "apt28_080",
        "model_name": "deepseek-v4-flash",
        "prompt_version": "1.0",
        "generated_at": "2026-07-15T20:00:00+08:00",
        "chunks": [],
    }


def test_extraction_artifact_filename_accepts_authoritative_run_id():
    payload = _extraction_payload()

    validate_extraction_artifact_filename(f"data/extracted/{payload['run_id']}.json", payload)


def test_extraction_artifact_filename_rejects_filename_mismatch():
    payload = _extraction_payload()

    with pytest.raises(ValueError, match="文件名"):
        validate_extraction_artifact_filename("data/extracted/extract-other.json", payload)


def test_extraction_artifact_filename_rejects_run_id_metadata_mismatch():
    payload = _extraction_payload()
    payload["model_name"] = "another-model"

    with pytest.raises(ValueError, match="run_id"):
        validate_extraction_artifact_filename(
            f"data/extracted/{payload['run_id']}.json",
            payload,
            allow_legacy=True,
        )


def test_extraction_artifact_filename_rejects_naive_generated_at():
    payload = _extraction_payload()
    payload["generated_at"] = "2026-07-15T12:00:00"

    with pytest.raises(ValueError, match="时区"):
        validate_extraction_artifact_filename(
            f"data/extracted/{payload['run_id']}.json",
            payload,
        )


def test_legacy_mode_only_skips_extraction_filename_comparison():
    payload = _extraction_payload()

    validate_extraction_artifact_filename(
        "data/examples/extraction_result.example.json",
        payload,
        allow_legacy=True,
    )


def test_candidate_audit_filename_and_extraction_binding_are_validated():
    extraction = _extraction_payload()
    audit = {**extraction, "chunks": []}

    validate_candidate_audit_artifact_filename(
        f"data/extracted/{audit['run_id']}-candidate-audit.json",
        audit,
        extraction_result=extraction,
    )

    audit["doc_id"] = "apt28_081"
    with pytest.raises(ValueError, match="doc_id"):
        validate_candidate_audit_artifact_filename(
            "data/examples/candidate-audit.json",
            audit,
            extraction_result=extraction,
            allow_legacy=True,
        )


def test_golden_artifact_filename_accepts_single_document():
    payload = {
        "schema_version": "1.0",
        "golden_version": "1.0",
        "language": "en",
        "doc_ids": ["apt28_080"],
    }

    validate_golden_artifact_filename(
        "data/golden/golden-en-apt28_080-1.0-1.0.json",
        payload,
    )


def test_golden_artifact_filename_rejects_multiple_documents():
    payload = {
        "schema_version": "1.0",
        "golden_version": "1.0",
        "language": "en",
        "doc_ids": ["apt28_080", "apt28_081"],
    }

    with pytest.raises(ValueError, match="单篇"):
        validate_golden_artifact_filename(
            "data/golden/golden-en-apt28_080+apt28_081-1.0-1.0.json",
            payload,
        )


def test_evaluation_artifact_filename_matches_payload_metadata():
    payload = {
        "schema_version": "1.0",
        "evaluated_at": "2026-07-15T20:00:00+08:00",
        "extraction": {
            "run_id": _extraction_payload()["run_id"],
            "doc_id": "apt28_080",
            "model_name": "deepseek-v4-flash",
            "prompt_version": "1.0",
            "schema_version": "1.0",
        },
        "golden": {
            "doc_id": "apt28_080",
            "schema_version": "1.0",
            "golden_version": "1.0",
            "doc_ids": ["apt28_080"],
        },
    }

    validate_evaluation_artifact_filename(
        (
            "data/evaluation/evaluation_result-apt28_080-deepseek-v4-flash-"
            "1.0-1.0-1.0-20260715120000000000.json"
        ),
        payload,
    )


def test_evaluation_artifact_filename_rejects_mismatched_extraction_run_id():
    payload = {
        "schema_version": "1.0",
        "evaluated_at": "2026-07-15T20:00:00+08:00",
        "extraction": {
            "run_id": (
                "extract-apt28_080-another-model-1.0-1.0-"
                "20260715120000000000-1234abcd"
            ),
            "doc_id": "apt28_080",
            "model_name": "deepseek-v4-flash",
            "prompt_version": "1.0",
            "schema_version": "1.0",
        },
        "golden": {
            "doc_id": "apt28_080",
            "schema_version": "1.0",
            "golden_version": "1.0",
            "doc_ids": ["apt28_080"],
        },
    }

    with pytest.raises(ValueError, match="run_id"):
        validate_evaluation_artifact_filename(
            (
                "data/evaluation/evaluation_result-apt28_080-deepseek-v4-flash-"
                "1.0-1.0-1.0-20260715120000000000.json"
            ),
            payload,
        )


def test_evaluation_artifact_filename_rejects_non_versioned_name():
    payload = {
        "schema_version": "1.0",
        "evaluated_at": "2026-07-15T20:00:00+08:00",
        "extraction": {
            "run_id": _extraction_payload()["run_id"],
            "doc_id": "apt28_080",
            "model_name": "deepseek-v4-flash",
            "prompt_version": "1.0",
            "schema_version": "1.0",
        },
        "golden": {
            "doc_id": "apt28_080",
            "golden_version": "1.0",
            "doc_ids": ["apt28_080"],
        },
    }

    with pytest.raises(ValueError, match="文件名"):
        validate_evaluation_artifact_filename("evaluation.json", payload)
