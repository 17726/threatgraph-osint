from __future__ import annotations

import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from backend.app.services.demo_store import DemoStore
from backend.app.core.llm_config import has_valid_llm_config


ALLOWED_KEYWORDS = {"APT28", "Kimsuky", "Lazarus"}
MAX_SOURCE_MASK = 4095


class CrawlService:
    def __init__(
        self,
        db_path: str | Path | None = None,
        crawler_base_url: str | None = None,
        store: DemoStore | None = None,
    ) -> None:
        self.store = store or DemoStore(db_path)
        self.crawler_base_url = (
            crawler_base_url or os.getenv("CRAWLER_BASE_URL", "http://crawler:8100")
        ).rstrip("/")
        self.poll_interval = float(os.getenv("CRAWL_POLL_INTERVAL_SECONDS", "0.5"))
        self.max_poll_seconds = float(os.getenv("CRAWL_MAX_POLL_SECONDS", "1800"))
        self.max_poll_failures = int(os.getenv("CRAWL_MAX_POLL_FAILURES", "5"))
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, keyword: str, limit: int, sources: int, filter_enabled: bool) -> dict[str, Any]:
        self.validate_request(keyword, limit, sources, filter_enabled)
        if not has_valid_llm_config():
            raise LLMNotConfiguredError("无有效 LLM 配置")
        with self._lock:
            if any(run["status"] in {"pending", "running"} for run in self._runs.values()):
                raise RuntimeError("已有采集任务正在运行")
            run_id = f"crawl_{int(time.time())}_{secrets.token_hex(4)}"
            run = self._new_run(run_id, keyword, limit, sources, filter_enabled)
            self._runs[run_id] = run
            result = self.public_status(run)
        threading.Thread(target=self._run, args=(run_id,), daemon=True).start()
        return result

    def status(self, crawl_run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._runs.get(crawl_run_id)
            if run is None:
                raise KeyError(crawl_run_id)
            return self.public_status(run)

    @staticmethod
    def validate_request(keyword: str, limit: int, sources: int, filter_enabled: bool) -> None:
        if keyword not in ALLOWED_KEYWORDS:
            raise ValueError("keyword 必须是 APT28、Kimsuky 或 Lazarus")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit 必须是正整数")
        if not isinstance(sources, int) or isinstance(sources, bool) or not 1 <= sources <= MAX_SOURCE_MASK:
            raise ValueError("sources 必须是 1 到 4095 之间的整数")
        if not isinstance(filter_enabled, bool):
            raise ValueError("filter 必须是布尔值")

    def next_start_number(self, keyword: str) -> int:
        group_slug = keyword.lower()
        maximum = 0
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT doc_id FROM documents WHERE lower(target_group) = lower(?)",
                (keyword,),
            ).fetchall()
        for row in rows:
            prefix, separator, number = row["doc_id"].rpartition("_")
            if separator and prefix.lower() == group_slug and number.isdigit():
                maximum = max(maximum, int(number))
        return maximum + 1

    def _run(self, run_id: str) -> None:
        try:
            with self._lock:
                run = self._runs[run_id]
                run["status"] = "running"
                keyword = run["keyword"]
                payload = {
                    "crawl_run_id": run_id,
                    "keyword": keyword,
                    "limit": run["limit"],
                    "sources": run["sources"],
                    "filter": run["filter"],
                    "start_number": self.next_start_number(keyword),
                }
            response = httpx.post(
                f"{self.crawler_base_url}/api/v1/crawl/runs",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            self._poll(run_id)
        except Exception as exc:
            self._finish(run_id, status="failed", error_message=str(exc))

    def _poll(self, run_id: str) -> None:
        started_at = time.monotonic()
        failures = 0
        while True:
            if time.monotonic() - started_at >= self.max_poll_seconds:
                raise TimeoutError("crawler 任务轮询超时")
            try:
                response = httpx.get(
                    f"{self.crawler_base_url}/api/v1/crawl/runs/{run_id}",
                    timeout=30,
                )
                response.raise_for_status()
                crawler_run = response.json()
                failures = 0
            except Exception:
                failures += 1
                if failures >= self.max_poll_failures:
                    raise RuntimeError("连续查询 crawler 状态失败") from None
                time.sleep(self.poll_interval)
                continue
            self._merge_crawler_status(run_id, crawler_run)
            if crawler_run.get("status") in {"succeeded", "failed"}:
                return
            if crawler_run.get("status") not in {"pending", "running"}:
                raise RuntimeError("crawler 返回未知任务状态")
            time.sleep(self.poll_interval)

    def _merge_crawler_status(self, run_id: str, crawler_run: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs[run_id]
            for key in (
                "items_found",
                "items_promoted",
                "items_imported",
                "items_skipped",
                "items_failed",
                "items_pipeline_succeeded",
                "items_pipeline_failed",
                "document_ids",
                "source_results",
                "workspace_cleaned",
                "error_message",
            ):
                if key in crawler_run:
                    run[key] = crawler_run[key]
            if crawler_run.get("status") in {"succeeded", "failed"}:
                run["status"] = crawler_run["status"]

    def _finish(self, run_id: str, status: str, error_message: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            run["status"] = status
            run["error_message"] = error_message

    @staticmethod
    def _new_run(run_id: str, keyword: str, limit: int, sources: int, filter_enabled: bool) -> dict[str, Any]:
        return {
            "crawl_run_id": run_id,
            "keyword": keyword,
            "limit": limit,
            "sources": sources,
            "filter": filter_enabled,
            "status": "pending",
            "items_found": 0,
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 0,
            "items_pipeline_succeeded": 0,
            "items_pipeline_failed": 0,
            "document_ids": [],
            "source_results": {},
            "workspace_cleaned": False,
            "error_message": None,
        }
    @staticmethod
    def public_status(run: dict[str, Any]) -> dict[str, Any]:
        return {
            key: run[key]
            for key in (
                "crawl_run_id",
                "keyword",
                "status",
                "items_found",
                "items_promoted",
                "items_imported",
                "items_skipped",
                "items_failed",
                "items_pipeline_succeeded",
                "items_pipeline_failed",
                "document_ids",
                "source_results",
                "workspace_cleaned",
                "error_message",
            )
        }


class LLMNotConfiguredError(RuntimeError):
    """Raised before a crawl task can start without live LLM configuration."""
