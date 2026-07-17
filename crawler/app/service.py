from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import httpx


TERMINAL_STATUSES = {"succeeded", "partial_success", "failed"}
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
# 复用 Uvicorn 已配置的 logger，确保 crawler 子进程事件输出到容器日志。
LOGGER = logging.getLogger("uvicorn.error")
MAX_EVENTS = 100


class CrawlerService:
    def __init__(
        self,
        workspace_root: Path | None = None,
        backend_base_url: str | None = None,
        artifact_root: Path | None = None,
    ):
        self.workspace_root = workspace_root or Path(os.getenv("CRAWLER_WORKSPACE", "/tmp/threatgraph-crawler"))
        self.backend_base_url = (backend_base_url or os.getenv("BACKEND_BASE_URL", "http://backend:8000")).rstrip("/")
        configured_artifact_root = os.getenv("CRAWLER_ARTIFACT_ROOT")
        self.artifact_root = (
            artifact_root
            or (Path(configured_artifact_root) if configured_artifact_root else None)
            or (workspace_root.parent / "crawl_runs" if workspace_root else Path("/app/data/crawl_runs"))
        )
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
                "pipeline": None,
                "events": [
                    {
                        "sequence": 1,
                        "level": "info",
                        "phase": "pending",
                        "message": "采集任务已创建",
                        "doc_id": None,
                        "source": None,
                        "job_id": None,
                        "details": {},
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                ],
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
                "filter_summary": None,
                "artifact_path": None,
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
        event = None
        with self._lock:
            if run_id in self._runs:
                run = self._runs[run_id]
                previous = run.get("progress") or {}
                changed = any(
                    previous.get(key) != progress.get(key)
                    for key in ("phase", "source", "message")
                )
                run["progress"] = dict(progress)
                if changed:
                    event = self._append_event_locked(
                        run,
                        phase=str(progress.get("phase") or "running"),
                        message=str(progress.get("message") or "任务正在执行"),
                        source=progress.get("source"),
                        details={
                            "current": progress.get("current", 0),
                            "total": progress.get("total", 0),
                        },
                    )
        if event is not None:
            LOGGER.info(
                "crawl_event crawl_run_id=%s phase=%s progress=%s/%s source=%s message=%s",
                run_id,
                event["phase"],
                progress.get("current", 0),
                progress.get("total", 0),
                event.get("source") or "-",
                event["message"],
            )

    @staticmethod
    def _append_event_locked(
        run: dict[str, Any],
        *,
        phase: str,
        message: str,
        level: str = "info",
        doc_id: str | None = None,
        source: str | None = None,
        job_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events = run.setdefault("events", [])
        event = {
            "sequence": (events[-1]["sequence"] + 1) if events else 1,
            "level": level,
            "phase": phase,
            "message": message,
            "doc_id": doc_id,
            "source": source,
            "job_id": job_id,
            "details": details or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        events.append(event)
        if len(events) > MAX_EVENTS:
            del events[:-MAX_EVENTS]
        return event

    def _publish_pipeline_status(
        self,
        run_id: str,
        *,
        target: str,
        doc_id: str,
        source: str | None,
        current: int,
        total: int,
        pipeline: dict[str, Any],
        phase: str,
        message: str,
        level: str = "info",
    ) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            previous = run.get("pipeline") or {}
            previous_progress = previous.get("progress") or {}
            changed = (
                previous.get("status") != pipeline.get("status")
                or previous_progress.get("phase") != (pipeline.get("progress") or {}).get("phase")
            )
            run["pipeline"] = dict(pipeline)
            run["progress"] = {
                "phase": "pipeline",
                "current": current,
                "total": total,
                "target": target,
                "source": source,
                "message": message,
                "doc_id": doc_id,
                "job_id": pipeline.get("job_id"),
                "percent": (pipeline.get("progress") or {}).get("percent", 0),
            }
            event = None
            if changed:
                event = self._append_event_locked(
                    run,
                    phase=phase,
                    message=message,
                    level=level,
                    doc_id=doc_id,
                    source=source,
                    job_id=pipeline.get("job_id"),
                    details={"pipeline_status": pipeline.get("status")},
                )
        if event is not None:
            log_method = LOGGER.error if level == "error" else LOGGER.info
            log_method(
                "crawl_event crawl_run_id=%s phase=%s doc_id=%s source=%s job_id=%s message=%s",
                run_id,
                phase,
                doc_id,
                source or "-",
                pipeline.get("job_id") or "-",
                message,
            )

    def _publish_filter_summary(self, run_id: str, summary: dict[str, Any]) -> None:
        errors = int(summary.get("errors", 0))
        if errors <= 0:
            return
        message = (
            f"过滤部分完成：保留 {summary.get('kept', 0)}，"
            f"丢弃 {summary.get('discarded', 0)}，失败 {errors}；继续处理成功文档"
        )
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            event = self._append_event_locked(
                run,
                phase="filter_partial",
                message=message,
                level="warning",
                details={
                    "total": summary.get("total", 0),
                    "kept": summary.get("kept", 0),
                    "discarded": summary.get("discarded", 0),
                    "errors": errors,
                },
            )
        LOGGER.warning(
            "crawl_event crawl_run_id=%s phase=%s message=%s details=%s",
            run_id,
            event["phase"],
            event["message"],
            json.dumps(event["details"], ensure_ascii=False),
        )

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
            previous = self._runs.get(payload["crawl_run_id"], {})
            result.setdefault("events", previous.get("events", []))
            result.setdefault("pipeline", previous.get("pipeline"))
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
            "pipeline": None,
            "events": [],
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
            "filter_summary": None,
            "artifact_path": None,
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
            filter_summary = self._read_json(workspace / "data" / "filter-result.json")
            if filter_summary:
                self._publish_filter_summary(run_id, filter_summary)
            result.update(self._import_documents(payload))
            if filter_summary:
                result["filter_summary"] = filter_summary
                result["items_failed"] += int(filter_summary.get("errors", 0))
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
            try:
                result["artifact_path"] = self._archive_workspace(run_id, workspace)
            except Exception as archive_error:
                result["artifact_error"] = str(archive_error)
                result["workspace_cleaned"] = False
            else:
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

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

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
            "filter_summary": None,
            "artifact_path": None,
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
                    pipeline = self._run_live_pipeline(
                        document_id,
                        crawl_run_id=payload["crawl_run_id"],
                        target=payload["keyword"],
                        current=summary["progress"]["current"],
                        total=len(paths),
                        source=source_name,
                    )
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
        with self._lock:
            current_run = self._runs.get(payload["crawl_run_id"], {})
            summary["events"] = list(current_run.get("events", []))
            summary["pipeline"] = current_run.get("pipeline")
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
            "partial_success"
            if result.get("items_pipeline_succeeded", 0) > 0
            and result.get("items_failed", 0) > 0
            else "succeeded"
            if result.get("items_pipeline_succeeded", 0) > 0
            else "failed"
        )
        if result["status"] == "failed":
            result["error_message"] = "没有成功完成任何文档的 live Pipeline"
            result["progress"]["phase"] = "failed"
            result["progress"]["message"] = "采集任务失败"
        elif result["status"] == "partial_success":
            result["progress"]["phase"] = "partial_success"
            result["progress"]["message"] = "采集任务部分成功"
            result["error_message"] = f"{result.get('items_failed', 0)} 篇文档处理失败，其余文档已继续处理"
        else:
            result["progress"]["phase"] = "completed"
            result["progress"]["message"] = "采集任务完成"
        return result

    def _run_live_pipeline(
        self,
        doc_id: str,
        *,
        crawl_run_id: str | None = None,
        target: str = "",
        current: int = 0,
        total: int = 1,
        source: str | None = None,
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.backend_base_url}/api/v1/pipeline/run",
            json={"doc_id": doc_id, "extraction_mode": "live"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        job = payload.get("data", payload)
        job_id = job["job_id"]
        if crawl_run_id is not None:
            self._publish_pipeline_status(
                crawl_run_id,
                target=target,
                doc_id=doc_id,
                source=source,
                current=current,
                total=total,
                pipeline=job,
                phase="pipeline_submitted",
                message=f"已提交文档 Pipeline：{doc_id}",
            )
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            response = httpx.get(
                f"{self.backend_base_url}/api/v1/pipeline/status/{job_id}",
                timeout=30,
            )
            response.raise_for_status()
            current_payload = response.json()
            pipeline_status = current_payload.get("data", current_payload)
            pipeline_progress = pipeline_status.get("progress") or {}
            status = pipeline_status.get("status")
            child_phase = pipeline_progress.get("phase") or status or "running"
            message = pipeline_progress.get("message") or f"文档 Pipeline {status}"
            if crawl_run_id is not None:
                terminal = status in {"succeeded", "failed"}
                event_phase = (
                    "pipeline_completed"
                    if status == "succeeded"
                    else "pipeline_failed"
                    if status == "failed"
                    else f"pipeline_{child_phase}"
                )
                self._publish_pipeline_status(
                    crawl_run_id,
                    target=target,
                    doc_id=doc_id,
                    source=source,
                    current=current + (1 if terminal and status == "succeeded" else 0),
                    total=total,
                    pipeline=pipeline_status,
                    phase=event_phase,
                    message=message,
                    level="error" if status == "failed" else "info",
                )
            if status in {"succeeded", "failed"}:
                return pipeline_status
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

    def _archive_workspace(self, run_id: str, workspace: Path) -> str:
        """将运行中间产物原子归档到仓库挂载目录。"""
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        target = self.artifact_root / run_id
        staging = self.artifact_root / f".{run_id}.tmp"
        if staging.exists():
            shutil.rmtree(staging)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(workspace, staging)
        staging.rename(target)
        return f"data/crawl_runs/{run_id}"
