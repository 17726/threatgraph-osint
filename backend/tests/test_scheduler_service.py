import asyncio
import sqlite3
import threading

from backend.app.db.schema import ensure_pipeline_schema
from backend.app.services.demo_store import DemoStore
from backend.app.services.scheduler_service import SchedulerService


class FakePipeline:
    def __init__(self):
        self.submitted_doc_ids = []

    def submit(self, *, doc_id, **kwargs):
        self.submitted_doc_ids.append(doc_id)
        return {"job_id": f"job-{doc_id}", "status": "pending"}


def add_document(db_path, doc_id):
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO documents (
                doc_id, target_group, source_url, source_type, title, language,
                clean_text, content_hash, created_at
            ) VALUES (?, 'APT28', 'https://example.test', 'news', ?, 'en', 'text', 'hash', 'now')
            """,
            (doc_id, doc_id),
        )


def add_succeeded_job(db_path, doc_id):
    with sqlite3.connect(db_path) as connection:
        ensure_pipeline_schema(connection)
        connection.execute(
            """
            INSERT INTO pipeline_jobs (
                job_id, doc_id, target_group, use_cache, steps_json, status, created_at
            ) VALUES (?, ?, 'APT28', 1, '[]', 'succeeded', 'now')
            """,
            (f"job-{doc_id}", doc_id),
        )


def add_pending_job(db_path, doc_id):
    with sqlite3.connect(db_path) as connection:
        ensure_pipeline_schema(connection)
        connection.execute(
            """
            INSERT INTO pipeline_jobs (
                job_id, doc_id, target_group, use_cache, steps_json, status, created_at
            ) VALUES (?, ?, 'APT28', 1, '[]', 'pending', 'now')
            """
            ,
            (f"job-{doc_id}", doc_id),
        )


def test_scheduler_does_not_resubmit_unfinished_pipeline_job(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    add_document(store.db_path, "already-pending")
    add_pending_job(store.db_path, "already-pending")
    pipeline = FakePipeline()
    scheduler = SchedulerService(store.db_path, pipeline, interval_seconds=1)

    result = scheduler.scan_once()

    assert result["submitted"] == 0
    assert pipeline.submitted_doc_ids == []


def test_scheduler_submits_pending_document_once(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    add_document(store.db_path, "apt28_032")
    add_document(store.db_path, "already-done")
    add_succeeded_job(store.db_path, "already-done")
    pipeline = FakePipeline()
    scheduler = SchedulerService(store.db_path, pipeline, interval_seconds=1)

    scheduler.scan_once()
    scheduler.scan_once()

    assert pipeline.submitted_doc_ids == ["apt28_032"]


def test_scheduler_does_not_submit_same_document_concurrently(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    add_document(store.db_path, "doc-1")
    started = threading.Event()
    release = threading.Event()
    calls = []

    class BlockingPipeline:
        def submit_background(self, *, doc_id, **kwargs):
            calls.append(doc_id)
            started.set()
            release.wait()
            return {"job_id": "job-doc-1", "status": "pending"}

    scheduler = SchedulerService(store.db_path, BlockingPipeline())

    first = threading.Thread(target=scheduler.scan_once)
    first.start()
    assert started.wait(timeout=1)
    second = scheduler.scan_once()
    release.set()
    first.join(timeout=1)

    assert second["submitted"] == 0
    assert len(calls) == 1
    assert calls[0] == "doc-1"


def test_scheduler_reports_submit_failure_and_retries_document_without_blocking_others(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    add_document(store.db_path, "doc-fails-first")
    add_document(store.db_path, "doc-succeeds")
    attempts = []

    class FlakyPipeline:
        def submit(self, *, doc_id, **kwargs):
            attempts.append(doc_id)
            if doc_id == "doc-fails-first" and attempts.count(doc_id) == 1:
                raise RuntimeError("temporary submit failure")
            return {"job_id": f"job-{doc_id}", "status": "pending"}

    scheduler = SchedulerService(store.db_path, FlakyPipeline())

    first_result = scheduler.scan_once()

    assert first_result["submitted"] == 1
    assert first_result["failed"] == [
        {"doc_id": "doc-fails-first", "retry": True, "error": "temporary submit failure"}
    ]
    assert attempts == ["doc-fails-first", "doc-succeeds"]

    second_result = scheduler.scan_once()

    assert second_result["submitted"] == 1
    assert second_result["failed"] == []
    assert attempts == ["doc-fails-first", "doc-succeeds", "doc-fails-first"]



def test_scheduler_calls_neo4j_sync_when_watermark_is_behind(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    calls = []
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "INSERT INTO graph_changes (table_name, record_id, operation) VALUES ('entities', 'e1', 'upsert')"
        )
    scheduler = SchedulerService(
        store.db_path,
        FakePipeline(),
        sync_neo4j=lambda: calls.append("sync"),
    )

    scheduler.scan_once()

    assert calls == ["sync"]


def test_scheduler_reads_enabled_and_interval_from_environment(tmp_path, monkeypatch):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    monkeypatch.setenv("THREATGRAPH_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("THREATGRAPH_SCHEDULER_INTERVAL_SECONDS", "2.5")

    scheduler = SchedulerService(store.db_path, FakePipeline())

    assert scheduler.enabled is True
    assert scheduler.interval_seconds == 2.5


def test_scheduler_start_and_stop_run_periodically(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    add_document(store.db_path, "doc-1")
    pipeline = FakePipeline()
    scheduler = SchedulerService(store.db_path, pipeline, interval_seconds=0.01, enabled=True)

    async def exercise():
        await scheduler.start()
        await asyncio.sleep(0.03)
        await scheduler.stop()

    asyncio.run(exercise())

    assert pipeline.submitted_doc_ids == ["doc-1"]


def test_scheduler_is_disabled_by_default(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    add_document(store.db_path, "doc-1")
    pipeline = FakePipeline()
    scheduler = SchedulerService(store.db_path, pipeline, interval_seconds=0.01)

    async def exercise():
        await scheduler.start()
        await asyncio.sleep(0.02)
        await scheduler.stop()

    asyncio.run(exercise())

    assert pipeline.submitted_doc_ids == []


def test_scheduler_run_loop_offloads_scan_to_worker_thread(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    scheduler = SchedulerService(store.db_path, FakePipeline(), interval_seconds=0.01, enabled=True)
    event_loop_thread = threading.get_ident()
    scan_thread_ids = []
    scanned = threading.Event()

    def scan_once():
        scan_thread_ids.append(threading.get_ident())
        scanned.set()
        return {"submitted": 0, "synced": 0}

    scheduler.scan_once = scan_once

    async def exercise():
        await scheduler.start()
        await asyncio.to_thread(scanned.wait, 1)
        await scheduler.stop()

    asyncio.run(exercise())

    assert scan_thread_ids
    assert scan_thread_ids[0] != event_loop_thread


def test_scheduler_stop_waits_for_in_flight_sync_task(tmp_path):
    store = DemoStore(tmp_path / "scheduler.db", seed_demo=False)
    started = threading.Event()
    release = threading.Event()

    def sync_neo4j():
        started.set()
        release.wait()

    scheduler = SchedulerService(
        store.db_path,
        FakePipeline(),
        interval_seconds=0.01,
        enabled=True,
        sync_neo4j=sync_neo4j,
    )

    async def exercise():
        scheduler.scan_once = lambda: scheduler._schedule(sync_neo4j()) or {"submitted": 0, "synced": 1}
        await scheduler.start()
        await asyncio.to_thread(started.wait, 1)
        stop_task = asyncio.create_task(scheduler.stop())
        await asyncio.sleep(0)
        assert not stop_task.done()
        release.set()
        await asyncio.wait_for(stop_task, timeout=1)

    asyncio.run(exercise())
