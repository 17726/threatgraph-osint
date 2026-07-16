from fastapi.testclient import TestClient

from crawler.app.main import app, crawler_service


def test_create_crawl_run_returns_accepted(monkeypatch) -> None:
    monkeypatch.setattr(crawler_service, "submit", lambda payload: {
        "crawl_run_id": payload["crawl_run_id"],
        "status": "accepted",
    })

    client = TestClient(app)
    response = client.post(
        "/api/v1/crawl/runs",
        json={
            "crawl_run_id": "crawl_test_001",
            "keyword": "APT28",
            "limit": 2,
            "sources": 1,
            "filter": False,
            "start_number": 108,
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "crawl_run_id": "crawl_test_001",
        "status": "accepted",
    }


def test_get_unknown_crawl_run_returns_not_found() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/crawl/runs/missing")

    assert response.status_code == 404


def test_duplicate_crawl_run_returns_conflict(monkeypatch) -> None:
    monkeypatch.setattr(crawler_service, "_run_and_store", lambda payload: None)
    client = TestClient(app)
    payload = {
        "crawl_run_id": "crawl_duplicate",
        "keyword": "APT28",
        "limit": 1,
        "sources": 1,
        "filter": False,
        "start_number": 1,
    }

    assert client.post("/api/v1/crawl/runs", json=payload).status_code == 202
    assert client.post("/api/v1/crawl/runs", json=payload).status_code == 409
