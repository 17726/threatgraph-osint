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
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline


DEFAULT_OPERATION = "extract_and_build"
INTERRUPTED_ERROR = "上次执行因服务进程中断而失败"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PipelineService:
    """持久化并同步执行 P0 离线抽取建图任务。"""

    def __init__(
        self,
        db_path: str | Path,
        *,
        runner: Callable[..., Any] | None = None,
        max_workers: int = 2,
        offline_pipeline: Any | None = None,
        document_locator: Callable[[str], tuple[str, str | None]] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.offline_pipeline = offline_pipeline
        self.document_locator = document_locator
        self.runner = runner or self._run_default_operation
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pipeline",
        )
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _initialize(self) -> None:
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

    def _validate_scope(
        self,
        doc_id: str | None,
        target_group: str | None,
    ) -> None:
        if not doc_id and not target_group:
            raise ValueError("必须提供 doc_id 或 target_group")
        if doc_id and target_group:
            raise ValueError("doc_id 和 target_group 只能提供其中一个")

    def _request_key(
        self,
        *,
        doc_id: str | None,
        target_group: str | None,
        use_cache: bool,
    ) -> str:
        request = json.dumps(
            {
                "operation": DEFAULT_OPERATION,
                "doc_id": doc_id,
                "target_group": target_group,
                "use_cache": use_cache,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(request.encode("utf-8")).hexdigest()

    def create_job(
        self,
        *,
        doc_id: str | None = None,
        target_group: str | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        self._validate_scope(doc_id, target_group)
        request_key = self._request_key(
            doc_id=doc_id,
            target_group=target_group,
            use_cache=use_cache,
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
                return self._job_dict(existing)

            job_id = f"job_{uuid.uuid4().hex}"
            created_at = _now()
            connection.execute(
                """INSERT INTO pipeline_jobs (
                     job_id, doc_id, target_group, use_cache, operation,
                     request_key, steps_json, status, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    job_id,
                    doc_id,
                    target_group,
                    int(use_cache),
                    DEFAULT_OPERATION,
                    request_key,
                    json.dumps([DEFAULT_OPERATION]),
                    created_at,
                ),
            )
            connection.execute(
                """INSERT INTO pipeline_job_steps (
                     job_id, step_name, step_order, status
                   ) VALUES (?, ?, 0, 'pending')""",
                (job_id, DEFAULT_OPERATION),
            )
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return self._job_dict(row)

    def submit(self, **kwargs: Any) -> dict[str, Any]:
        return self.create_job(**kwargs)

    def submit_background(self, **kwargs: Any) -> dict[str, Any]:
        job = self.create_job(**kwargs)
        if job["status"] == "pending":
            self._executor.submit(self._run_job, job["job_id"])
        return job

    def claim(self, job_id: str) -> bool:
        started_at = _now()
        with self.connect() as connection:
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
                (started_at, job_id, DEFAULT_OPERATION),
            )
            return True

    def run_sync(self, **kwargs: Any) -> dict[str, Any]:
        job = self.create_job(**kwargs)
        return self._run_job(job["job_id"])

    def _run_job(self, job_id: str) -> dict[str, Any]:
        job = self.status(job_id)
        if not self.claim(job["job_id"]):
            return self.status(job["job_id"])

        context = {
            "doc_id": job["doc_id"],
            "target_group": job["target_group"],
            "use_cache": job["use_cache"],
        }
        try:
            result = self.runner(**context)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            if result is None:
                result = {}
        except Exception as exc:
            self._finish_failed(job["job_id"], exc)
            return self.status(job["job_id"])

        self._finish_succeeded(job["job_id"], result)
        return self.status(job["job_id"])

    def _finish_succeeded(self, job_id: str, result: Any) -> None:
        result_json = json.dumps(result, ensure_ascii=False, default=str)
        finished_at = _now()
        with self.connect() as connection:
            connection.execute(
                """UPDATE pipeline_job_steps
                   SET status = 'succeeded', result_json = ?, finished_at = ?
                   WHERE job_id = ? AND step_name = ?""",
                (result_json, finished_at, job_id, DEFAULT_OPERATION),
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
            connection.execute(
                """UPDATE pipeline_job_steps
                   SET status = 'failed', error_message = ?, finished_at = ?
                   WHERE job_id = ? AND step_name = ?""",
                (error, finished_at, job_id, DEFAULT_OPERATION),
            )
            connection.execute(
                """UPDATE pipeline_jobs
                   SET status = 'failed', current_step = NULL,
                       failed_step = operation, error_message = ?, finished_at = ?
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
        return {
            **self._job_dict(row),
            "current_step": row["current_step"],
            "failed_step": row["failed_step"],
            "error": row["error_message"],
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
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
            "use_cache": bool(row["use_cache"]),
            "operation": row["operation"],
            "status": row["status"],
        }

    def _run_default_operation(
        self,
        *,
        doc_id: str | None,
        target_group: str | None,
        use_cache: bool,
    ) -> dict[str, Any]:
        _ = use_cache
        if doc_id:
            return {
                "doc_ids": [doc_id],
                "summaries": [self._run_document(doc_id)],
            }
        doc_ids = self._document_ids_from_sqlite(target_group or "")
        if not doc_ids:
            raise ValueError(f"没有匹配文档：target_group={target_group}")
        return {
            "doc_ids": doc_ids,
            "summaries": [self._run_document(item) for item in doc_ids],
        }

    def _run_document(self, doc_id: str) -> dict[str, Any]:
        if self.document_locator is not None:
            document_path, extraction_path = self.document_locator(doc_id)
            if extraction_path is None:
                raise ValueError(f"doc_id={doc_id} 缺少已审核抽取结果")
            return self._invoke_offline_pipeline(document_path, extraction_path)

        root = Path(__file__).resolve().parents[3]
        extraction_paths = sorted(
            (root / "data" / "extracted").glob(f"*{doc_id}*.json")
        )
        if not extraction_paths:
            raise ValueError(f"doc_id={doc_id} 缺少已审核抽取结果")
        document_paths = sorted(
            (root / "data" / "documents").glob(f"**/{doc_id}.json")
        )
        if document_paths:
            return self._invoke_offline_pipeline(
                str(document_paths[0]),
                str(extraction_paths[0]),
            )

        document = self._document_from_sqlite(doc_id)
        if document is None:
            raise ValueError(f"没有可执行的标准文档：doc_id={doc_id}")
        with tempfile.TemporaryDirectory(prefix="threatgraph-pipeline-") as directory:
            document_path = Path(directory) / f"{doc_id}.json"
            document_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return self._invoke_offline_pipeline(
                str(document_path),
                str(extraction_paths[0]),
            )

    def _invoke_offline_pipeline(
        self,
        document_path: str,
        extraction_path: str,
    ) -> dict[str, Any]:
        pipeline = self.offline_pipeline or OfflineExtractionPipeline(self.db_path)
        result = pipeline.run(document_path, extraction_path)
        if is_dataclass(result):
            return asdict(result)
        return result

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

    def _documents_table_exists(self, connection: sqlite3.Connection) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'documents'"
            ).fetchone()
            is not None
        )
