import sqlite3
import threading
import time
import json
from pathlib import Path

import pytest

from backend.app.services import pipeline_service as pipeline_service_module
from backend.app.services.pipeline_run_archive import PipelineRunArchive
from backend.app.services.pipeline_service import (
    DEFAULT_OPERATION,
    PipelineService,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
APT28_DOCUMENT_PATH = REPO_ROOT / "data/documents/apt28/apt28_080.json"
APT28_EXTRACTION_PATH = REPO_ROOT / (
    "data/extracted/"
    "extract-apt28_080-deepseek-v4-flash-1.0-1.0-"
    "20260714075123666577-c463deb3.json"
)
APT28_AUDIT_PATH = REPO_ROOT / (
    "data/extracted/"
    "extract-apt28_080-deepseek-v4-flash-1.0-1.0-"
    "20260714075123666577-c463deb3-candidate-audit.json"
)


def _copy_json(source: Path, target: Path) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _selector():
    selector = getattr(
        pipeline_service_module,
        "select_reviewed_extraction",
        None,
    )
    assert callable(selector), "缺少显式的 reviewed 工件选择器"
    return selector


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

    assert {"pipeline_jobs", "pipeline_job_steps", "pipeline_job_events"} <= tables
    assert "extraction_mode" in job_columns


def test_pipeline_observability_exposes_progress_and_ordered_events(tmp_path):
    service = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {"graph_updated": True},
    )

    result = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert result["progress"] == {
        "phase": "completed",
        "current": 1,
        "total": 1,
        "percent": 100,
        "message": "流水线执行完成",
        "doc_id": "doc-1",
        "updated_at": result["finished_at"],
    }
    assert [event["phase"] for event in result["events"]] == [
        "pending",
        "running",
        "completed",
    ]
    assert [event["sequence"] for event in result["events"]] == [1, 2, 3]
    assert all(event["job_id"] == result["job_id"] for event in result["events"])
    assert result["events"][-1]["details"] == {"graph_updated": True}
    service.close()


def test_pipeline_observability_preserves_failure_context(tmp_path):
    def failing_runner(**_context):
        raise RuntimeError("审核工件不可用")

    service = PipelineService(tmp_path / "pipeline.db", runner=failing_runner)

    result = service.run_sync(doc_id="doc-bad", extraction_mode="reviewed")

    assert result["status"] == "failed"
    assert result["progress"]["phase"] == "failed"
    assert result["progress"]["doc_id"] == "doc-bad"
    assert result["progress"]["message"] == "审核工件不可用"
    assert result["events"][-1]["level"] == "error"
    assert result["events"][-1]["details"] == {
        "error_type": "RuntimeError",
        "failed_step": "import_extraction_and_build",
    }
    service.close()


def test_pipeline_observability_reports_real_default_operation_boundaries(tmp_path):
    document_path = tmp_path / "document.json"
    extraction_path = tmp_path / "extraction.json"
    document_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")
    extraction_path.write_text('{"run_id":"run-1"}', encoding="utf-8")

    class FakeOfflinePipeline:
        def run(self, _document_path, _extraction_path):
            return {"canonical_entities": 2, "canonical_relations": 1}

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        document_locator=lambda _doc_id: (str(document_path), str(extraction_path)),
        projection_sync=lambda: {"status": "succeeded", "changes": 3},
    )

    result = service.run_sync(doc_id="doc-1", extraction_mode="reviewed")

    phases = [event["phase"] for event in result["events"]]
    assert phases == [
        "pending",
        "running",
        "resolving_scope",
        "locating_inputs",
        "loading_reviewed",
        "building_graph",
        "document_completed",
        "syncing_projection",
        "completed",
    ]
    assert result["events"][4]["details"]["extraction_path"].endswith(
        "extraction.json"
    )
    assert result["events"][6]["details"]["canonical_entities"] == 2
    service.close()


def test_pipeline_observability_emits_docker_visible_structured_log(tmp_path, caplog):
    service = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {"graph_updated": True},
    )

    with caplog.at_level("INFO", logger="uvicorn.error"):
        result = service.run_sync(doc_id="doc-log", extraction_mode="reviewed")

    assert any(
        "pipeline_event" in record.message
        and result["job_id"] in record.message
        and "phase=completed" in record.message
        for record in caplog.records
    )
    service.close()


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


def test_default_pipeline_triggers_projection_sync_after_sqlite_import(tmp_path):
    document_path = tmp_path / "document.json"
    extraction_path = tmp_path / "extraction.json"
    document_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")
    extraction_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")
    sync_calls = []

    class FakeOfflinePipeline:
        def run(self, _document_path, _extraction_path):
            return {"doc_id": "doc-1", "run_id": "reviewed-run"}

    def sync_projection():
        sync_calls.append(True)
        return {"status": "succeeded", "changes": 3, "watermark": 3}

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        document_locator=lambda _doc_id: (
            str(document_path),
            str(extraction_path),
        ),
        projection_sync=sync_projection,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="reviewed")

    assert job["status"] == "succeeded"
    assert sync_calls == [True]
    assert job["result"]["neo4j_sync"] == {
        "status": "succeeded",
        "changes": 3,
        "watermark": 3,
    }
    service.close()


def test_projection_sync_failure_does_not_rollback_sqlite_pipeline(tmp_path):
    document_path = tmp_path / "document.json"
    extraction_path = tmp_path / "extraction.json"
    document_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")
    extraction_path.write_text('{"doc_id":"doc-1"}', encoding="utf-8")

    class FakeOfflinePipeline:
        def run(self, _document_path, _extraction_path):
            return {"doc_id": "doc-1", "run_id": "reviewed-run"}

    def failing_sync():
        raise RuntimeError("bolt://用户名:密码@内网地址")

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        document_locator=lambda _doc_id: (
            str(document_path),
            str(extraction_path),
        ),
        projection_sync=failing_sync,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="reviewed")

    assert job["status"] == "succeeded"
    assert job["result"]["neo4j_sync"] == {
        "status": "failed",
        "reason": "neo4j_sync_failed",
    }
    service.close()


@pytest.mark.parametrize(
    "doc_id",
    ["apt28_080", "kimsuky_001", "lazarus_001"],
)
def test_reviewed_pipeline_builds_fixed_course_sample(tmp_path, doc_id):
    service = PipelineService(tmp_path / f"{doc_id}.db")

    result = service.run_sync(doc_id=doc_id, extraction_mode="reviewed")

    assert result["status"] == "succeeded", result["error"]
    assert result["operation"] == "import_extraction_and_build"
    summary = result["result"]["summaries"][0]
    assert summary["canonical_entities"] > 0
    assert summary["canonical_relations"] > 0
    assert summary["evidence"] > 0
    service.close()


@pytest.mark.parametrize(
    "doc_id",
    [
        "apt28_002",
        "apt28_003",
        "apt28_004",
        "apt28_005",
        "kimsuky_002",
        "kimsuky_003",
        "lazarus_003",
        "lazarus_004",
        "lazarus_009",
    ],
)
def test_reviewed_pipeline_imports_pr47_migrated_artifact(tmp_path, doc_id):
    service = PipelineService(tmp_path / f"{doc_id}.db")

    result = service.run_sync(doc_id=doc_id, extraction_mode="reviewed")

    assert result["status"] == "succeeded", result["error"]
    summary = result["result"]["summaries"][0]
    assert summary["canonical_entities"] > 0
    assert summary["canonical_relations"] > 0
    assert summary["evidence"] > 0
    service.close()


def test_reviewed_selector_uses_explicit_registry_and_ignores_candidate_audit(
    tmp_path,
):
    document = json.loads(APT28_DOCUMENT_PATH.read_text(encoding="utf-8"))
    valid_path = tmp_path / "data/extracted/extract-apt28_080-reviewed.json"
    audit_path = (
        tmp_path / "data/extracted/extract-apt28_080-candidate-audit.json"
    )
    _copy_json(APT28_EXTRACTION_PATH, valid_path)
    _copy_json(APT28_AUDIT_PATH, audit_path)
    registry_path = tmp_path / "config/reviewed-extractions.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "artifacts": [
                    {
                        "doc_id": "apt28_080",
                        "reviewed_extraction": str(
                            valid_path.relative_to(tmp_path)
                        ).replace("\\", "/"),
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    selected = _selector()(tmp_path, "apt28_080", document)

    assert selected == valid_path


def test_reviewed_selector_rejects_unregistered_live_artifact(tmp_path):
    document = json.loads(APT28_DOCUMENT_PATH.read_text(encoding="utf-8"))
    live_path = tmp_path / "data/run_artifacts/extract-apt28_080-live.json"
    _copy_json(APT28_EXTRACTION_PATH, live_path)

    selected = _selector()(tmp_path, "apt28_080", document)

    assert selected is None


def test_reviewed_selector_rejects_duplicate_registry_entries(tmp_path):
    document = json.loads(APT28_DOCUMENT_PATH.read_text(encoding="utf-8"))
    selected_path = tmp_path / "data/extracted/extract-apt28_080-reviewed.json"
    _copy_json(APT28_EXTRACTION_PATH, selected_path)
    registry_path = tmp_path / "config/reviewed-extractions.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "doc_id": "apt28_080",
        "reviewed_extraction": str(selected_path.relative_to(tmp_path)).replace(
            "\\", "/"
        ),
    }
    registry_path.write_text(
        json.dumps(
            {"schema_version": "1.0", "artifacts": [item, item]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="审核工件清单包含重复 doc_id"):
        _selector()(tmp_path, "apt28_080", document)


def test_reviewed_selector_uses_explicit_manifest_choice(tmp_path):
    document = json.loads(APT28_DOCUMENT_PATH.read_text(encoding="utf-8"))
    _copy_json(
        APT28_DOCUMENT_PATH,
        tmp_path / "data/documents/apt28/apt28_080.json",
    )
    first_path = tmp_path / "data/extracted/extract-apt28_080-first.json"
    selected_path = tmp_path / "data/extracted/extract-apt28_080-selected.json"
    _copy_json(APT28_EXTRACTION_PATH, first_path)
    _copy_json(APT28_EXTRACTION_PATH, selected_path)
    manifest_path = tmp_path / "config/course-demo.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "samples": [
                    {
                        "target_group": "APT28",
                        "doc_id": "apt28_080",
                        "document": "data/documents/apt28/apt28_080.json",
                        "reviewed_extraction": str(
                            selected_path.relative_to(tmp_path)
                        ).replace("\\", "/"),
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    selected = _selector()(tmp_path, "apt28_080", document)

    assert selected == selected_path


def test_live_mode_persists_extraction_artifacts_and_run_log(tmp_path):
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
        last_candidate_audit = {
            "schema_version": "1.0",
            "run_id": (
                "extract-doc-1-fake-live-model-1.0-1.0-"
                "20260715164054539671-8210bd88"
            ),
            "doc_id": "doc-1",
            "model_name": "fake-live-model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-15T16:40:54.539671+00:00",
            "chunks": [],
        }

        def extract(self, document):
            assert document["doc_id"] == "doc-1"
            return {
                "schema_version": "1.0",
                "run_id": self.last_candidate_audit["run_id"],
                "doc_id": "doc-1",
                "model_name": "fake-live-model",
                "prompt_version": "1.0",
                "generated_at": "2026-07-15T16:40:54.539671+00:00",
                "chunks": [],
            }

    class FakeOfflinePipeline:
        def run(self, actual_document_path, actual_extraction_path):
            observed_paths.extend(
                [Path(actual_document_path), Path(actual_extraction_path)]
            )
            assert json.loads(
                Path(actual_extraction_path).read_text(encoding="utf-8")
            )["run_id"].endswith("8210bd88")
            return {"doc_id": "doc-1", "run_id": "live-run"}

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        extraction_service=FakeExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert job["status"] == "succeeded"
    assert job["operation"] == "extract_and_build"
    assert job["result"]["summaries"][0]["extraction"]["mode"] == "live"
    assert observed_paths
    assert observed_paths[1].is_file()
    extraction = job["result"]["summaries"][0]["extraction"]
    assert extraction["artifacts"]["result_path"].startswith("extracted/")
    run_log_path = tmp_path / "run_logs" / f"pipeline-run-{job['job_id']}.json"
    run_log = json.loads(run_log_path.read_text(encoding="utf-8"))
    assert run_log["status"] == "succeeded"
    assert run_log["run_id"].endswith("8210bd88")
    assert job["run_archive"]["status"] == "succeeded"
    assert job["run_archive"]["run_id"].endswith("8210bd88")
    service.close()


def test_live_mode_exposes_failed_run_archive_in_job_status(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )

    class FailingExtractionService:
        def extract(self, _document):
            raise RuntimeError("模型不可用")

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        extraction_service=FailingExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert job["status"] == "failed"
    assert job["error"] == "模型不可用"
    assert job["run_archive"] == {
        "run_log": f"run_logs/pipeline-run-{job['job_id']}.json",
        "status": "failed",
        "run_id": None,
        "artifacts": {},
    }
    service.close()


def test_live_mode_keeps_artifacts_when_sqlite_import_fails(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )

    class FakeExtractionService:
        model = "fake-live-model"
        last_api_observation = {"calls": 1}
        last_warnings = []
        last_candidate_audit = {
            "schema_version": "1.0",
            "run_id": (
                "extract-doc-1-fake-live-model-1.0-1.0-"
                "20260715164054539671-8210bd88"
            ),
            "doc_id": "doc-1",
            "model_name": "fake-live-model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-15T16:40:54.539671+00:00",
            "chunks": [],
        }

        def extract(self, _document):
            return {
                key: value
                for key, value in self.last_candidate_audit.items()
            }

    class FailingOfflinePipeline:
        def run(self, _document_path, _extraction_path):
            raise RuntimeError("SQLite 导入失败")

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FailingOfflinePipeline(),
        extraction_service=FakeExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    run_log = json.loads(archive.log_path(job["job_id"]).read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert run_log["status"] == "failed"
    assert run_log["error"] == "SQLite 导入失败"
    assert (tmp_path / run_log["artifacts"]["result_path"]).is_file()
    assert (tmp_path / run_log["artifacts"]["candidate_audit_path"]).is_file()
    assert len(run_log["artifacts"]["result_sha256"]) == 64
    service.close()


def test_sqlite_finish_failure_compensates_live_archive(tmp_path, monkeypatch):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )

    class FakeExtractionService:
        model = "fake-live-model"
        last_api_observation = {"calls": 1}
        last_warnings = []
        last_candidate_audit = {
            "schema_version": "1.0",
            "run_id": (
                "extract-doc-1-fake-live-model-1.0-1.0-"
                "20260715164054539671-8210bd88"
            ),
            "doc_id": "doc-1",
            "model_name": "fake-live-model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-15T16:40:54.539671+00:00",
            "chunks": [],
        }

        def extract(self, _document):
            return dict(self.last_candidate_audit)

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=lambda: None,
        extraction_service=FakeExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )
    monkeypatch.setattr(
        service,
        "_invoke_offline_pipeline",
        lambda *_args: {"doc_id": "doc-1", "run_id": "live-run"},
    )
    monkeypatch.setattr(
        service,
        "_finish_succeeded",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("SQLite 收尾失败")),
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    run_log = json.loads(archive.log_path(job["job_id"]).read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert job["error"] == "SQLite 收尾失败"
    assert run_log["status"] == "failed"
    assert run_log["error"] == "SQLite 收尾失败"
    service.close()


def test_archive_success_failure_compensates_sqlite_result(tmp_path, monkeypatch):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )

    class FakeExtractionService:
        model = "fake-live-model"
        last_api_observation = {"calls": 1}
        last_warnings = []
        last_candidate_audit = {
            "schema_version": "1.0",
            "run_id": (
                "extract-doc-1-fake-live-model-1.0-1.0-"
                "20260715164054539671-8210bd88"
            ),
            "doc_id": "doc-1",
            "model_name": "fake-live-model",
            "prompt_version": "1.0",
            "generated_at": "2026-07-15T16:40:54.539671+00:00",
            "chunks": [],
        }

        def extract(self, _document):
            return dict(self.last_candidate_audit)

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=lambda: None,
        extraction_service=FakeExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )
    monkeypatch.setattr(
        service,
        "_invoke_offline_pipeline",
        lambda *_args: {"doc_id": "doc-1", "run_id": "live-run"},
    )
    monkeypatch.setattr(
        archive,
        "succeed",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("档案收尾失败")),
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    run_log = json.loads(archive.log_path(job["job_id"]).read_text(encoding="utf-8"))
    assert job["status"] == "failed"
    assert job["error"] == "档案收尾失败"
    assert job["result"] == {}
    assert job["steps"][0]["status"] == "failed"
    assert job["steps"][0]["result"] == {}
    assert run_log["status"] == "failed"
    assert run_log["error"] == "档案收尾失败"
    service.close()


def test_archive_failure_does_not_mask_pipeline_error(tmp_path, monkeypatch):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )

    class FailingExtractionService:
        last_api_observation = {"calls": 2}
        last_warnings = ["模型警告"]

        def extract(self, _document):
            raise RuntimeError("模型不可用")

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        extraction_service=FailingExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )
    monkeypatch.setattr(
        archive,
        "fail_if_started",
        lambda *_args: (_ for _ in ()).throw(OSError("档案不可写")),
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert job["status"] == "failed"
    assert job["error"].startswith("模型不可用")
    assert "运行档案更新失败" in job["error"]
    service.close()


def test_live_failure_preserves_llm_observation(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )

    class FailingExtractionService:
        last_api_observation = {"calls": 2, "status": "timeout"}
        last_warnings = ["模型响应超时"]

        def extract(self, _document):
            raise RuntimeError("模型不可用")

    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        extraction_service=FailingExtractionService(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    run_log = json.loads(archive.log_path(job["job_id"]).read_text(encoding="utf-8"))
    assert run_log["llm"] == {"calls": 2, "status": "timeout"}
    assert run_log["warnings"] == ["模型响应超时"]
    service.close()


def test_live_archive_write_failure_marks_job_failed(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        json.dumps({"doc_id": "doc-1", "clean_text": "APT28 uses malware."}),
        encoding="utf-8",
    )
    invalid_run_log_dir = tmp_path / "not-a-directory"
    invalid_run_log_dir.write_text("占位文件", encoding="utf-8")
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=invalid_run_log_dir,
        path_root=tmp_path,
    )
    service = PipelineService(
        tmp_path / "pipeline.db",
        extraction_service=object(),
        document_locator=lambda _doc_id: (str(document_path), None),
        run_archive=archive,
    )

    job = service.run_sync(doc_id="doc-1", extraction_mode="live")

    assert job["status"] == "failed"
    assert job["current_step"] is None
    assert job["error"] == "运行档案写入失败"
    service.close()


def test_service_restart_marks_live_run_archive_interrupted(tmp_path):
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "extracted",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    first = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {},
        run_archive=archive,
    )
    job = first.create_job(doc_id="doc-1", extraction_mode="live")
    assert first.claim(job["job_id"]) is True
    archive.start(
        job_id=job["job_id"],
        doc_id="doc-1",
        operation="extract_and_build",
    )
    first.close()

    second = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {},
        run_archive=archive,
    )

    status = second.status(job["job_id"])
    run_log = json.loads(archive.log_path(job["job_id"]).read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["error"] == "上次执行因服务进程中断而失败"
    assert run_log["status"] == "failed"
    assert run_log["error"] == "上次执行因服务进程中断而失败"
    second.close()


def test_service_restart_tolerates_corrupt_live_run_archive(tmp_path):
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    first = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {},
        run_archive=archive,
    )
    job = first.create_job(doc_id="doc-1", extraction_mode="live")
    assert first.claim(job["job_id"]) is True
    archive.start(
        job_id=job["job_id"],
        doc_id="doc-1",
        operation="extract_and_build",
    )
    archive.log_path(job["job_id"]).write_text("{损坏", encoding="utf-8")
    first.close()

    second = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {},
        run_archive=archive,
    )

    status = second.status(job["job_id"])
    assert status["status"] == "failed"
    assert status["error"] == "上次执行因服务进程中断而失败"
    assert status["run_archive"]["status"] == "unavailable"
    second.close()


def test_service_restart_reconciles_sqlite_success_to_live_archive(tmp_path):
    archive = PipelineRunArchive(
        extraction_dir=tmp_path / "run_artifacts",
        run_log_dir=tmp_path / "run_logs",
        path_root=tmp_path,
    )
    first = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {},
        run_archive=archive,
    )
    job = first.create_job(doc_id="doc-1", extraction_mode="live")
    assert first.claim(job["job_id"]) is True
    archive.start(
        job_id=job["job_id"],
        doc_id="doc-1",
        operation="extract_and_build",
    )
    first._finish_succeeded(job["job_id"], {"doc_ids": ["doc-1"]})
    first.close()

    assert archive.summary(job["job_id"])["status"] == "running"

    second = PipelineService(
        tmp_path / "pipeline.db",
        runner=lambda **_context: {},
        run_archive=archive,
    )

    status = second.status(job["job_id"])
    run_log = json.loads(archive.log_path(job["job_id"]).read_text(encoding="utf-8"))
    assert status["status"] == "succeeded"
    assert status["result"] == {"doc_ids": ["doc-1"]}
    assert run_log["status"] == "succeeded"
    assert run_log["result"] == {"doc_ids": ["doc-1"]}
    second.close()


def test_live_mode_rejects_target_group_scope(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", runner=lambda **_context: {})

    with pytest.raises(ValueError, match="live.*doc_id"):
        service.create_job(target_group="APT28", extraction_mode="live")

    service.close()
