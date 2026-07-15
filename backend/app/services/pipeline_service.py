from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import sqlite3
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from backend.app.db.schema import ensure_pipeline_schema
from backend.app.services.llm_service import LLMExtractionService
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from backend.app.services.pipeline_run_archive import PipelineRunArchive
from scripts.validate_extraction_result import validate_import_payload


REVIEWED_EXTRACTION_MODE = "reviewed"
LIVE_EXTRACTION_MODE = "live"
DEFAULT_EXTRACTION_MODE = REVIEWED_EXTRACTION_MODE
REVIEWED_OPERATION = "import_extraction_and_build"
LIVE_OPERATION = "extract_and_build"
DEFAULT_OPERATION = REVIEWED_OPERATION
INTERRUPTED_ERROR = "上次执行因服务进程中断而失败"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE_EXTRACTION_DIR = REPO_ROOT / "data/run_artifacts"
DEFAULT_PIPELINE_RUN_LOG_DIR = REPO_ROOT / "data/run_logs"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _operation_for_mode(extraction_mode: str) -> str:
    if extraction_mode == REVIEWED_EXTRACTION_MODE:
        return REVIEWED_OPERATION
    if extraction_mode == LIVE_EXTRACTION_MODE:
        return LIVE_OPERATION
    raise ValueError("extraction_mode 只支持 reviewed 或 live")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}无法读取: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label}必须是 JSON 对象: {path}")
    return payload


def _resolve_repository_path(repository_root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("演示清单中的路径不能为空")
    root = repository_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"演示清单路径超出仓库: {relative_path}") from exc
    return candidate


def _manifest_sample(
    repository_root: Path,
    doc_id: str,
    manifest_path: Path,
) -> dict[str, Any] | None:
    if not manifest_path.exists():
        return None
    manifest = _load_json_object(manifest_path, "课程演示清单")
    if manifest.get("schema_version") != "1.0":
        raise ValueError("课程演示清单 schema_version 必须为 1.0")
    samples = manifest.get("samples")
    if not isinstance(samples, list):
        raise ValueError("课程演示清单 samples 必须是数组")
    matches = [
        item
        for item in samples
        if isinstance(item, dict) and item.get("doc_id") == doc_id
    ]
    if len(matches) > 1:
        raise ValueError(f"课程演示清单包含重复 doc_id: {doc_id}")
    if not matches:
        return None

    sample = matches[0]
    configured_document_path = _resolve_repository_path(
        repository_root,
        sample.get("document", ""),
    )
    configured_document = _load_json_object(
        configured_document_path,
        "课程演示 Document",
    )
    if configured_document.get("doc_id") != doc_id:
        raise ValueError(f"课程演示 Document 的 doc_id 不匹配: {doc_id}")
    return sample


def _valid_extraction(
    path: Path,
    document: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = _load_json_object(path, "extraction_result")
    except ValueError as exc:
        return None, [str(exc)]
    report = validate_import_payload(payload, document)
    return (payload if report.ok else None), report.errors


def _registry_artifact(
    repository_root: Path,
    doc_id: str,
    registry_path: Path,
) -> Path | None:
    if not registry_path.exists():
        return None
    registry = _load_json_object(registry_path, "审核工件清单")
    if registry.get("schema_version") != "1.0":
        raise ValueError("审核工件清单 schema_version 必须为 1.0")
    artifacts = registry.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("审核工件清单 artifacts 必须是数组")
    indexed: dict[str, dict[str, Any]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("审核工件清单 artifacts 条目必须是对象")
        item_doc_id = item.get("doc_id")
        if not isinstance(item_doc_id, str) or not item_doc_id:
            raise ValueError("审核工件清单 doc_id 不能为空")
        if item_doc_id in indexed:
            raise ValueError(f"审核工件清单包含重复 doc_id: {item_doc_id}")
        indexed[item_doc_id] = item
    selected = indexed.get(doc_id)
    if selected is None:
        return None
    return _resolve_repository_path(
        repository_root,
        selected.get("reviewed_extraction", ""),
    )


def select_reviewed_extraction(
    repository_root: str | Path,
    doc_id: str,
    document: dict[str, Any],
    *,
    manifest_path: str | Path | None = None,
) -> Path | None:
    """选择唯一、契约合法的已审核抽取工件。"""
    root = Path(repository_root).resolve()
    active_manifest_path = (
        Path(manifest_path).resolve()
        if manifest_path is not None
        else root / "config/course-demo.json"
    )
    sample = _manifest_sample(root, doc_id, active_manifest_path)
    if sample is not None:
        selected_path = _resolve_repository_path(
            root,
            sample.get("reviewed_extraction", ""),
        )
        if not selected_path.is_file():
            raise ValueError(f"清单中的已审核抽取工件不存在: {selected_path}")
        payload, errors = _valid_extraction(selected_path, document)
        if payload is None:
            raise ValueError(
                "清单中的已审核抽取工件契约校验失败: "
                + "; ".join(errors),
            )
        return selected_path

    selected_path = _registry_artifact(
        root,
        doc_id,
        root / "config/reviewed-extractions.json",
    )
    if selected_path is None:
        return None
    if not selected_path.is_file():
        raise ValueError(
            f"审核工件清单中的抽取结果不存在: {selected_path}"
        )
    payload, errors = _valid_extraction(selected_path, document)
    if payload is None:
        raise ValueError(
            "审核工件清单中的抽取结果契约校验失败: " + "; ".join(errors)
        )
    return selected_path


class PipelineService:
    """持久化并后台执行标准文档之后的抽取建图任务。"""

    def __init__(
        self,
        db_path: str | Path,
        *,
        runner: Callable[..., Any] | None = None,
        max_workers: int = 2,
        offline_pipeline: Any | None = None,
        extraction_service: Any | None = None,
        document_locator: Callable[[str], tuple[str, str | None]] | None = None,
        run_archive: PipelineRunArchive | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.offline_pipeline = offline_pipeline
        self.extraction_service = extraction_service
        self.document_locator = document_locator
        self.runner = runner
        self.run_archive = run_archive or PipelineRunArchive(
            extraction_dir=DEFAULT_LIVE_EXTRACTION_DIR,
            run_log_dir=DEFAULT_PIPELINE_RUN_LOG_DIR,
            path_root=REPO_ROOT,
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pipeline",
        )
        self._closed = False
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True)

    def _initialize(self) -> None:
        live_terminal_jobs: list[tuple[str, str, str, str | None]] = []
        with self.connect() as connection:
            ensure_pipeline_schema(connection)
            interrupted_at = _now()
            running_ids = [
                row["job_id"]
                for row in connection.execute(
                    "SELECT job_id FROM pipeline_jobs WHERE status = 'running'"
                ).fetchall()
            ]
            if running_ids:
                placeholders = ",".join("?" for _ in running_ids)
                connection.execute(
                    f"""UPDATE pipeline_job_steps
                        SET status = 'failed', error_message = ?, finished_at = ?
                        WHERE job_id IN ({placeholders}) AND status = 'running'""",
                    (INTERRUPTED_ERROR, interrupted_at, *running_ids),
                )
                connection.execute(
                    f"""UPDATE pipeline_jobs
                        SET status = 'failed', current_step = NULL,
                            failed_step = operation, error_message = ?, finished_at = ?
                        WHERE job_id IN ({placeholders})""",
                    (INTERRUPTED_ERROR, interrupted_at, *running_ids),
                )
            live_terminal_jobs = [
                (
                    row["job_id"],
                    row["status"],
                    row["result_json"],
                    row["error_message"],
                )
                for row in connection.execute(
                    """SELECT job_id, status, result_json, error_message
                       FROM pipeline_jobs
                       WHERE extraction_mode = 'live'
                         AND status IN ('succeeded', 'failed')"""
                ).fetchall()
            ]
        for job_id, status, result_json, error_message in live_terminal_jobs:
            try:
                archive_summary = self.run_archive.summary(job_id)
                if archive_summary is None or archive_summary["status"] in {
                    status,
                    "unavailable",
                }:
                    continue
                if status == "succeeded":
                    self.run_archive.succeed(
                        job_id,
                        json.loads(result_json or "{}"),
                    )
                else:
                    self.run_archive.fail_if_started(
                        job_id,
                        error_message or INTERRUPTED_ERROR,
                    )
            except Exception:
                # SQLite 是任务状态事实源；损坏或不可写的本机档案不能阻止服务恢复。
                pass

    def _validate_scope(
        self,
        doc_id: str | None,
        target_group: str | None,
        extraction_mode: str,
    ) -> None:
        _operation_for_mode(extraction_mode)
        if not doc_id and not target_group:
            raise ValueError("必须提供 doc_id 或 target_group")
        if doc_id and target_group:
            raise ValueError("doc_id 和 target_group 只能提供其中一个")
        if extraction_mode == LIVE_EXTRACTION_MODE and target_group:
            raise ValueError("live 模式只允许使用 doc_id，禁止按目标组织批量调用 LLM")

    def _request_key(
        self,
        *,
        doc_id: str | None,
        target_group: str | None,
        extraction_mode: str,
    ) -> str:
        request = json.dumps(
            {
                "operation": _operation_for_mode(extraction_mode),
                "doc_id": doc_id,
                "target_group": target_group,
                "extraction_mode": extraction_mode,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(request.encode("utf-8")).hexdigest()

    def _create_job(
        self,
        *,
        doc_id: str | None = None,
        target_group: str | None = None,
        extraction_mode: str = DEFAULT_EXTRACTION_MODE,
    ) -> tuple[dict[str, Any], bool]:
        self._validate_scope(doc_id, target_group, extraction_mode)
        operation = _operation_for_mode(extraction_mode)
        request_key = self._request_key(
            doc_id=doc_id,
            target_group=target_group,
            extraction_mode=extraction_mode,
        )
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT * FROM pipeline_jobs
                   WHERE request_key = ? AND status IN ('pending', 'running')
                   ORDER BY created_at DESC LIMIT 1""",
                (request_key,),
            ).fetchone()
            if existing is not None:
                return self._job_dict(existing), False

            job_id = f"job_{uuid.uuid4().hex}"
            created_at = _now()
            connection.execute(
                """INSERT INTO pipeline_jobs (
                     job_id, doc_id, target_group, use_cache, extraction_mode,
                     operation, request_key, steps_json, status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    job_id,
                    doc_id,
                    target_group,
                    int(extraction_mode == REVIEWED_EXTRACTION_MODE),
                    extraction_mode,
                    operation,
                    request_key,
                    json.dumps([operation]),
                    created_at,
                ),
            )
            connection.execute(
                """INSERT INTO pipeline_job_steps (
                     job_id, step_name, step_order, status
                   ) VALUES (?, ?, 0, 'pending')""",
                (job_id, operation),
            )
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return self._job_dict(row), True

    def create_job(
        self,
        *,
        doc_id: str | None = None,
        target_group: str | None = None,
        extraction_mode: str = DEFAULT_EXTRACTION_MODE,
    ) -> dict[str, Any]:
        job, _created = self._create_job(
            doc_id=doc_id,
            target_group=target_group,
            extraction_mode=extraction_mode,
        )
        return job

    def submit(self, **kwargs: Any) -> dict[str, Any]:
        return self.create_job(**kwargs)

    def submit_background(self, **kwargs: Any) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("流水线任务服务已关闭")
        job, created = self._create_job(**kwargs)
        if created:
            if not self.claim(job["job_id"]):
                return self.status(job["job_id"])
            try:
                self._executor.submit(self._run_claimed_job, job["job_id"])
            except Exception as exc:
                self._finish_failed(job["job_id"], exc)
                raise
            return self.status(job["job_id"])
        return job

    def claim(self, job_id: str) -> bool:
        started_at = _now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT operation FROM pipeline_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return False
            cursor = connection.execute(
                """UPDATE pipeline_jobs
                   SET status = 'running', current_step = operation, started_at = ?
                   WHERE job_id = ? AND status = 'pending'""",
                (started_at, job_id),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                """UPDATE pipeline_job_steps
                   SET status = 'running', started_at = ?
                   WHERE job_id = ? AND step_name = ? AND status = 'pending'""",
                (started_at, job_id, row["operation"]),
            )
            return True

    def run_sync(self, **kwargs: Any) -> dict[str, Any]:
        job = self.create_job(**kwargs)
        return self._run_job(job["job_id"])

    def _run_job(self, job_id: str) -> dict[str, Any]:
        if not self.claim(job_id):
            return self.status(job_id)
        return self._run_claimed_job(job_id)

    def _run_claimed_job(self, job_id: str) -> dict[str, Any]:
        job = self.status(job_id)
        context = {
            "doc_id": job["doc_id"],
            "target_group": job["target_group"],
            "extraction_mode": job["extraction_mode"],
        }
        archive_live = (
            job["extraction_mode"] == LIVE_EXTRACTION_MODE
            and self.runner is None
        )
        try:
            if archive_live:
                self.run_archive.start(
                    job_id=job_id,
                    doc_id=job["doc_id"],
                    operation=job["operation"],
                )
            if self.runner is None:
                result = self._run_default_operation(job_id=job_id, **context)
            else:
                result = self.runner(**context)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            if result is None:
                result = {}
        except Exception as exc:
            failure = self._archive_failure(job_id, exc) if archive_live else exc
            self._finish_failed(job_id, failure)
            return self.status(job_id)

        try:
            self._finish_succeeded(job_id, result)
            if archive_live:
                self.run_archive.succeed(job_id, result)
        except Exception as exc:
            failure = self._archive_failure(job_id, exc) if archive_live else exc
            self._finish_failed(job_id, failure)
        return self.status(job_id)

    def _archive_failure(self, job_id: str, exc: Exception) -> Exception:
        error = str(exc) or exc.__class__.__name__
        try:
            self.run_archive.fail_if_started(job_id, error)
        except Exception:
            error = f"{error}；运行档案更新失败"
        return RuntimeError(error)

    @staticmethod
    def _operation_for_job(
        connection: sqlite3.Connection,
        job_id: str,
    ) -> str:
        row = connection.execute(
            "SELECT operation FROM pipeline_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"流水线任务不存在: {job_id}")
        return row["operation"]

    def _finish_succeeded(self, job_id: str, result: Any) -> None:
        result_json = json.dumps(result, ensure_ascii=False, default=str)
        finished_at = _now()
        with self.connect() as connection:
            operation = self._operation_for_job(connection, job_id)
            connection.execute(
                """UPDATE pipeline_job_steps
                   SET status = 'succeeded', result_json = ?, finished_at = ?
                   WHERE job_id = ? AND step_name = ?""",
                (result_json, finished_at, job_id, operation),
            )
            connection.execute(
                """UPDATE pipeline_jobs
                   SET status = 'succeeded', current_step = NULL,
                       result_json = ?, finished_at = ?
                   WHERE job_id = ?""",
                (result_json, finished_at, job_id),
            )

    def _finish_failed(self, job_id: str, exc: Exception) -> None:
        error = str(exc) or exc.__class__.__name__
        finished_at = _now()
        with self.connect() as connection:
            operation = self._operation_for_job(connection, job_id)
            connection.execute(
                """UPDATE pipeline_job_steps
                   SET status = 'failed', result_json = '{}',
                       error_message = ?, finished_at = ?
                   WHERE job_id = ? AND step_name = ?""",
                (error, finished_at, job_id, operation),
            )
            connection.execute(
                """UPDATE pipeline_jobs
                   SET status = 'failed', current_step = NULL,
                       failed_step = operation, result_json = '{}',
                       error_message = ?, finished_at = ?
                   WHERE job_id = ?""",
                (error, finished_at, job_id),
            )

    def status(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"流水线任务不存在: {job_id}")
            steps = connection.execute(
                """SELECT step_name, step_order, status, result_json,
                          error_message, started_at, finished_at
                   FROM pipeline_job_steps
                   WHERE job_id = ? ORDER BY step_order""",
                (job_id,),
            ).fetchall()
        run_archive = (
            self.run_archive.summary(job_id)
            if row["extraction_mode"] == LIVE_EXTRACTION_MODE
            else None
        )
        return {
            **self._job_dict(row),
            "current_step": row["current_step"],
            "failed_step": row["failed_step"],
            "error": row["error_message"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "run_archive": run_archive,
            "steps": [
                {
                    "step_name": item["step_name"],
                    "step_order": item["step_order"],
                    "status": item["status"],
                    "result": json.loads(item["result_json"]),
                    "error": item["error_message"],
                    "started_at": item["started_at"],
                    "finished_at": item["finished_at"],
                }
                for item in steps
            ],
        }

    def _job_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "doc_id": row["doc_id"],
            "target_group": row["target_group"],
            "extraction_mode": row["extraction_mode"],
            "operation": row["operation"],
            "status": row["status"],
        }

    def _run_default_operation(
        self,
        *,
        job_id: str,
        doc_id: str | None,
        target_group: str | None,
        extraction_mode: str,
    ) -> dict[str, Any]:
        if doc_id:
            return {
                "doc_ids": [doc_id],
                "summaries": [self._run_document(job_id, doc_id, extraction_mode)],
            }
        doc_ids = self._document_ids_from_sqlite(target_group or "")
        if not doc_ids:
            raise ValueError(f"没有匹配文档：target_group={target_group}")
        return {
            "doc_ids": doc_ids,
            "summaries": [
                self._run_document(job_id, item, extraction_mode) for item in doc_ids
            ],
        }

    def _run_document(
        self,
        job_id: str,
        doc_id: str,
        extraction_mode: str,
    ) -> dict[str, Any]:
        document, source_document_path, reviewed_extraction_path = self._locate_inputs(
            doc_id,
            include_reviewed=extraction_mode == REVIEWED_EXTRACTION_MODE,
        )
        with tempfile.TemporaryDirectory(prefix="threatgraph-pipeline-") as directory:
            temporary_directory = Path(directory)
            document_path = source_document_path
            if document_path is None:
                document_path = temporary_directory / "document.json"
                document_path.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            if extraction_mode == REVIEWED_EXTRACTION_MODE:
                if reviewed_extraction_path is None:
                    raise ValueError(f"doc_id={doc_id} 缺少已审核抽取结果")
                extraction_path = reviewed_extraction_path
                extraction_metadata = {
                    "mode": REVIEWED_EXTRACTION_MODE,
                    "source": "reviewed_artifact",
                }
            else:
                extraction_service = self.extraction_service or LLMExtractionService()
                try:
                    extraction_result = extraction_service.extract(document)
                    if inspect.isawaitable(extraction_result):
                        extraction_result = asyncio.run(extraction_result)
                except Exception:
                    try:
                        self.run_archive.observe(
                            job_id,
                            llm=getattr(
                                extraction_service,
                                "last_api_observation",
                                {},
                            ),
                            warnings=getattr(
                                extraction_service,
                                "last_warnings",
                                [],
                            ),
                        )
                    except Exception:
                        pass
                    raise
                api_observation = getattr(
                    extraction_service,
                    "last_api_observation",
                    {},
                )
                warnings = getattr(extraction_service, "last_warnings", [])
                artifacts = self.run_archive.attach_extraction(
                    job_id,
                    extraction_result,
                    getattr(extraction_service, "last_candidate_audit", None),
                    llm=api_observation,
                    warnings=warnings,
                )
                extraction_path = self.run_archive.path_root / artifacts["result_path"]
                extraction_metadata = {
                    "mode": LIVE_EXTRACTION_MODE,
                    "source": "live_llm",
                    "run_id": extraction_result["run_id"],
                    "model": getattr(extraction_service, "model", ""),
                    "api": api_observation,
                    "warnings": warnings,
                    "artifacts": artifacts,
                    "run_log": self.run_archive.display_path(
                        self.run_archive.log_path(job_id)
                    ),
                }

            summary = self._invoke_offline_pipeline(
                str(document_path),
                str(extraction_path),
            )
            return {**summary, "extraction": extraction_metadata}

    def _locate_inputs(
        self,
        doc_id: str,
        *,
        include_reviewed: bool = True,
    ) -> tuple[dict[str, Any], Path | None, Path | None]:
        if self.document_locator is not None:
            document_value, extraction_value = self.document_locator(doc_id)
            document_path = Path(document_value)
            document = json.loads(document_path.read_text(encoding="utf-8"))
            extraction_path = Path(extraction_value) if extraction_value else None
            return document, document_path, extraction_path

        document = self._document_from_sqlite(doc_id)
        if document is not None:
            extraction_path = (
                select_reviewed_extraction(REPO_ROOT, doc_id, document)
                if include_reviewed
                else None
            )
            return document, None, extraction_path

        document_paths = sorted(
            (REPO_ROOT / "data" / "documents").glob(f"**/{doc_id}.json")
        )
        if not document_paths:
            raise ValueError(f"没有可执行的标准文档：doc_id={doc_id}")
        document_path = document_paths[0]
        document = json.loads(document_path.read_text(encoding="utf-8"))
        extraction_path = (
            select_reviewed_extraction(REPO_ROOT, doc_id, document)
            if include_reviewed
            else None
        )
        return document, document_path, extraction_path

    def _invoke_offline_pipeline(
        self,
        document_path: str,
        extraction_path: str,
    ) -> dict[str, Any]:
        pipeline = self.offline_pipeline or OfflineExtractionPipeline(self.db_path)
        result = pipeline.run(document_path, extraction_path)
        if is_dataclass(result):
            return asdict(result)
        if isinstance(result, dict):
            return result
        raise TypeError("离线流水线必须返回 dataclass 或 dict")

    def _document_ids_from_sqlite(self, target_group: str) -> list[str]:
        with self.connect() as connection:
            if not self._documents_table_exists(connection):
                return []
            rows = connection.execute(
                "SELECT doc_id FROM documents WHERE target_group = ? ORDER BY doc_id",
                (target_group,),
            ).fetchall()
        return [row["doc_id"] for row in rows]

    def _document_from_sqlite(self, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            if not self._documents_table_exists(connection):
                return None
            row = connection.execute(
                "SELECT * FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        if row is None:
            return None
        document = dict(row)
        for column, output, fallback in (
            ("target_groups_json", "target_groups", "[]"),
            ("tags_json", "tags", "[]"),
            ("metadata_json", "metadata", "{}"),
        ):
            if column in document:
                document[output] = json.loads(document.pop(column) or fallback)
        document.pop("created_at", None)
        return document

    @staticmethod
    def _documents_table_exists(connection: sqlite3.Connection) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'documents'"
            ).fetchone()
            is not None
        )
