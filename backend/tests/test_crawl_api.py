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


def test_crawl_run_rejects_missing_llm_config(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    response = TestClient(app).post(
        "/api/v1/crawl/runs",
        json={"keyword": "APT28", "limit": 1, "sources": 1, "filter": False},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ERR_LLM_NOT_CONFIGURED"
    assert response.json()["error"]["message"] == "无有效 LLM 配置"
