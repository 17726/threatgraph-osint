from fastapi.testclient import TestClient

from backend.app.main import app, crawl_service


def test_crawl_run_rejects_invalid_keyword(monkeypatch) -> None:
    monkeypatch.setattr(crawl_service, "submit", lambda *args: {})

    response = TestClient(app).post(
        "/api/v1/crawl/runs",
        json={"keyword": "Unknown", "limit": 1, "sources": 1, "filter": False},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_VALIDATION"


def test_crawl_run_returns_not_found_for_unknown_id() -> None:
    response = TestClient(app).get("/api/v1/crawl/runs/missing")

    assert response.status_code == 404
