"""LLM 抽取流程的版本化工件命名工具。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = "1.0"
DEFAULT_PROMPT_VERSION = "1.0"
DEFAULT_GOLDEN_VERSION = "1.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+$")


def ensure_version(value: str, *, field_name: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} 必须是两段式数字版本，例如 1.0: {value!r}")
    return value


def now_utc() -> datetime:
    return datetime.now(UTC)


def _require_aware_datetime(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("时间必须包含明确时区")
    return moment


def iso_timestamp(moment: datetime) -> str:
    return _require_aware_datetime(moment).astimezone(UTC).isoformat()


def filename_timestamp(moment: datetime) -> str:
    return _require_aware_datetime(moment).astimezone(UTC).strftime("%Y%m%d%H%M%S%f")


def timestamp_from_iso(value: str) -> str:
    return filename_timestamp(datetime.fromisoformat(value))


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")


def extraction_run_id(
    *,
    doc_id: str,
    model_name: str,
    prompt_version: str,
    schema_version: str = SCHEMA_VERSION,
    generated_at: str,
) -> str:
    ensure_version(prompt_version, field_name="prompt_version")
    ensure_version(schema_version, field_name="schema_version")
    return (
        f"extract-{safe_filename(doc_id)}-{safe_filename(model_name)}-"
        f"{prompt_version}-{schema_version}-{timestamp_from_iso(generated_at)}-"
        f"{uuid4().hex[:8]}"
    )


def extraction_filename(run_id: str) -> str:
    return f"{run_id}.json"


def candidate_audit_filename(run_id: str) -> str:
    return f"{run_id}-candidate-audit.json"


def evaluation_filename(
    *,
    doc_id: str,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    golden_version: str,
    evaluated_at: str,
) -> str:
    ensure_version(prompt_version, field_name="prompt_version")
    ensure_version(schema_version, field_name="schema_version")
    ensure_version(golden_version, field_name="golden_version")
    return (
        f"evaluation_result-{safe_filename(doc_id)}-{safe_filename(model_name)}-"
        f"{prompt_version}-{schema_version}-{golden_version}-"
        f"{timestamp_from_iso(evaluated_at)}.json"
    )


def golden_filename(
    *,
    language: str,
    doc_id: str,
    schema_version: str,
    golden_version: str,
) -> str:
    ensure_version(schema_version, field_name="schema_version")
    ensure_version(golden_version, field_name="golden_version")
    return (
        f"golden-{safe_filename(language)}-{safe_filename(doc_id)}-"
        f"{schema_version}-{golden_version}.json"
    )


def _required_string(payload: dict[str, Any], field_name: str, *, artifact: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{artifact} 缺少非空字符串字段 {field_name}")
    return value


def _run_id_prefix(payload: dict[str, Any], *, artifact: str) -> tuple[str, str]:
    run_id = _required_string(payload, "run_id", artifact=artifact)
    doc_id = _required_string(payload, "doc_id", artifact=artifact)
    model_name = _required_string(payload, "model_name", artifact=artifact)
    prompt_version = _required_string(payload, "prompt_version", artifact=artifact)
    schema_version = _required_string(payload, "schema_version", artifact=artifact)
    ensure_version(prompt_version, field_name="prompt_version")
    ensure_version(schema_version, field_name="schema_version")
    return run_id, (
        f"extract-{safe_filename(doc_id)}-{safe_filename(model_name)}-"
        f"{prompt_version}-{schema_version}-"
    )


def _validate_run_id_metadata(payload: dict[str, Any], *, artifact: str) -> str:
    run_id, metadata_prefix = _run_id_prefix(payload, artifact=artifact)
    generated_at = _required_string(payload, "generated_at", artifact=artifact)
    expected_prefix = f"{metadata_prefix}{timestamp_from_iso(generated_at)}-"
    if not re.fullmatch(re.escape(expected_prefix) + r"[0-9a-f]{8}", run_id):
        raise ValueError(f"{artifact} 的 run_id 与 payload 元数据不一致")
    return run_id


def _validate_run_id_reference(payload: dict[str, Any], *, artifact: str) -> str:
    run_id, metadata_prefix = _run_id_prefix(payload, artifact=artifact)
    pattern = re.escape(metadata_prefix) + r"\d{20}-[0-9a-f]{8}"
    if not re.fullmatch(pattern, run_id):
        raise ValueError(f"{artifact} 的 run_id 与 payload 元数据不一致")
    return run_id


def validate_extraction_artifact_filename(
    path: str | Path,
    payload: dict[str, Any],
    *,
    allow_legacy: bool = False,
) -> None:
    """校验正式 Extraction 文件名及其权威 Run ID 元数据。"""

    run_id = _validate_run_id_metadata(payload, artifact="Extraction")
    expected_name = extraction_filename(run_id)
    actual_name = Path(path).name
    if not allow_legacy and actual_name != expected_name:
        raise ValueError(
            f"Extraction 文件名与 run_id 不一致: expected={expected_name}, actual={actual_name}"
        )


def validate_candidate_audit_artifact_filename(
    path: str | Path,
    payload: dict[str, Any],
    *,
    extraction_result: dict[str, Any] | None = None,
    allow_legacy: bool = False,
) -> None:
    """校验 Candidate Audit 文件名及其与 Extraction 的绑定。"""

    if extraction_result is not None:
        for field_name in (
            "run_id",
            "doc_id",
            "model_name",
            "prompt_version",
            "schema_version",
            "generated_at",
        ):
            if payload.get(field_name) != extraction_result.get(field_name):
                raise ValueError(
                    f"Candidate Audit 的 {field_name} 与 Extraction Result 不一致"
                )
    run_id = _validate_run_id_metadata(payload, artifact="Candidate Audit")
    expected_name = candidate_audit_filename(run_id)
    actual_name = Path(path).name
    if not allow_legacy and actual_name != expected_name:
        raise ValueError(
            "Candidate Audit 文件名与 run_id 不一致: "
            f"expected={expected_name}, actual={actual_name}"
        )


def validate_golden_artifact_filename(
    path: str | Path,
    payload: dict[str, Any],
    *,
    allow_legacy: bool = False,
) -> None:
    """校验当前单 Document Golden 的正式文件名。"""

    language = _required_string(payload, "language", artifact="Golden")
    schema_version = _required_string(payload, "schema_version", artifact="Golden")
    golden_version = _required_string(payload, "golden_version", artifact="Golden")
    doc_ids = payload.get("doc_ids")
    if not isinstance(doc_ids, list) or len(doc_ids) != 1:
        raise ValueError("正式 Golden 当前必须且只能对应单篇 Document")
    doc_id = doc_ids[0]
    if not isinstance(doc_id, str) or not doc_id:
        raise ValueError("Golden 的 doc_ids 必须包含一个非空文档 ID")
    expected_name = golden_filename(
        language=language,
        doc_id=doc_id,
        schema_version=schema_version,
        golden_version=golden_version,
    )
    actual_name = Path(path).name
    if not allow_legacy and actual_name != expected_name:
        raise ValueError(
            f"Golden 文件名与 payload 不一致: expected={expected_name}, actual={actual_name}"
        )


def validate_evaluation_artifact_filename(
    path: str | Path,
    payload: dict[str, Any],
) -> None:
    """校验 Evaluation 文件名及其 Extraction/Golden 元数据。"""

    extraction = payload.get("extraction")
    golden = payload.get("golden")
    if not isinstance(extraction, dict) or not isinstance(golden, dict):
        raise ValueError("Evaluation 缺少 extraction 或 golden 元数据")
    evaluated_at = _required_string(payload, "evaluated_at", artifact="Evaluation")
    _validate_run_id_reference(extraction, artifact="Evaluation extraction")
    doc_id = _required_string(extraction, "doc_id", artifact="Evaluation extraction")
    model_name = _required_string(
        extraction,
        "model_name",
        artifact="Evaluation extraction",
    )
    prompt_version = _required_string(
        extraction,
        "prompt_version",
        artifact="Evaluation extraction",
    )
    schema_version = _required_string(
        extraction,
        "schema_version",
        artifact="Evaluation extraction",
    )
    golden_version = _required_string(
        golden,
        "golden_version",
        artifact="Evaluation golden",
    )
    golden_doc_id = _required_string(golden, "doc_id", artifact="Evaluation golden")
    golden_doc_ids = golden.get("doc_ids")
    if golden_doc_id != doc_id:
        raise ValueError("Evaluation 的 Golden doc_id 与 Extraction doc_id 不一致")
    if golden_doc_ids is not None and (
        not isinstance(golden_doc_ids, list) or doc_id not in golden_doc_ids
    ):
        raise ValueError("Evaluation 的 Golden doc_ids 与 Extraction doc_id 不一致")
    expected_name = evaluation_filename(
        doc_id=doc_id,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        golden_version=golden_version,
        evaluated_at=evaluated_at,
    )
    actual_name = Path(path).name
    if actual_name != expected_name:
        raise ValueError(
            "Evaluation 文件名与 payload 不一致: "
            f"expected={expected_name}, actual={actual_name}"
        )
