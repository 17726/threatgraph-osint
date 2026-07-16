from pathlib import Path
from types import SimpleNamespace

from crawler.app.service import CrawlerService


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


def test_service_marks_partial_import_as_succeeded(monkeypatch, tmp_path: Path) -> None:
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
        "document_ids": ["apt28_108"],
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
