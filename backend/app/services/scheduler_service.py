from __future__ import annotations

import asyncio
import inspect
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from backend.app.db.schema import ensure_pipeline_schema


class SchedulerService:
    """进程内扫描文档流水线任务并触发 Neo4j 增量同步。"""

    def __init__(
        self,
        db_path: str | Path,
        pipeline_service: Any,
        *,
        interval_seconds: float | None = None,
        enabled: bool | None = None,
        sync_neo4j: Callable[[], Any] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.pipeline_service = pipeline_service
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else float(os.getenv("THREATGRAPH_SCHEDULER_INTERVAL_SECONDS", "60"))
        )
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("THREATGRAPH_SCHEDULER_ENABLED", "false").lower()
            in {"1", "true", "yes", "on"}
        )
        self.sync_neo4j = sync_neo4j
        self._scan_lock = threading.Lock()
        self._submitted_doc_ids: set[str] = set()
        self._submitted_doc_ids_lock = threading.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._scan_async_lock = asyncio.Lock()
        self._loop_task: asyncio.Task[Any] | None = None
        self._scan_task: asyncio.Task[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        with self.connect() as connection:
            ensure_pipeline_schema(connection)
            connection.commit()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def scan_once(self) -> dict[str, Any]:
        """扫描一次待处理文档，并在有落后变更时触发同步。"""
        if not self._scan_lock.acquire(blocking=False):
            return {"submitted": 0, "failed": [], "synced": 0}
        try:
            submitted = 0
            failed: list[dict[str, Any]] = []
            with self.connect() as connection:
                documents = connection.execute(
                    """
                    SELECT d.doc_id, d.target_group
                    FROM documents AS d
                    WHERE NOT EXISTS (
                        SELECT 1 FROM pipeline_jobs AS j
                        WHERE j.doc_id = d.doc_id AND j.status IN ('pending', 'running', 'succeeded')
                    )
                    ORDER BY d.doc_id
                    """
                ).fetchall()
                for document in documents:
                    doc_id = document["doc_id"]
                    with self._submitted_doc_ids_lock:
                        if doc_id in self._submitted_doc_ids:
                            continue
                    submit = getattr(self.pipeline_service, "submit_background", None)
                    if submit is None:
                        submit = self.pipeline_service.submit
                    try:
                        submit(doc_id=doc_id, target_group=document["target_group"])
                    except Exception as exc:
                        failed.append({"doc_id": doc_id, "retry": True, "error": str(exc)})
                        continue
                    with self._submitted_doc_ids_lock:
                        self._submitted_doc_ids.add(doc_id)
                    submitted += 1

                max_change = connection.execute(
                    "SELECT coalesce(max(change_id), 0) FROM graph_changes"
                ).fetchone()[0]
                watermark_row = connection.execute(
                    "SELECT watermark FROM sync_state WHERE state_key = 'neo4j'"
                ).fetchone()
                watermark = watermark_row[0] if watermark_row else 0

            synced = 0
            if self.sync_neo4j is not None and max_change > watermark:
                result = self.sync_neo4j()
                if inspect.isawaitable(result):
                    self._schedule(result)
                synced = 1
            return {"submitted": submitted, "failed": failed, "synced": synced}
        finally:
            self._scan_lock.release()

    async def start(self) -> None:
        if not self.enabled or self._loop_task is not None and not self._loop_task.done():
            return
        self._loop = asyncio.get_running_loop()
        self._loop_task = asyncio.create_task(self.run_loop())

    async def stop(self) -> None:
        loop_task = self._loop_task
        self._loop_task = None
        if loop_task is not None:
            loop_task.cancel()
            await asyncio.gather(loop_task, return_exceptions=True)
        if self._scan_task is not None:
            await asyncio.gather(self._scan_task, return_exceptions=True)
        self._loop = None
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def run_loop(self) -> None:
        while True:
            self._scan_task = asyncio.create_task(asyncio.to_thread(self.scan_once))
            try:
                await self._scan_task
            finally:
                self._scan_task = None
            await asyncio.sleep(self.interval_seconds)

    def _schedule(self, awaitable: Any) -> None:
        if self._loop is None:
            raise RuntimeError("调度器未启动")
        if inspect.iscoroutine(awaitable):
            task = self._loop.call_soon_threadsafe(self._create_task, awaitable)
            return
        task = self._loop.call_soon_threadsafe(self._create_task, awaitable)

    def _create_task(self, awaitable: Any) -> None:
        task = asyncio.create_task(awaitable)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
