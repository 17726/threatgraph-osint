import sqlite3
import threading
import time
import json
from pathlib import Path

import pytest

from backend.app.services.pipeline_service import (
    DEFAULT_OPERATION,
    PipelineService,
)


def test_pipeline_schema_is_persisted(tmp_path):
    db_path = tmp_path / "pipeline.db"

    PipelineService(db_path, runner=lambda **_context: {})

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        job_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(pipeline_jobs)")
        }

    assert {"pipeline_jobs", "pipeline_job_steps"} <= tables
    assert "extraction_mode" in job_columns


def test_pipeline_requires_exactly_one_scope(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})

    with pytest.raises(ValueError, match="doc_id 或 target_group"):
        service.create_job()
    with pytest.raises(ValueError, match="只能提供其中一个"):
        service.create_job(doc_id="doc-1", target_group="APT28")


def test_job_can_only_be_claimed_once(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})
    job = service.create_job(doc_id="doc-1")

    assert service.claim(job["job_id"]) is True
    assert service.claim(job["job_id"]) is False


def test_pipeline_reports_one_real_composite_operation(tmp_path):
    calls = []

    def runner(**context):
        calls.append(context)
        return {"doc_ids": [context["doc_id"]], "graph_updated": True}

    service = PipelineService(tmp_path / "pipeline.db", runner=runner)

    result = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert result["operation"] == "extract_and_build"
    assert result["status"] == "succeeded"
    assert result["result"] == {
        "doc_ids": ["doc-1"],
        "graph_updated": True,
    }
    assert [step["step_name"] for step in result["steps"]] == [
        "extract_and_build"
    ]
    assert calls == [
        {
            "doc_id": "doc-1",
            "target_group": None,
            "extraction_mode": "live",
        }
    ]


def test_pipeline_deduplicates_active_request(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})

    first = service.create_job(doc_id="doc-1")
    second = service.create_job(doc_id="doc-1")

    assert second["job_id"] == first["job_id"]
    assert second["status"] == "pending"


def test_runner_type_error_is_not_retried_without_arguments(tmp_path):
    calls = []

    def runner(**context):
        calls.append(context)
        raise TypeError("业务内部类型错误")

    service = PipelineService(tmp_path / "pipeline.db", runner=runner)

    result = service.run_sync(doc_id="doc-1")

    assert result["status"] == "failed"
    assert result["failed_step"] == DEFAULT_OPERATION
    assert result["error"] == "业务内部类型错误"
    assert len(calls) == 1


def test_target_group_without_documents_table_fails_clearly(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db")

    result = service.run_sync(target_group="missing-group")

    assert result["status"] == "failed"
    assert result["error"] == "没有匹配文档：target_group=missing-group"


def test_service_marks_interrupted_running_job_as_failed(tmp_path):
    db_path = tmp_path / "pipeline.db"
    service = PipelineService(db_path, runner=lambda **_context: {})
    job = service.create_job(doc_id="doc-1")
    assert service.claim(job["job_id"]) is True

    restarted = PipelineService(db_path, runner=lambda **_context: {})
    status = restarted.status(job["job_id"])

    assert status["status"] == "failed"
    assert "进程中断" in status["error"]


def test_pipeline_submit_background_runs_without_blocking_caller(tmp_path):
    started = threading.Event()
    release = threading.Event()

    def runner(**_context):
        started.set()
        release.wait(timeout=2)
        return {"graph_updated": True}

    service = PipelineService(tmp_path / "pipeline.db", runner=runner)

    job = service.submit_background(doc_id="doc-1")

    assert job["status"] == "running"
    assert started.wait(timeout=1)
    release.set()

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        status = service.status(job["job_id"])
        if status["status"] == "succeeded":
            break
        time.sleep(0.01)

    assert status["status"] == "succeeded"
    assert status["result"] == {"graph_updated": True}
    service.close()


def test_pipeline_close_shuts_down_background_executor(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})

    service.close()

    with pytest.raises(RuntimeError):
        service._executor.submit(lambda: None)


def test_duplicate_background_request_is_only_scheduled_once(tmp_path):
    class RecordingExecutor:
        def __init__(self):
            self.calls = []

        def submit(self, function, *args):
            self.calls.append((function, args))

        def shutdown(self, wait=True):
            assert wait is True

    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})
    original_executor = service._executor
    executor = RecordingExecutor()
    service._executor = executor

    first = service.submit_background(doc_id="doc-1")
    second = service.submit_background(doc_id="doc-1")

    assert second["job_id"] == first["job_id"]
    assert len(executor.calls) == 1
    original_executor.shutdown(wait=True)


def test_reviewed_mode_uses_existing_result_without_calling_llm(tmp_path):
    document_path = tmp_path / "document.json"
    extraction_path = tmp_path / "extraction.json"
    document_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")
    extraction_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")
    calls = []

    class FakeExtractionService:
        def extract(self, _document):
            raise AssertionError("reviewed 模式不应调用 LLM")

    class FakeOfflinePipeline:
        def run(self, actual_document_path, actual_extraction_path):
            calls.append((actual_document_path, actual_extraction_path))
            return {"doc_id": "doc-1", "run_id": "reviewed-run"}

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        extraction_service=FakeExtractionService(),
        document_locator=lambda _doc_id: (
            str(document_path),
            str(extraction_path),
        ),
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="reviewed")

    assert job["status"] == "succeeded"
    assert job["operation"] == "import_extraction_and_build"
    assert calls == [(str(document_path), str(extraction_path))]
    service.close()


def test_live_mode_calls_llm_and_uses_temporary_extraction_file(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )
    observed_paths: list[Path] = []

    class FakeExtractionService:
        model = "fake-live-model"
        last_api_observation = {"calls": 1}
        last_warnings = []

        def extract(self, document):
            assert document["doc_id"] == "doc-1"
            return {"doc_id": "doc-1", "run_id": "live-run", "chunks": []}

    class FakeOfflinePipeline:
        def run(self, actual_document_path, actual_extraction_path):
            observed_paths.extend(
                [Path(actual_document_path), Path(actual_extraction_path)]
            )
            assert json.loads(
                Path(actual_extraction_path).read_text(encoding="utf-8")
            )["run_id"] == "live-run"
            return {"doc_id": "doc-1", "run_id": "live-run"}

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        extraction_service=FakeExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert job["status"] == "succeeded"
    assert job["operation"] == "extract_and_build"
    assert job["result"]["summaries"][0]["extraction"]["mode"] == "live"
    assert observed_paths
    assert not observed_paths[1].exists()
    service.close()


def test_live_mode_rejects_target_group_scope(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})

    with pytest.raises(ValueError, match="live.*doc_id"):
        service.create_job(target_group="APT28", extraction_mode="live")

    service.close()
