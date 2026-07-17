from pathlib import Path
from types import SimpleNamespace

from crawler.app.service import CrawlerService


def test_finalize_succeeds_when_any_source_has_successful_pipeline() -> None:
    service = CrawlerService()

    result = service._finalize_result(
        {"limit": 1, "selected_sources": ["Qianxin", "SecureList"]},
        {
            "items_pipeline_succeeded": 1,
            "source_results": {
                "Qianxin": {"items_pipeline_succeeded": 1},
                "SecureList": {"items_pipeline_succeeded": 0},
            },
        },
        None,
    )

    assert result["status"] == "succeeded"


def test_partial_source_success_is_succeeded_again() -> None:
    service = CrawlerService()

    result = service._finalize_result(
        {"limit": 1, "selected_sources": ["奇安信威胁情报中心", "Microsoft"]},
        {
            "items_pipeline_succeeded": 1,
            "source_results": {"Microsoft": {"items_pipeline_succeeded": 1}},
        },
        None,
    )

    assert result["status"] == "succeeded"


def test_failed_result_exposes_failed_progress() -> None:
    result = CrawlerService._failed_result(
        {"crawl_run_id": "crawl_test", "keyword": "APT28"}, "failed"
    )

    assert result["progress"]["phase"] == "failed"


def test_new_run_initializes_selected_source_results() -> None:
    service = CrawlerService()

    selected = service._initial_source_results(1 | (1 << 7))

    assert selected["奇安信威胁情报中心"] == {
        "items_promoted": 0,
        "items_imported": 0,
        "items_skipped": 0,
        "items_failed": 0,
        "items_pipeline_succeeded": 0,
    }
    assert selected["SecureList"]["items_promoted"] == 0


def test_pending_run_initializes_selected_source_results(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("LLM_API_KEY", "key")
    service = CrawlerService()
    monkeypatch.setattr(service, "_run_and_store", lambda payload: None)

    result = service.submit(
        {
            "crawl_run_id": "crawl_pending",
            "keyword": "APT28",
            "limit": 1,
            "sources": 1 | (1 << 7),
            "filter": False,
            "start_number": 1,
        }
    )

    assert result["status"] == "accepted"
    assert set(service.status("crawl_pending")["source_results"]) == {
        "奇安信威胁情报中心",
        "SecureList",
    }


def test_exception_result_has_failed_progress() -> None:
    service = CrawlerService()
    result = service._failed_result(
        {"crawl_run_id": "crawl_test", "keyword": "APT28"}, "failed"
    )

    assert result["status"] == "failed"
    assert result["progress"]["phase"] == "failed"


def test_service_passes_start_number_to_runner(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    captured: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        def poll(self):
            return self.returncode

    def fake_popen(command, **kwargs):
        captured.append(command)
        return FakeProcess()

    monkeypatch.setattr("crawler.app.service.subprocess.Popen", fake_popen)
    monkeypatch.setattr(service, "_import_documents", lambda run: {
        "items_pipeline_succeeded": 0,
        "source_results": {},
    })

    service._execute({
        "crawl_run_id": "crawl_test",
        "keyword": "APT28",
        "limit": 2,
        "sources": 1,
        "filter": False,
        "start_number": 108,
    })

    assert "--start-number" in captured[0]
    assert captured[0][captured[0].index("--start-number") + 1] == "108"


def test_service_marks_partial_source_success_as_succeeded(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    monkeypatch.setattr(
        "crawler.app.service.subprocess.Popen",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, poll=lambda: 0),
    )
    monkeypatch.setattr(service, "_import_documents", lambda run: {
        "items_found": 2,
        "items_promoted": 2,
        "items_imported": 1,
        "items_skipped": 1,
        "items_failed": 0,
        "items_pipeline_succeeded": 1,
        "items_pipeline_failed": 0,
        "document_ids": ["apt28_108"],
        "source_results": {
            "奇安信威胁情报中心": {
                "items_promoted": 2,
                "items_imported": 1,
                "items_skipped": 1,
                "items_failed": 0,
                "items_pipeline_succeeded": 1,
            }
        },
    })

    result = service._execute({
        "crawl_run_id": "crawl_partial",
        "keyword": "APT28",
        "limit": 2,
        "sources": 1,
        "filter": False,
        "start_number": 108,
    })

    assert result["status"] == "succeeded"
    assert result["items_imported"] == 1


def test_service_marks_crawler_script_failure_as_failed(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    monkeypatch.setattr(
        "crawler.app.service.subprocess.Popen",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, poll=lambda: 1),
    )
    monkeypatch.setattr(service, "_import_documents", lambda run: {
        "items_found": 1,
        "items_promoted": 1,
        "items_imported": 1,
        "items_skipped": 0,
        "items_failed": 0,
        "items_pipeline_succeeded": 1,
        "items_pipeline_failed": 0,
        "document_ids": ["apt28_001"],
    })

    result = service._execute({
        "crawl_run_id": "crawl_script_failed",
        "keyword": "APT28",
        "limit": 1,
        "sources": 4095,
        "filter": False,
        "start_number": 1,
    })

    assert result["status"] == "failed"
    assert result["error_message"] == "crawler pipeline exited with 1"


def test_service_runs_live_pipeline_after_document_import(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    document_dir = tmp_path / "crawl_pipeline" / "data" / "documents" / "apt28"
    document_dir.mkdir(parents=True)
    document_dir.joinpath("apt28_108.json").write_text(
        '{"doc_id":"apt28_108","clean_text":"APT28"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "crawler.app.service.subprocess.Popen",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, poll=lambda: 0),
    )
    calls: list[tuple[str, dict | None]] = []

    class Response:
        def __init__(self, payload: dict):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    responses = iter(
        [
            Response({"success": True, "data": {"doc_id": "apt28_108", "status": "imported"}}),
            Response({"success": True, "data": {"job_id": "job_001", "status": "running"}}),
            Response({"success": True, "data": {"job_id": "job_001", "status": "running"}}),
            Response({"success": True, "data": {"job_id": "job_001", "status": "succeeded"}}),
        ]
    )

    def fake_post(url, json, timeout):
        calls.append((url, json))
        return next(responses)

    monkeypatch.setattr("crawler.app.service.httpx.post", fake_post)
    monkeypatch.setattr(
        "crawler.app.service.httpx.get",
        lambda url, timeout: next(responses),
    )

    result = service._execute({
        "crawl_run_id": "crawl_pipeline",
        "keyword": "APT28",
        "limit": 1,
        "sources": 1,
        "filter": False,
        "start_number": 108,
    })

    assert result["items_imported"] == 1
    assert result["items_pipeline_succeeded"] == 1, {
        "result": result,
        "calls": calls,
        "error": result["error_message"],
    }
    assert result["source_results"] == {
        "奇安信威胁情报中心": {
            "items_promoted": 0,
            "items_imported": 0,
            "items_skipped": 0,
            "items_failed": 0,
            "items_pipeline_succeeded": 0,
        },
        "unknown": {
            "items_promoted": 1,
            "items_imported": 1,
            "items_skipped": 0,
            "items_failed": 0,
            "items_pipeline_succeeded": 1,
        }
    }
    assert calls[1] == (
        "http://backend:8000/api/v1/pipeline/run",
        {"doc_id": "apt28_108", "extraction_mode": "live"},
    )


def test_crawl_observability_exposes_child_pipeline_progress(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    run_id = "crawl_observability"
    service._runs[run_id] = {
        "crawl_run_id": run_id,
        "keyword": "APT28",
        "status": "running",
        "events": [],
        "pipeline": None,
        "progress": None,
    }

    class Response:
        def __init__(self, payload: dict):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "data": self.payload}

    monkeypatch.setattr(
        "crawler.app.service.httpx.post",
        lambda *args, **kwargs: Response(
            {"job_id": "job_child_001", "status": "running"}
        ),
    )
    responses = iter(
        [
            Response(
                {
                    "job_id": "job_child_001",
                    "status": "running",
                    "progress": {
                        "phase": "building_graph",
                        "current": 0,
                        "total": 1,
                        "percent": 0,
                        "message": "正在校验、归一化并写入 SQLite：apt28_108",
                        "doc_id": "apt28_108",
                    },
                }
            ),
            Response(
                {
                    "job_id": "job_child_001",
                    "status": "succeeded",
                    "progress": {
                        "phase": "completed",
                        "current": 1,
                        "total": 1,
                        "percent": 100,
                        "message": "流水线执行完成",
                        "doc_id": "apt28_108",
                    },
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "crawler.app.service.httpx.get", lambda *args, **kwargs: next(responses)
    )

    result = service._run_live_pipeline(
        "apt28_108",
        crawl_run_id=run_id,
        target="APT28",
        current=0,
        total=1,
        source="FreeBuf",
    )
    status = service.status(run_id)

    assert result["status"] == "succeeded"
    assert status["pipeline"]["job_id"] == "job_child_001"
    assert status["pipeline"]["progress"]["percent"] == 100
    assert status["progress"]["phase"] == "pipeline"
    assert status["progress"]["message"] == "流水线执行完成"
    assert [event["phase"] for event in status["events"]] == [
        "pipeline_submitted",
        "pipeline_building_graph",
        "pipeline_completed",
    ]


def test_crawl_observability_records_collection_phase_changes() -> None:
    service = CrawlerService()
    run_id = "crawl_progress_events"
    service._runs[run_id] = {
        "crawl_run_id": run_id,
        "keyword": "APT28",
        "status": "running",
        "events": [],
        "progress": None,
    }

    service._update_progress(
        run_id,
        {
            "phase": "collecting",
            "current": 1,
            "total": 3,
            "target": "APT28",
            "source": "FreeBuf",
            "message": "正在采集",
        },
    )
    service._update_progress(
        run_id,
        {
            "phase": "collecting",
            "current": 2,
            "total": 3,
            "target": "APT28",
            "source": "FreeBuf",
            "message": "正在采集",
        },
    )
    service._update_progress(
        run_id,
        {
            "phase": "validating",
            "current": 0,
            "total": 2,
            "target": "APT28",
            "source": None,
            "message": "正在校验",
        },
    )

    status = service.status(run_id)

    assert [event["phase"] for event in status["events"]] == [
        "collecting",
        "validating",
    ]


def test_crawl_observability_emits_docker_visible_structured_log(caplog) -> None:
    service = CrawlerService()
    run_id = "crawl_log_events"
    service._runs[run_id] = {
        "crawl_run_id": run_id,
        "keyword": "APT28",
        "status": "running",
        "events": [],
        "progress": None,
    }

    with caplog.at_level("INFO", logger="uvicorn.error"):
        service._update_progress(
            run_id,
            {
                "phase": "collecting",
                "current": 1,
                "total": 2,
                "target": "APT28",
                "source": "FreeBuf",
                "message": "正在采集",
            },
        )

    assert any(
        "crawl_event" in record.message and run_id in record.message
        for record in caplog.records
    )


def test_import_failure_still_counts_document_as_found(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    document_dir = tmp_path / "crawl_import_failure" / "data" / "documents" / "apt28"
    document_dir.mkdir(parents=True)
    document_dir.joinpath("apt28_108.json").write_text(
        '{"doc_id":"apt28_108","source_name":"Example"}',
        encoding="utf-8",
    )

    class Response:
        def raise_for_status(self):
            raise RuntimeError("import failed")

    monkeypatch.setattr(
        "crawler.app.service.httpx.post", lambda *args, **kwargs: Response()
    )

    result = service._import_documents(
        {
            "crawl_run_id": "crawl_import_failure",
            "keyword": "APT28",
        }
    )

    assert result["items_found"] == 1
    assert result["items_failed"] == 1


def test_service_cleans_workspace_on_failure(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    for name in ("cleaned", "cleaned_filtered", "documents"):
        directory = tmp_path / "crawl_failed" / "data" / name
        directory.mkdir(parents=True)
        (directory / "document.json").write_text("{}", encoding="utf-8")

    def fail_run(*args, **kwargs):
        raise RuntimeError("crawler failed")

    monkeypatch.setattr("crawler.app.service.subprocess.Popen", fail_run)

    result = service._execute({
        "crawl_run_id": "crawl_failed",
        "keyword": "APT28",
        "limit": 1,
        "sources": 1,
        "filter": False,
        "start_number": 1,
    })

    assert result["status"] == "failed"
    assert result["workspace_cleaned"] is True
    assert not (tmp_path / "crawl_failed" / "documents").exists()
