from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from backend.app.db.schema import ensure_pipeline_schema
from backend.app.services.llm_service import LLMExtractionService
from backend.app.services.neo4j_service import Neo4jService
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline


DEFAULT_STEPS = [
    "extract",
    "normalize",
    "build_graph",
    "analyze_behavior",
    "infer",
    "report",
    "neo4j_sync",
]

_ALLOWED_STATUSES = {"pending", "running", "succeeded", "failed", "skipped"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PipelineService:
    def __init__(
        self,
        db_path: str | Path,
        *,
        steps: dict[str, Callable[..., Any]] | None = None,
        max_workers: int = 2,
        offline_pipeline: Any | None = None,
        neo4j_service: Any | None = None,
        extraction_service: Any | None = None,
        document_locator: Callable[[str], tuple[str, str | None]] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.steps = dict(steps or {})
        self.offline_pipeline = offline_pipeline
        self.neo4j_service = neo4j_service
        self.extraction_service = extraction_service or LLMExtractionService()
        self.document_locator = document_locator
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pipeline",
        )
        self._initialize()

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            ensure_pipeline_schema(connection)

    def _validate_steps(self, steps: list[str] | None) -> list[str]:
        selected = list(steps) if steps is not None else list(DEFAULT_STEPS)
        unknown = [step for step in selected if step not in DEFAULT_STEPS]
        if unknown:
            raise ValueError(f"未知流水线步骤: {', '.join(unknown)}")
        if len(set(selected)) != len(selected):
            raise ValueError("流水线步骤不能重复")
        return selected

    def _find_existing_job(
        self,
        connection: sqlite3.Connection,
        doc_id: str | None,
        target_group: str | None,
        steps_json: str,
        use_cache: bool,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT * FROM pipeline_jobs
            WHERE ((doc_id IS ? AND target_group IS ?) OR (doc_id = ? AND target_group = ?))
              AND steps_json = ? AND use_cache = ?
              AND status IN ('pending', 'running')
            ORDER BY created_at DESC LIMIT 1
            """,
            (doc_id, target_group, doc_id, target_group, steps_json, int(use_cache)),
        ).fetchone()

    def submit(
        self,
        *,
        doc_id: str | None = None,
        target_group: str | None = None,
        use_cache: bool = True,
        steps: list[str] | None = None,
    ) -> dict[str, Any]:
        selected = self._validate_steps(steps)
        steps_json = json.dumps(selected, ensure_ascii=False)
        with self.connect() as connection:
            existing = self._find_existing_job(
                connection, doc_id, target_group, steps_json, use_cache
            )
            if existing:
                return self._job_dict(existing)
            job_id = f"job_{uuid.uuid4().hex}"
            created_at = _now()
            connection.execute(
                """
                INSERT INTO pipeline_jobs
                (job_id, doc_id, target_group, use_cache, steps_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (job_id, doc_id, target_group, int(use_cache), steps_json, created_at),
            )
            connection.executemany(
                """
                INSERT INTO pipeline_job_steps (job_id, step_name, step_order, status)
                VALUES (?, ?, ?, 'pending')
                """,
                [(job_id, step, index) for index, step in enumerate(selected)],
            )
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            return self._job_dict(row)

    def submit_background(self, **kwargs: Any) -> dict[str, Any]:
        job = self.submit(**kwargs)
        if job["status"] == "pending":
            self._executor.submit(self._run_job, job["job_id"])
        return job

    async def run_async(self, **kwargs: Any) -> dict[str, Any]:
        job = self.submit(**kwargs)
        if job["status"] == "pending":
            return await asyncio.to_thread(self._run_job, job["job_id"])
        return self.status(job["job_id"])

    def run_sync(self, **kwargs: Any) -> dict[str, Any]:
        job = self.submit(**kwargs)
        if job["status"] == "pending":
            return self._run_job(job["job_id"])
        return self.status(job["job_id"])

    def _default_step(self, step_name: str, context: dict[str, Any]) -> dict[str, Any]:
        if step_name == "extract":
            doc_id = context.get("doc_id")
            target_group = context.get("target_group")
            if doc_id:
                return self._extract_document(doc_id)
            if target_group:
                doc_ids = self._document_ids_from_sqlite(target_group)
                if not doc_ids:
                    raise ValueError(f"没有匹配文档：target_group={target_group}")
                summaries = [self._extract_document(item_doc_id) for item_doc_id in doc_ids]
                return {"doc_ids": doc_ids, "summaries": summaries}
            raise ValueError("没有可执行的抽取输入：必须提供 doc_id 或 target_group")
        if step_name in {"normalize", "build_graph", "analyze_behavior", "infer", "report"}:
            return {"status": "skipped", "reason": "included_in_extract"}
        if step_name == "neo4j_sync":
            if self.neo4j_service is None:
                return {"status": "not_configured"}
            return self.neo4j_service.sync_incremental()
        raise ValueError(f"未知流水线步骤: {step_name}")

    def _extract_document(self, doc_id: str) -> dict[str, Any]:
        document_path, extraction_path = self._locate_inputs(doc_id)
        if extraction_path is None:
            document = json.loads(Path(document_path).read_text(encoding="utf-8"))
            extraction_result = self.extraction_service.extract(document)
            if inspect.isawaitable(extraction_result):
                extraction_result = asyncio.run(extraction_result)
            extraction_path = self._write_extraction_input(doc_id, extraction_result)
        pipeline = self.offline_pipeline or OfflineExtractionPipeline(self.db_path)
        result = pipeline.run(document_path, extraction_path)
        return {
            "doc_id": doc_id,
            "document_path": str(document_path),
            "extraction_path": str(extraction_path),
            "summary": asdict(result) if hasattr(result, "_fields") or hasattr(result, "__dataclass_fields__") else result,
        }

    def _document_ids_from_sqlite(self, target_group: str) -> list[str]:
        with self.connect() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
            ).fetchone()
            if table is None:
                return []
            rows = connection.execute(
                "SELECT doc_id FROM documents WHERE target_group = ? ORDER BY doc_id",
                (target_group,),
            ).fetchall()
        return [row["doc_id"] for row in rows]

    def _write_extraction_input(self, doc_id: str, extraction_result: dict[str, Any]) -> Path:
        output_dir = self.db_path.parent / "pipeline_extracted"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{doc_id}.json"
        output_path.write_text(
            json.dumps(extraction_result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def _write_document_input(self, document: dict[str, Any]) -> Path:
        output_dir = self.db_path.parent / "pipeline_documents"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{document['doc_id']}.json"
        output_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def _document_from_sqlite(self, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
            ).fetchone()
            if table is None:
                return None
            row = connection.execute(
                "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
        if row is None:
            return None
        document = dict(row)
        for column, output in (
            ("target_groups_json", "target_groups"),
            ("tags_json", "tags"),
            ("metadata_json", "metadata"),
        ):
            if column in document:
                document[output] = json.loads(document.pop(column) or ("{}" if output == "metadata" else "[]"))
        document.pop("created_at", None)
        return document

    def _locate_inputs(self, doc_id: str) -> tuple[str, str | None]:
        if self.document_locator is not None:
            return self.document_locator(doc_id)
        document = self._document_from_sqlite(doc_id)
        if document is not None:
            return str(self._write_document_input(document)), None
        root = Path(__file__).resolve().parents[3]
        document_paths = list((root / "data" / "documents").glob(f"**/{doc_id}.json"))
        extraction_paths = list((root / "data" / "extracted").glob(f"*{doc_id}*.json"))
        if not document_paths:
            raise ValueError(
                f"没有可执行的抽取输入：doc_id={doc_id} 缺少标准文档"
            )
        return str(document_paths[0]), str(extraction_paths[0]) if extraction_paths else None

    def _invoke_step(self, step_name: str, context: dict[str, Any]) -> Any:
        function = self.steps.get(step_name)
        if function is None:
            return self._default_step(step_name, context)
        try:
            signature = inspect.signature(function)
            if any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            ):
                return function(**context)
            named = {
                name: context[name]
                for name in signature.parameters
                if name in context
            }
            if named:
                return function(**named)
        except (TypeError, ValueError):
            pass
        return function()

    def _run_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"流水线任务不存在: {job_id}")
            context = {
                "job_id": row["job_id"],
                "doc_id": row["doc_id"],
                "target_group": row["target_group"],
                "use_cache": bool(row["use_cache"]),
            }
            step_names = json.loads(row["steps_json"])
            started_at = _now()
            connection.execute(
                "UPDATE pipeline_jobs SET status = 'running', started_at = ? WHERE job_id = ?",
                (started_at, job_id),
            )
            connection.commit()

        results: dict[str, Any] = {}
        try:
            for step_name in step_names:
                step_started = _now()
                with self.connect() as connection:
                    connection.execute(
                        "UPDATE pipeline_jobs SET current_step = ? WHERE job_id = ?",
                        (step_name, job_id),
                    )
                    connection.execute(
                        """UPDATE pipeline_job_steps SET status = 'running', started_at = ?
                           WHERE job_id = ? AND step_name = ?""",
                        (step_started, job_id, step_name),
                    )
                    connection.commit()
                result = self._invoke_step(step_name, {**context, **results})
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
                if result is None:
                    result = {}
                results[step_name] = result
                with self.connect() as connection:
                    connection.execute(
                        """UPDATE pipeline_job_steps
                           SET status = 'succeeded', result_json = ?, finished_at = ?
                           WHERE job_id = ? AND step_name = ?""",
                        (json.dumps(result, ensure_ascii=False, default=str), _now(), job_id, step_name),
                    )
                    connection.commit()
        except Exception as exc:
            failed_step = step_name
            error = str(exc) or exc.__class__.__name__
            with self.connect() as connection:
                connection.execute(
                    """UPDATE pipeline_job_steps
                       SET status = 'failed', error_message = ?, finished_at = ?
                       WHERE job_id = ? AND step_name = ?""",
                    (error, _now(), job_id, failed_step),
                )
                connection.execute(
                    """UPDATE pipeline_jobs SET status = 'failed', current_step = NULL,
                       failed_step = ?, error_message = ?, result_json = ?, finished_at = ?
                       WHERE job_id = ?""",
                    (failed_step, error, json.dumps(results, ensure_ascii=False, default=str), _now(), job_id),
                )
                connection.commit()
            return self.status(job_id)

        with self.connect() as connection:
            connection.execute(
                """UPDATE pipeline_jobs SET status = 'succeeded', current_step = NULL,
                   result_json = ?, finished_at = ? WHERE job_id = ?""",
                (json.dumps(results, ensure_ascii=False, default=str), _now(), job_id),
            )
            connection.commit()
        return self.status(job_id)

    def _job_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "doc_id": row["doc_id"],
            "target_group": row["target_group"],
            "use_cache": bool(row["use_cache"]),
            "steps": json.loads(row["steps_json"]),
            "status": row["status"],
        }

    def status(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"流水线任务不存在: {job_id}")
            steps = connection.execute(
                """SELECT step_name, step_order, status, result_json, error_message,
                          started_at, finished_at
                   FROM pipeline_job_steps WHERE job_id = ? ORDER BY step_order""",
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
