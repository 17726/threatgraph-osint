from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.document_contract import require_valid_document
from backend.app.core.response import error_response, success_response
from backend.app.services.demo_store import DemoStore
from backend.app.services.graph_query_service import GraphQueryService
from backend.app.services.pipeline_service import (
    DEFAULT_EXTRACTION_MODE,
    PipelineService,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    pipeline_service.close()


app = FastAPI(
    title="ThreatGraph-OSINT API",
    description="开源威胁情报知识图谱研判系统 P0 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = DemoStore()
graph_query_service = GraphQueryService(store.db_path)
pipeline_service = PipelineService(store.db_path)


def _split_query_values(values: list[str]) -> list[str]:
    return [
        item.strip()
        for value in values
        for item in value.split(",")
        if item.strip()
    ]


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
def graph(
    target: str | None = Query(default=None),
    entity_types: list[str] = Query(default=[]),
    entity_ids: list[str] = Query(default=[]),
    relation_types: list[str] = Query(default=[]),
    tags: list[str] = Query(default=[]),
    source_types: list[str] = Query(default=[]),
    languages: list[str] = Query(default=[]),
    first_seen_from: str | None = Query(default=None),
    last_seen_to: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    depth: int = Query(default=2, ge=0, le=20),
    limit: int | None = Query(default=None, ge=1),
):
    return success_response(
        graph_query_service.get_graph(
            target=target,
            entity_types=_split_query_values(entity_types),
            entity_ids=_split_query_values(entity_ids),
            relation_types=_split_query_values(relation_types),
            tags=_split_query_values(tags),
            source_types=_split_query_values(source_types),
            languages=_split_query_values(languages),
            first_seen_from=first_seen_from,
            last_seen_to=last_seen_to,
            min_confidence=min_confidence,
            depth=depth,
            limit=limit,
        )
    )


@app.get("/api/v1/reports/{target_group}")
def report(target_group: str):
    result = store.get_report(target_group)
    if result is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return success_response(result)


@app.post("/api/v1/reports/{target_group}/generate")
def generate_report(target_group: str):
    """基于知识图谱数据生成智能分析报告。"""
    result = store.generate_report(target_group)
    if result is None:
        raise HTTPException(status_code=404, detail="目标组织不存在，无法生成报告")
    return success_response(result)


@app.get("/api/v1/graph/neighbors")
def graph_neighbors(
    entity_id: str = Query(...),
    relation_types: list[str] = Query(default=[]),
    source_types: list[str] = Query(default=[]),
    languages: list[str] = Query(default=[]),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int | None = Query(default=None, ge=1),
):
    return success_response(
        graph_query_service.get_neighbors(
            entity_id,
            relation_types=_split_query_values(relation_types),
            source_types=_split_query_values(source_types),
            languages=_split_query_values(languages),
            min_confidence=min_confidence,
            limit=limit,
        )
    )


@app.get("/api/v1/graph/path")
def graph_path(
    source: str = Query(...),
    target: str = Query(...),
    max_depth: int = Query(default=4, ge=0, le=20),
    relation_types: list[str] = Query(default=[]),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
):
    return success_response(
        graph_query_service.get_path(
            source=source,
            target=target,
            max_depth=max_depth,
            relation_types=_split_query_values(relation_types),
            min_confidence=min_confidence,
        )
    )


@app.get("/api/v1/analysis/{target_group}/behavior")
def analysis_behavior(target_group: str):
    result = store.get_analysis()
    patterns = [p for p in result["behavior_patterns"] if p["target_group"].lower() == target_group.lower()]
    return success_response({"target_group": target_group, "patterns": patterns})


@app.get("/api/v1/analysis/{target_group}/mitre")
def analysis_mitre(target_group: str):
    result = store.get_analysis()
    mappings = [m for m in result["mitre_mappings"] if m["target_group"].lower() == target_group.lower()]
    return success_response({"target_group": target_group, "mappings": mappings})


@app.get("/api/v1/analysis/{target_group}/inferences")
def analysis_inferences(target_group: str):
    result = store.get_analysis()
    return success_response({"target_group": target_group, "inferences": result["inferred_relations"]})


@app.get("/api/v1/analysis/{target_group}/threat-assessment")
def analysis_threat_assessment(target_group: str):
    return success_response({
        "target_group": target_group,
        "risk_level": "HIGH",
        "risk_score": 82,
        "rationale": f"{target_group} 活跃时间长，攻击目标集中于政府和军事领域。",
        "recommendations": ["加强鱼叉式钓鱼邮件检测", "对相关 ATT&CK 技术建立告警规则"],
        "evidence_ids": [],
    })


@app.post("/api/v1/analysis/{target_group}/run")
def analysis_run(target_group: str):
    return success_response({"target_group": target_group, "status": "analysis_baseline_ready"})


@app.post("/api/v1/pipeline/run")
def pipeline_run(payload: dict = Body(default={})):
    try:
        if "use_cache" in payload:
            raise ValueError(
                "use_cache 已废弃；请使用 extraction_mode=reviewed 或 live"
            )
        unknown_fields = sorted(
            set(payload) - {"doc_id", "target_group", "extraction_mode"}
        )
        if unknown_fields:
            raise ValueError(f"流水线请求包含未知字段: {', '.join(unknown_fields)}")
        result = pipeline_service.submit_background(
            doc_id=payload.get("doc_id"),
            target_group=payload.get("target_group"),
            extraction_mode=payload.get(
                "extraction_mode",
                DEFAULT_EXTRACTION_MODE,
            ),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("ERR_VALIDATION", str(exc)),
        )
    return JSONResponse(status_code=202, content=success_response(result))


@app.get("/api/v1/pipeline/status/{job_id}")
def pipeline_status(job_id: str):
    try:
        result = pipeline_service.status(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(result)


@app.post("/api/v1/documents/import")
def import_document(payload: dict = Body(...)):
    try:
        require_valid_document(payload)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=error_response("ERR_VALIDATION", str(exc)),
        )
    result = store.import_document(payload)
    return success_response(result)


@app.get("/api/v1/entities/search")
def search_entities(q: str = Query(...)):
    return success_response(store.search_entities(q))


@app.get("/api/v1/entities/{entity_id}")
def get_entity(entity_id: str):
    result = store.get_entity(entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="实体不存在")
    return success_response(result)
