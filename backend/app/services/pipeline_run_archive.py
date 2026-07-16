from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.services.artifact_naming import (
    candidate_audit_filename,
    extraction_filename,
    validate_candidate_audit_artifact_filename,
    validate_extraction_artifact_filename,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Pipeline 运行档案必须是 JSON 对象: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PipelineRunArchive:
    """持久化 live Extraction、Candidate Audit 与任务运行摘要。"""

    def __init__(
        self,
        *,
        extraction_dir: str | Path,
        run_log_dir: str | Path,
        path_root: str | Path,
    ) -> None:
        self.path_root = Path(path_root).resolve()
        self.extraction_dir = self._resolve_output_directory(extraction_dir)
        self.run_log_dir = self._resolve_output_directory(run_log_dir)

    def _resolve_output_directory(self, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.path_root / path
        path = path.resolve()
        try:
            path.relative_to(self.path_root)
        except ValueError as exc:
            raise ValueError("运行档案目录必须位于配置根目录内") from exc
        return path

    def log_path(self, job_id: str) -> Path:
        return self.run_log_dir / f"pipeline-run-{job_id}.json"

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        try:
            _write_json_atomic(path, payload)
        except OSError as exc:
            raise RuntimeError("运行档案写入失败") from exc

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            return _load_json_object(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("运行档案读取失败") from exc

    def display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.path_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"运行档案路径超出配置根目录: {path}") from exc

    def start(self, *, job_id: str, doc_id: str, operation: str) -> Path:
        started_at = _now()
        path = self.log_path(job_id)
        self._write(
            path,
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "doc_id": doc_id,
                "extraction_mode": "live",
                "operation": operation,
                "status": "running",
                "run_id": None,
                "artifacts": {},
                "llm": {},
                "warnings": [],
                "result": {},
                "error": None,
                "started_at": started_at,
                "finished_at": None,
            },
        )
        return path

    def attach_extraction(
        self,
        job_id: str,
        extraction_result: dict[str, Any],
        candidate_audit: dict[str, Any] | None,
        *,
        llm: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, str]:
        if candidate_audit is None:
            raise ValueError("live 抽取缺少 Candidate Audit，拒绝生成不完整运行档案")

        run_id = extraction_result.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("live Extraction 缺少 run_id")
        result_path = self.extraction_dir / extraction_filename(run_id)
        audit_path = self.extraction_dir / candidate_audit_filename(run_id)
        validate_extraction_artifact_filename(result_path, extraction_result)
        validate_candidate_audit_artifact_filename(
            audit_path,
            candidate_audit,
            extraction_result=extraction_result,
        )

        self._write(result_path, extraction_result)
        self._write(audit_path, candidate_audit)
        try:
            result_sha256 = _sha256(result_path)
            candidate_audit_sha256 = _sha256(audit_path)
        except OSError as exc:
            raise RuntimeError("运行档案校验失败") from exc
        artifacts = {
            "result_path": self.display_path(result_path),
            "result_sha256": result_sha256,
            "candidate_audit_path": self.display_path(audit_path),
            "candidate_audit_sha256": candidate_audit_sha256,
        }
        self._update(
            job_id,
            run_id=run_id,
            artifacts=artifacts,
            llm=llm,
            warnings=warnings,
        )
        return artifacts

    def succeed(self, job_id: str, result: dict[str, Any]) -> None:
        self._update(
            job_id,
            status="succeeded",
            result=result,
            error=None,
            finished_at=_now(),
        )

    def fail(self, job_id: str, error: str) -> None:
        self._update(
            job_id,
            status="failed",
            error=error,
            finished_at=_now(),
        )

    def fail_if_started(self, job_id: str, error: str) -> bool:
        if not self.log_path(job_id).is_file():
            return False
        self.fail(job_id, error)
        return True

    def observe(
        self,
        job_id: str,
        *,
        llm: dict[str, Any],
        warnings: list[str],
    ) -> None:
        """在抽取失败前保存模型调用观测，便于排查外部服务问题。"""
        self._update(job_id, llm=llm, warnings=warnings)

    def summary(self, job_id: str) -> dict[str, Any] | None:
        path = self.log_path(job_id)
        if not path.is_file():
            return None
        try:
            payload = _load_json_object(path)
        except (OSError, json.JSONDecodeError, ValueError):
            return {
                "run_log": self.display_path(path),
                "status": "unavailable",
                "run_id": None,
                "artifacts": {},
            }
        return {
            "run_log": self.display_path(path),
            "status": payload.get("status"),
            "run_id": payload.get("run_id"),
            "artifacts": payload.get("artifacts", {}),
        }

    def _update(self, job_id: str, **changes: Any) -> None:
        path = self.log_path(job_id)
        if not path.is_file():
            raise KeyError(f"Pipeline 运行档案不存在: {job_id}")
        payload = self._load(path)
        payload.update(changes)
        self._write(path, payload)
