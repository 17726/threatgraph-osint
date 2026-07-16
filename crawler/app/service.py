from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from threading import Lock
from typing import Any

import httpx


TERMINAL_STATUSES = {"succeeded", "failed"}


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
                "document_ids": [],
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
            "document_ids": [],
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
            completed = subprocess.run(
                command,
                cwd="/app",
                env={**os.environ, "CRAWLER_DATA_ROOT": str(workspace / "data")},
                check=False,
            )
            pipeline_error = (
                f"crawler pipeline exited with {completed.returncode}"
                if completed.returncode
                else None
            )
            result.update(self._import_documents(payload))
            result["status"] = "succeeded" if result["items_imported"] > 0 else "failed"
            if result["status"] == "failed":
                result["error_message"] = pipeline_error or "没有成功导入任何文档"
            elif pipeline_error:
                result["error_message"] = pipeline_error
        except Exception as exc:
            result["status"] = "failed"
            result["error_message"] = str(exc)
        finally:
            result["workspace_cleaned"] = self._cleanup_workspace(workspace)
        return result

    @staticmethod
    def _failed_result(payload: dict[str, Any], message: str) -> dict[str, Any]:
        return {
            "crawl_run_id": payload["crawl_run_id"],
            "keyword": payload.get("keyword", ""),
            "status": "failed",
            "items_found": 0,
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 1,
            "document_ids": [],
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
            "document_ids": [],
        }
        paths = sorted(documents_dir.rglob("*.json")) if documents_dir.exists() else []
        summary["items_promoted"] = len(paths)
        for path in paths:
            try:
                document = json.loads(path.read_text(encoding="utf-8-sig"))
                response = httpx.post(
                    f"{self.backend_base_url}/api/v1/documents/import",
                    json=document,
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json().get("data", response.json())
                summary["items_found"] += 1
                if data.get("status") == "skipped":
                    summary["items_skipped"] += 1
                else:
                    summary["items_imported"] += 1
                    summary["document_ids"].append(data.get("doc_id", document.get("doc_id")))
            except Exception:
                summary["items_failed"] += 1
        return summary

    @staticmethod
    def _cleanup_workspace(workspace: Path) -> bool:
        try:
            if workspace.exists():
                shutil.rmtree(workspace)
            return True
        except OSError:
            return False
