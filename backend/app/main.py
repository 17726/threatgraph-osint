from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.response import error_response, success_response
from backend.app.services.demo_store import DemoStore


app = FastAPI(
    title="ThreatGraph-OSINT API",
    description="开源威胁情报知识图谱研判系统 P0 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = DemoStore()


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response("ERR_HTTP", str(exc.detail)),
    )


@app.get("/api/v1/health")
def health():
    components = store.health()
    return success_response({"status": "healthy", "components": components})


@app.get("/api/v1/graph")
def graph(target: str | None = Query(default=None), depth: int = Query(default=2, ge=1, le=4)):
    _ = depth
    return success_response(store.get_graph(target=target))


@app.get("/api/v1/reports/{target_group}")
def report(target_group: str):
    result = store.get_report(target_group)
    if result is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return success_response(result)
