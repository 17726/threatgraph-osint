from pathlib import Path
import time

from backend.app.services.crawl_service import CrawlService


def test_next_start_number_uses_highest_document_id(tmp_path: Path) -> None:
    service = CrawlService(
        db_path=tmp_path / "test.db",
        crawler_base_url="http://crawler:8100",
    )
    service.store.import_document(_document("apt28_007", "one"))
    service.store.import_document(_document("apt28_012", "two"))

    assert service.next_start_number("APT28") == 13


def test_submit_sends_start_number_to_crawler(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LLM_MODEL", "model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "key")
    service = CrawlService(
        db_path=tmp_path / "test.db",
        crawler_base_url="http://crawler:8100",
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"crawl_run_id": "crawl_test", "status": "accepted"}

    def post(url, json, timeout):
        captured.update(json)
        return Response()

    monkeypatch.setattr("backend.app.services.crawl_service.httpx.post", post)
    result = service.submit("APT28", 2, 1, False)

    assert result["status"] == "pending"
    deadline = time.time() + 1
    while "start_number" not in captured and time.time() < deadline:
        time.sleep(0.01)
    assert captured["start_number"] == 1


def _document(doc_id: str, text: str) -> dict:
    import hashlib

    return {
        "doc_id": doc_id,
        "schema_version": "1.0",
        "target_group": "APT28",
        "target_groups": ["APT28"],
        "source_url": f"https://example.com/{doc_id}",
        "source_type": "news",
        "source_name": "Example",
        "title": doc_id,
        "language": "en",
        "clean_text": text,
        "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "published_at": None,
        "retrieved_at": "2026-07-16T00:00:00Z",
        "source_reliability": "B",
        "tlp": "TLP:CLEAR",
        "tags": [],
        "metadata": {},
    }
