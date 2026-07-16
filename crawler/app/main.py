from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from crawler.app.service import CrawlerService


app = FastAPI(title="ThreatGraph-OSINT Crawler API", version="0.1.0")
crawler_service = CrawlerService()


@app.post("/api/v1/crawl/runs", status_code=202)
def create_crawl_run(payload: dict):
    required = {"crawl_run_id", "keyword", "limit", "sources", "filter", "start_number"}
    if set(payload) != required:
        raise HTTPException(status_code=400, detail="采集请求字段不完整或包含未知字段")
    if not isinstance(payload["limit"], int) or payload["limit"] < 1:
        raise HTTPException(status_code=400, detail="limit 必须是正整数")
    if not isinstance(payload["sources"], int) or not 1 <= payload["sources"] <= 4095:
        raise HTTPException(status_code=400, detail="sources 必须是 1 到 4095 之间的整数")
    if not isinstance(payload["start_number"], int) or payload["start_number"] < 1:
        raise HTTPException(status_code=400, detail="start_number 必须是正整数")
    try:
        return crawler_service.submit(payload)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=f"采集任务已存在: {exc.args[0]}") from exc


@app.get("/api/v1/crawl/runs/{crawl_run_id}")
def get_crawl_run(crawl_run_id: str):
    try:
        return crawler_service.status(crawl_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="采集任务不存在") from exc
