from pathlib import Path
from types import SimpleNamespace

from crawler.app.service import CrawlerService


def test_finalize_fails_when_selected_source_has_no_successful_pipeline() -> None:
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

    assert result["status"] == "failed"
    assert "SecureList" in result["error_message"]


def test_service_passes_start_number_to_runner(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(command)
        return 0

    monkeypatch.setattr("crawler.app.service.subprocess.run", fake_run)
    monkeypatch.setattr(service, "_import_documents", lambda run: None)

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


def test_service_marks_missing_selected_source_as_failed(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    monkeypatch.setattr(
        "crawler.app.service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
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

    assert result["status"] == "failed"
    assert result["items_imported"] == 1


def test_service_marks_crawler_script_failure_as_failed(monkeypatch, tmp_path: Path) -> None:
    service = CrawlerService(
        workspace_root=tmp_path,
        backend_base_url="http://backend:8000",
    )
    monkeypatch.setattr(
        "crawler.app.service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
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
        "crawler.app.service.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
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

    monkeypatch.setattr("crawler.app.service.subprocess.run", fail_run)

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
