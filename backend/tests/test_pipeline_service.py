import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from backend.app.services.llm_service import LLMExtractionService
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from backend.app.services.pipeline_service import DEFAULT_STEPS, PipelineService


def test_pipeline_reads_imported_sqlite_document_without_repository_file(tmp_path):
    from backend.app.services.demo_store import DemoStore

    db_path = tmp_path / "pipeline.db"
    store = DemoStore(db_path, seed_demo=False)
    store.import_document(
        {
            "doc_id": "imported-1",
            "target_group": "APT28",
            "source_url": "https://example.com/imported-1",
            "source_type": "news",
            "source_name": "Example",
            "title": "Imported document",
            "language": "en",
            "clean_text": "SQLite is the source of truth.",
            "content_hash": "sha256:ignored",
        }
    )
    calls = []

    class FakeExtractionService:
        def extract(self, document):
            calls.append(("extract", document["doc_id"], document["clean_text"], document["source_name"]))
            return {"doc_id": document["doc_id"], "chunks": []}

    class FakeOfflinePipeline:
        def run(self, document_path, extraction_result_path):
            document = json.loads(Path(document_path).read_text(encoding="utf-8"))
            calls.append(("offline", document["doc_id"], document["clean_text"], document["source_name"]))
            return {"doc_id": document["doc_id"], "run_id": "run-1"}

    service = PipelineService(
        db_path,
        offline_pipeline=FakeOfflinePipeline(),
        extraction_service=FakeExtractionService(),
    )

    job = service.run_sync(doc_id="imported-1", steps=["extract"])

    assert job["status"] == "succeeded"
    assert calls == [
        ("extract", "imported-1", "SQLite is the source of truth.", "Example"),
        ("offline", "imported-1", "SQLite is the source of truth.", "Example"),
    ]


def test_pipeline_extracts_each_sqlite_document_for_target_group_without_doc_id(tmp_path):
    from backend.app.services.demo_store import DemoStore

    db_path = tmp_path / "pipeline.db"
    store = DemoStore(db_path, seed_demo=False)
    for doc_id in ("group-doc-1", "group-doc-2"):
        store.import_document(
            {
                "doc_id": doc_id,
                "target_group": "APT28",
                "source_url": f"https://example.com/{doc_id}",
                "source_type": "news",
                "source_name": "Example",
                "title": doc_id,
                "language": "en",
                "clean_text": f"Content for {doc_id}.",
            }
        )
    extracted: list[str] = []
    processed: list[str] = []

    class FakeExtractionService:
        def extract(self, document):
            extracted.append(document["doc_id"])
            return {"doc_id": document["doc_id"], "chunks": []}

    class FakeOfflinePipeline:
        def run(self, document_path, extraction_result_path):
            document = json.loads(Path(document_path).read_text(encoding="utf-8"))
            processed.append(document["doc_id"])
            return {"doc_id": document["doc_id"], "run_id": f"run-{document['doc_id']}"}

    service = PipelineService(
        db_path,
        offline_pipeline=FakeOfflinePipeline(),
        extraction_service=FakeExtractionService(),
    )

    job = service.run_sync(target_group="APT28", steps=["extract"])

    assert job["status"] == "succeeded"
    result = job["result"]["extract"]
    assert result["doc_ids"] == ["group-doc-1", "group-doc-2"]
    assert [summary["doc_id"] for summary in result["summaries"]] == [
        "group-doc-1",
        "group-doc-2",
    ]
    assert extracted == ["group-doc-1", "group-doc-2"]
    assert processed == ["group-doc-1", "group-doc-2"]


def test_pipeline_target_group_without_matching_documents_fails(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db")

    job = service.run_sync(target_group="missing-group", steps=["extract"])

    assert job["status"] == "failed"
    assert "没有匹配文档" in job["error"]

def test_pipeline_default_steps_execute_existing_offline_pipeline_and_neo4j_sync(tmp_path):
    assert DEFAULT_STEPS == [
        "extract",
        "normalize",
        "build_graph",
        "analyze_behavior",
        "infer",
        "report",
        "neo4j_sync",
    ]
    calls: list[tuple] = []

    class FakeOfflinePipeline:
        def run(self, document_path, extraction_result_path):
            calls.append(("offline", document_path, extraction_result_path))
            return {
                "doc_id": "doc-1",
                "run_id": "run-1",
            }

    class FakeNeo4j:
        def sync_incremental(self):
            calls.append(("neo4j",))
            return {"status": "succeeded"}

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        neo4j_service=FakeNeo4j(),
        document_locator=lambda doc_id: ("document.json", "extraction.json"),
    )

    job = service.run_sync(doc_id="doc-1")

    assert job["status"] == "succeeded"
    assert calls == [
        ("offline", "document.json", "extraction.json"),
        ("neo4j",),
    ]


def test_pipeline_extracts_standard_document_when_extraction_result_is_absent(tmp_path):
    document_path = tmp_path / "document.json"
    document_path.write_text(
        '{"doc_id": "doc-1", "clean_text": "APT28 uses malware."}',
        encoding="utf-8",
    )
    calls = []

    class FakeExtractionService:
        def extract(self, document):
            calls.append(("extract", document["doc_id"], document["clean_text"]))
            return {"doc_id": document["doc_id"], "chunks": []}

    class FakeOfflinePipeline:
        def run(self, document_path, extraction_result_path):
            calls.append(("offline", document_path, extraction_result_path))
            assert extraction_result_path is not None
            assert Path(extraction_result_path).exists()
            assert json.loads(Path(extraction_result_path).read_text(encoding="utf-8"))["doc_id"] == "doc-1"
            return {"doc_id": "doc-1", "run_id": "run-1"}

    service = PipelineService(
        tmp_path / "pipeline.db",
        offline_pipeline=FakeOfflinePipeline(),
        extraction_service=FakeExtractionService(),
        document_locator=lambda doc_id: (str(document_path), None),
    )

    job = service.run_sync(doc_id="doc-1", steps=["extract"])

    assert job["status"] == "succeeded"
    assert calls[0] == ("extract", "doc-1", "APT28 uses malware.")
    assert calls[1][0] == "offline"


    calls = []
    steps = {name: (lambda name=name: calls.append(name)) for name in DEFAULT_STEPS}
    service = PipelineService(tmp_path / "pipeline.db", steps=steps)

    job = service.run_sync(target_group="APT28")

    assert calls == DEFAULT_STEPS
    assert service.status(job["job_id"])["status"] == "succeeded"
    assert [step["step_name"] for step in service.status(job["job_id"])["steps"]] == DEFAULT_STEPS


def test_pipeline_failure_persists_failed_step_and_error(tmp_path):
    def fail():
        raise ValueError("抽取输入不存在")

    service = PipelineService(tmp_path / "pipeline.db", steps={"extract": fail})

    job = service.run_sync(doc_id="missing-doc", steps=["extract"])
    status = service.status(job["job_id"])

    assert status["status"] == "failed"
    assert status["failed_step"] == "extract"
    assert status["steps"][0]["status"] == "failed"
    assert "抽取输入不存在" in status["steps"][0]["error"]


def test_pipeline_reuses_pending_or_running_job(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", steps={"extract": lambda: None})
    first = service.submit(doc_id="doc-1", steps=["extract"])
    second = service.submit(doc_id="doc-1", steps=["extract"])

    assert second["job_id"] == first["job_id"]
    assert second["status"] == "pending"


def test_pipeline_rejects_clean_step_as_unknown(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db")

    with pytest.raises(ValueError, match="未知流水线步骤"):
        service._default_step("clean", {})


def test_pipeline_initializes_default_extraction_service(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db")

    assert isinstance(service.extraction_service, LLMExtractionService)


def test_pipeline_async_submit_runs_in_background(tmp_path):
    calls = []
    service = PipelineService(
        tmp_path / "pipeline.db",
        steps={"extract": lambda: calls.append("extract")},
    )

    job = asyncio.run(service.run_async(steps=["extract"]))

    assert job["status"] == "succeeded"
    assert calls == ["extract"]


def test_pipeline_without_extraction_input_fails_clearly(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db")

    job = service.run_sync(doc_id="missing-doc", steps=["extract"])
    status = service.status(job["job_id"])

    assert status["status"] == "failed"
    assert "没有可执行的抽取输入" in status["error"]




def test_pipeline_close_shuts_down_executor(tmp_path):
    service = PipelineService(tmp_path / "pipeline.db", steps={"extract": lambda: None})

    service.close()

    with pytest.raises(RuntimeError):
        service._executor.submit(lambda: None)


def test_pipeline_schema_is_persisted(tmp_path):
    db_path = tmp_path / "pipeline.db"
    PipelineService(db_path, steps={"extract": lambda: None}).run_sync(steps=["extract"])

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"pipeline_jobs", "pipeline_job_steps"} <= tables
