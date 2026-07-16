from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from threading import Lock
from typing import Any

import httpx


TERMINAL_STATUSES = {"succeeded", "failed"}
SOURCE_NAMES = (
    "奇安信威胁情报中心",
    "The Hacker News",
    "Palo Alto Unit 42",
    "FreeBuf",
    "Chainalysis",
    "TRM Labs",
    "Microsoft",
    "SecureList",
    "CrowdStrike",
    "Group-IB",
    "OFAC",
    "FBI",
)


class CrawlerService:
    def __init__(self, workspace_root: Path | None = None, backend_base_url: str | None = None):
        self.workspace_root = workspace_root or Path(os.getenv("CRAWLER_WORKSPACE", "/tmp/threatgraph-crawler"))
        self.backend_base_url = (backend_base_url or os.getenv("BACKEND_BASE_URL", "http://backend:8000")).rstrip("/")
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def submit(self, payload: dict[str, Any]) -> dict[str, str]:
        run_id = payload["crawl_run_id"]
        with self._lock:
            if run_id in self._runs:
                raise KeyError(run_id)
            self._runs[run_id] = {
                "crawl_run_id": run_id,
                "keyword": payload["keyword"],
                "status": "pending",
                "items_found": 0,
                "items_promoted": 0,
                "items_imported": 0,
                "items_skipped": 0,
                "items_failed": 0,
                "items_pipeline_succeeded": 0,
                "items_pipeline_failed": 0,
                "pipeline_error": None,
                "document_ids": [],
            "source_results": self._initial_source_results(payload["sources"]),
                "progress": {
                    "phase": "pending",
                    "current": 0,
                    "total": 0,
                    "target": payload["keyword"],
                    "source": None,
                    "message": "任务排队中",
                },
                "workspace_cleaned": False,
                "error_message": None,
            }
        import threading

        threading.Thread(target=self._run_and_store, args=(payload,), daemon=True).start()
        return {"crawl_run_id": run_id, "status": "accepted"}

    def status(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            return dict(self._runs[run_id])

    def _update_progress(self, run_id: str, progress: dict[str, Any]) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id]["progress"] = dict(progress)

    @staticmethod
    def _empty_source_result() -> dict[str, int]:
        return {
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 0,
            "items_pipeline_succeeded": 0,
        }

    @classmethod
    def _initial_source_results(cls, sources: int) -> dict[str, dict[str, int]]:
        return {
            SOURCE_NAMES[index]: cls._empty_source_result()
            for index in range(len(SOURCE_NAMES))
            if sources & (1 << index)
        }

    def _set_import_progress(
        self,
        run_id: str,
        target: str,
        current: int,
        total: int,
        source: str | None,
    ) -> None:
        self._update_progress(
            run_id,
            {
                "phase": "importing",
                "current": current,
                "total": total,
                "target": target,
                "source": source,
                "message": "正在导入",
            },
        )

    def _run_and_store(self, payload: dict[str, Any]) -> None:
        try:
            result = self._execute(payload)
        except Exception as exc:
            result = self._failed_result(payload, str(exc))
        with self._lock:
            self._runs[payload["crawl_run_id"]] = result

    def _execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload["crawl_run_id"]
        workspace = self.workspace_root / run_id
        result = {
            "crawl_run_id": run_id,
            "keyword": payload["keyword"],
            "status": "failed",
            "items_found": 0,
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 0,
            "items_pipeline_succeeded": 0,
            "items_pipeline_failed": 0,
            "pipeline_error": None,
            "document_ids": [],
            "progress": {
                "phase": "running",
                "current": 0,
                "total": 0,
                "target": payload["keyword"],
                "source": None,
                "message": "任务正在执行",
            },
                "source_results": self._initial_source_results(payload["sources"]),
            "workspace_cleaned": False,
            "error_message": None,
        }
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            result["status"] = "running"
            command = [
                sys.executable,
                "scripts/run_all_crawlers.py",
                "--keyword",
                payload["keyword"],
                "--limit",
                str(payload["limit"]),
                "--sources",
                str(payload["sources"]),
                "--start-number",
                str(payload["start_number"]),
            ]
            if payload.get("filter"):
                command.append("--filter")
            progress_path = workspace / "data" / "progress.json"
            process = subprocess.Popen(
                command,
                cwd="/app",
                env={
                    **os.environ,
                    "CRAWLER_DATA_ROOT": str(workspace / "data"),
                    "CRAWLER_PROGRESS_FILE": str(progress_path),
                },
            )
            while process.poll() is None:
                progress = self._read_progress(progress_path)
                if progress:
                    with self._lock:
                        result["progress"] = progress
                    self._update_progress(run_id, progress)
                time.sleep(0.25)
            return_code = process.returncode or 0
            progress_path = workspace / "data" / "progress.json"
            progress = self._read_progress(progress_path)
            if progress:
                result["progress"] = progress
            pipeline_error = (
                f"crawler pipeline exited with {return_code}"
                if return_code
                else None
            )
            result.update(self._import_documents(payload))
            selected_sources = [
                SOURCE_NAMES[index]
                for index in range(len(SOURCE_NAMES))
                if payload["sources"] & (1 << index)
            ]
            result = self._finalize_result(
                {**payload, "selected_sources": selected_sources},
                result,
                pipeline_error,
            )
            if result["status"] == "failed":
                result["error_message"] = (
                    pipeline_error
                    or result.get("pipeline_error")
                    or "没有成功完成任何文档的 live Pipeline"
                )
            elif pipeline_error:
                result["error_message"] = pipeline_error
        except Exception as exc:
            result["status"] = "failed"
            result["error_message"] = str(exc)
            result["progress"]["phase"] = "failed"
            result["progress"]["message"] = "采集任务失败"
        finally:
            result["workspace_cleaned"] = self._cleanup_workspace(workspace)
        return result

    @staticmethod
    def _read_progress(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        progress = payload.get("progress")
        return progress if isinstance(progress, dict) else None

    @classmethod
    def _failed_result(cls, payload: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "crawl_run_id": payload["crawl_run_id"],
            "keyword": payload.get("keyword", ""),
            "status": "failed",
            "items_found": 0,
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 1,
            "items_pipeline_succeeded": 0,
            "items_pipeline_failed": 0,
            "document_ids": [],
            "source_results": cls._initial_source_results(payload.get("sources", 0)),
            "progress": {
                "phase": "failed",
                "current": 0,
                "total": 0,
                "target": payload.get("keyword", ""),
                "source": None,
                "message": "采集任务失败",
            },
            "workspace_cleaned": False,
            "error_message": message,
        }

    def _import_documents(self, payload: dict[str, Any]) -> dict[str, Any]:
        documents_dir = self.workspace_root / payload["crawl_run_id"] / "data" / "documents"
        summary = {
            "items_found": 0,
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 0,
            "items_pipeline_succeeded": 0,
            "items_pipeline_failed": 0,
            "document_ids": [],
            "source_results": self._initial_source_results(payload.get("sources", 0)),
            "progress": {
                "phase": "importing",
                "current": 0,
                "total": 0,
                "target": payload["keyword"],
                "source": None,
                "message": "正在导入",
            },
        }
        paths = sorted(documents_dir.rglob("*.json")) if documents_dir.exists() else []
        summary["items_promoted"] = len(paths)
        summary["progress"]["total"] = len(paths)
        self._set_import_progress(
            payload["crawl_run_id"], payload["keyword"], 0, len(paths), None
        )
        for path in paths:
            source = None
            try:
                document = json.loads(path.read_text(encoding="utf-8-sig"))
                summary["items_found"] += 1
                source_name = str(document.get("source_name", "unknown")).strip() or "unknown"
                source = summary["source_results"].setdefault(
                    source_name, self._empty_source_result()
                )
                source["items_promoted"] += 1
                response = httpx.post(
                    f"{self.backend_base_url}/api/v1/documents/import",
                    json=document,
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json().get("data", response.json())
                document_id = data.get("doc_id", document.get("doc_id"))
                summary["progress"]["source"] = source_name
                self._set_import_progress(
                    payload["crawl_run_id"],
                    payload["keyword"],
                    summary["progress"]["current"],
                    len(paths),
                    source_name,
                )
                if data.get("status") == "skipped":
                    summary["items_skipped"] += 1
                    source["items_skipped"] += 1
                else:
                    summary["items_imported"] += 1
                    source["items_imported"] += 1
                summary["document_ids"].append(document_id)
                try:
                    pipeline = self._run_live_pipeline(document_id)
                    if pipeline["status"] == "succeeded":
                        summary["items_pipeline_succeeded"] += 1
                        source["items_pipeline_succeeded"] += 1
                    else:
                        summary["items_pipeline_failed"] += 1
                        summary["items_failed"] += 1
                        source["items_failed"] += 1
                except Exception as exc:
                    summary["items_pipeline_failed"] += 1
                    summary["items_failed"] += 1
                    source["items_failed"] += 1
                    summary["pipeline_error"] = str(exc)
            except Exception as exc:
                summary["items_failed"] += 1
                summary["pipeline_error"] = str(exc)
                if source is not None:
                    source["items_failed"] += 1
            summary["progress"]["current"] += 1
            self._set_import_progress(
                payload["crawl_run_id"],
                payload["keyword"],
                summary["progress"]["current"],
                len(paths),
                None,
            )
        summary["progress"]["source"] = None
        return summary

    def _finalize_result(
        self,
        payload: dict[str, Any],
        result: dict[str, Any],
        pipeline_error: str | None,
    ) -> dict[str, Any]:
        if "progress" not in result:
            result["progress"] = {
                "phase": "running",
                "current": 0,
                "total": 0,
                "target": payload.get("keyword", ""),
                "source": None,
                "message": "任务正在执行",
            }
        if pipeline_error:
            result["status"] = "failed"
            result["error_message"] = pipeline_error
            result["progress"]["phase"] = "failed"
            result["progress"]["message"] = "采集任务失败"
            return result

        result["status"] = (
            "succeeded" if result.get("items_pipeline_succeeded", 0) > 0 else "failed"
        )
        if result["status"] == "failed":
            result["error_message"] = "没有成功完成任何文档的 live Pipeline"
            result["progress"]["phase"] = "failed"
            result["progress"]["message"] = "采集任务失败"
        else:
            result["progress"]["phase"] = "completed"
            result["progress"]["message"] = "采集任务完成"
        return result

    def _run_live_pipeline(self, doc_id: str) -> dict[str, Any]:
        response = httpx.post(
            f"{self.backend_base_url}/api/v1/pipeline/run",
            json={"doc_id": doc_id, "extraction_mode": "live"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        job = payload.get("data", payload)
        job_id = job["job_id"]
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            response = httpx.get(
                f"{self.backend_base_url}/api/v1/pipeline/status/{job_id}",
                timeout=30,
            )
            response.raise_for_status()
            current_payload = response.json()
            current = current_payload.get("data", current_payload)
            if current.get("status") in {"succeeded", "failed"}:
                return current
            time.sleep(0.5)
        raise TimeoutError(f"live Pipeline 超时: {job_id}")

    @staticmethod
    def _cleanup_workspace(workspace: Path) -> bool:
        try:
            if workspace.exists():
                shutil.rmtree(workspace)
            return True
        except OSError:
            return False
