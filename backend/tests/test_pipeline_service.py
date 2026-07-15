import sqlite3

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

    assert {"pipeline_jobs", "pipeline_job_steps"} <= tables


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

    result = service.run_sync(doc_id="doc-1", use_cache=False)

    assert result["operation"] == DEFAULT_OPERATION == "extract_and_build"
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
            "use_cache": False,
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
    assert result["failed_step"] == "extract_and_build"
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
