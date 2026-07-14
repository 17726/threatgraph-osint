"""LLM 抽取流程的版本化工件命名工具。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
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
