import sqlite3
import threading
import time
import json
from pathlib import Path

import pytest

from backend.app.services import pipeline_service as pipeline_service_module
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


def test_reviewed_selector_ignores_candidate_audit(tmp_path):
    document = json.loads(APT28_DOCUMENT_PATH.read_text(encoding="utf-8"))
    valid_path = tmp_path / "data/extracted/extract-apt28_080-reviewed.json"
    audit_path = (
        tmp_path / "data/extracted/extract-apt28_080-candidate-audit.json"
    )
    _copy_json(APT28_EXTRACTION_PATH, valid_path)
    _copy_json(APT28_AUDIT_PATH, audit_path)

    selected = _selector()(tmp_path, "apt28_080", document)

    assert selected == valid_path


def test_reviewed_selector_rejects_multiple_valid_candidates(tmp_path):
    document = json.loads(APT28_DOCUMENT_PATH.read_text(encoding="utf-8"))
    first_path = tmp_path / "data/extracted/extract-apt28_080-first.json"
    second_path = tmp_path / "data/extracted/extract-apt28_080-second.json"
    _copy_json(APT28_EXTRACTION_PATH, first_path)
    second = _copy_json(APT28_EXTRACTION_PATH, second_path)
    second["run_id"] = (
        "extract-apt28_080-deepseek-v4-flash-1.0-1.0-"
        "20260714075123666577-deadbeef"
    )
    second_path.write_text(
        json.dumps(second, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="多个合法已审核抽取结果") as exc_info:
        _selector()(tmp_path, "apt28_080", document)

    assert "c463deb3" in str(exc_info.value)
    assert "deadbeef" in str(exc_info.value)


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
