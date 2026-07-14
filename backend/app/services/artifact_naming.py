"""Versioned artifact naming helpers for LLM extraction workflows."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROMPT_VERSION = "1.0"
DEFAULT_GOLDEN_VERSION = "1.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+$")
LEGACY_PREFIXES = {
    "extraction": ("extraction_result.",),
    "golden": ("golden.",),
    "evaluation": ("evaluation_result.",),
    "candidate_audit": ("candidate-audit.", "candidate-audit.json"),
}


def ensure_version(value: str, *, field_name: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} 必须是两段式数字版本，例如 1.0: {value!r}")
    return value


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def filename_timestamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M%S%f")


def timestamp_from_iso(value: str) -> str:
    return filename_timestamp(datetime.fromisoformat(value).astimezone(UTC))


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")


def _is_known_legacy_filename(filename: str, artifact_type: str) -> bool:
    return filename.startswith(LEGACY_PREFIXES[artifact_type])


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
        f"{prompt_version}-{schema_version}-{timestamp_from_iso(generated_at)}"
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
    doc_ids: list[str],
    schema_version: str,
    golden_version: str,
) -> str:
    ensure_version(schema_version, field_name="schema_version")
    ensure_version(golden_version, field_name="golden_version")
    normalized_doc_ids = canonical_doc_ids(doc_ids)
    doc_id_part = "+".join(safe_filename(doc_id) for doc_id in normalized_doc_ids)
    return (
        f"golden-{safe_filename(language)}-{doc_id_part}-"
        f"{schema_version}-{golden_version}.json"
    )


def canonical_doc_ids(doc_ids: list[str]) -> list[str]:
    if not isinstance(doc_ids, list) or not doc_ids:
        raise ValueError("doc_ids 必须至少包含一个文档 ID")
    if any(not isinstance(doc_id, str) or not doc_id.strip() for doc_id in doc_ids):
        raise ValueError("doc_ids 必须全部是非空字符串")
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("doc_ids 不允许重复")
    canonical_doc_ids = sorted(doc_ids)
    safe_doc_ids = [safe_filename(doc_id) for doc_id in canonical_doc_ids]
    if any(not safe_doc_id for safe_doc_id in safe_doc_ids):
        raise ValueError("doc_ids 必须包含可用于文件名的字符")
    if len(set(safe_doc_ids)) != len(safe_doc_ids):
        raise ValueError("doc_ids 安全化后产生文件名冲突")
    return canonical_doc_ids


def validate_extraction_artifact_filename(
    path: str | Path, payload: dict[str, Any], *, allow_legacy: bool = False
) -> None:
    filename = Path(path).name
    if not filename.startswith("extract-"):
        if allow_legacy and _is_known_legacy_filename(filename, "extraction"):
            return
        raise ValueError(f"抽取结果必须使用正式版本化文件名: {filename}")
    generated_at = payload.get("generated_at")
    if not isinstance(generated_at, str):
        raise ValueError("抽取结果缺少 generated_at，无法校验文件名")
    try:
        expected_run_id = extraction_run_id(
            doc_id=payload["doc_id"],
            model_name=payload["model_name"],
            prompt_version=payload["prompt_version"],
            schema_version=payload["schema_version"],
            generated_at=generated_at,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("抽取结果元数据无法生成标准 run_id") from exc
    expected_name = extraction_filename(expected_run_id)
    if payload.get("run_id") != expected_run_id or filename != expected_name:
        raise ValueError(
            f"文件名与抽取结果元数据不一致: expected={expected_name}, "
            f"actual={filename}"
        )


def validate_candidate_audit_filename(
    path: str | Path,
    payload: dict[str, Any],
    *,
    extraction_run_id: str | None = None,
    allow_legacy: bool = False,
) -> None:
    filename = Path(path).name
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("候选审计缺少 run_id，无法校验文件名")
    if extraction_run_id is not None and run_id != extraction_run_id:
        raise ValueError("candidate-audit run_id 必须与 extraction result 的 run_id 一致")
    if not filename.startswith("extract-"):
        if allow_legacy and _is_known_legacy_filename(filename, "candidate_audit"):
            return
        raise ValueError(f"候选审计必须使用正式版本化文件名: {filename}")
    expected_name = candidate_audit_filename(run_id)
    if filename != expected_name:
        raise ValueError(
            f"文件名与候选审计 run_id 不一致: expected={expected_name}, "
            f"actual={filename}"
        )


def validate_golden_artifact_filename(
    path: str | Path, payload: dict[str, Any], *, allow_legacy: bool = False
) -> None:
    filename = Path(path).name
    if not filename.startswith("golden-"):
        if allow_legacy and _is_known_legacy_filename(filename, "golden"):
            return
        raise ValueError(f"Golden 必须使用正式版本化文件名: {filename}")
    language = payload.get("language")
    doc_ids = payload.get("doc_ids")
    if not isinstance(language, str) or not language:
        raise ValueError("Golden 缺少 language，无法校验文件名")
    try:
        expected_name = golden_filename(
            language=language,
            doc_ids=doc_ids,
            schema_version=payload["schema_version"],
            golden_version=payload["golden_version"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Golden 元数据无法生成标准文件名") from exc
    if filename != expected_name:
        raise ValueError(
            f"文件名与 Golden 元数据不一致: expected={expected_name}, "
            f"actual={filename}"
        )


def validate_evaluation_artifact_filename(
    path: str | Path, payload: dict[str, Any], *, allow_legacy: bool = False
) -> None:
    filename = Path(path).name
    if not filename.startswith("evaluation_result-"):
        if allow_legacy and _is_known_legacy_filename(filename, "evaluation"):
            return
        raise ValueError(f"评测结果必须使用正式版本化文件名: {filename}")
    extraction = payload.get("extraction")
    golden = payload.get("golden")
    evaluated_at = payload.get("evaluated_at")
    if not isinstance(extraction, dict) or not isinstance(golden, dict):
        raise ValueError("评测结果缺少 extraction 或 golden 元数据")
    if not isinstance(evaluated_at, str):
        raise ValueError("评测结果缺少 evaluated_at，无法校验文件名")
    try:
        expected_name = evaluation_filename(
            doc_id=extraction["doc_id"],
            model_name=extraction["model_name"],
            prompt_version=extraction["prompt_version"],
            schema_version=extraction["schema_version"],
            golden_version=golden["golden_version"],
            evaluated_at=evaluated_at,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("评测结果元数据无法生成标准文件名") from exc
    if filename != expected_name:
        raise ValueError(
            f"文件名与评测结果元数据不一致: expected={expected_name}, "
            f"actual={filename}"
        )
