import hashlib
import json

import pytest

from backend.app.services.pipeline_run_archive import PipelineRunArchive


GENERATED_AT = "2026-07-15T16:40:54.539671+00:00"
RUN_ID = (
    "extract-doc-1-fake-live-model-1.0-1.0-"
    "20260715164054539671-8210bd88"
)


def extraction_result() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "doc_id": "doc-1",
        "model_name": "fake-live-model",
        "prompt_version": "1.0",
        "generated_at": GENERATED_AT,
        "chunks": [],
    }


def candidate_audit() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "doc_id": "doc-1",
        "model_name": "fake-live-model",
        "prompt_version": "1.0",
        "generated_at": GENERATED_AT,
        "chunks": [],
    }


def test_live_archive_persists_artifacts_and_succeeded_run_log(tmp_path):
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )

    log_path = archive.start(
        job_id="job-1",
        doc_id="doc-1",
        operation="extract_and_build",
    )
    artifacts = archive.attach_extraction(
        "job-1",
        extraction_result(),
        candidate_audit(),
        llm={"calls": 1, "usage": {"total_tokens": 42}},
        warnings=["测试警告"],
    )
    archive.succeed("job-1", {"canonical_entities": 2})

    result_path = tmp_path / artifacts["result_path"]
    audit_path = tmp_path / artifacts["candidate_audit_path"]
    run_log = json.loads(log_path.read_text(encoding="utf-8"))
    assert result_path.is_file()
    assert audit_path.is_file()
    assert run_log["status"] == "succeeded"
    assert run_log["run_id"] == RUN_ID
    assert run_log["artifacts"] == artifacts
    assert run_log["llm"]["calls"] == 1
    assert run_log["warnings"] == ["测试警告"]
    assert run_log["result"] == {"canonical_entities": 2}
    assert artifacts["result_sha256"] == hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
    assert artifacts["candidate_audit_sha256"] == hashlib.sha256(
        audit_path.read_bytes()
    ).hexdigest()


def test_live_archive_keeps_failed_run_log(tmp_path):
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    log_path = archive.start(
        job_id="job-failed",
        doc_id="doc-1",
        operation="extract_and_build",
    )

    archive.fail("job-failed", "模型不可用")

    run_log = json.loads(log_path.read_text(encoding="utf-8"))
    assert run_log["status"] == "failed"
    assert run_log["error"] == "模型不可用"
    assert run_log["finished_at"]


def test_live_archive_marks_existing_running_log_interrupted(tmp_path):
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    log_path = archive.start(
        job_id="job-interrupted",
        doc_id="doc-1",
        operation="extract_and_build",
    )

    assert archive.fail_if_started("job-interrupted", "服务进程中断") is True

    run_log = json.loads(log_path.read_text(encoding="utf-8"))
    assert run_log["status"] == "failed"
    assert run_log["error"] == "服务进程中断"
    assert archive.fail_if_started("missing", "服务进程中断") is False


def test_live_archive_rejects_output_directory_outside_path_root(tmp_path):
    outside = tmp_path.parent / "outside"

    with pytest.raises(ValueError, match="必须位于配置根目录内"):
        PipelineRunArchive(
            extraction_dir=outside / "extracted",
            run_log_dir=tmp_path / "run_logs",
            path_root=tmp_path,
        )

    assert not outside.exists()
