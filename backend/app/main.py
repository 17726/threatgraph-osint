from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.response import error_response, success_response
from backend.app.services.demo_store import DemoStore
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from scripts.export_graph_json import DEFAULT_OUTPUT_PATH, export_graph_json


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
DEFAULT_DOCUMENT_PATH = Path("data/examples/document.apt28.thn.beardshell.example.json")
DEFAULT_EXTRACTION_RESULT_PATH = Path(
    "data/extracted/extraction_result.apt28.thn.beardshell.v1.json"
)


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


@app.get("/api/v1/graph/path")
def graph_path(
    source: str = Query(..., min_length=1),
    target: str = Query(..., min_length=1),
    max_depth: int = Query(default=4, ge=1, le=6),
):
    return success_response(store.find_paths(source=source, target=target, max_depth=max_depth))


@app.get("/api/v1/entities/search")
def entities_search(q: str = Query(default="", min_length=0)):
    return success_response({"items": store.search_entities(q)})


@app.get("/api/v1/entities/{entity_id}")
def entity_detail(entity_id: str):
    result = store.get_entity(entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="实体不存在")
    return success_response(result)


@app.post("/api/v1/documents/import")
def import_document(document: dict[str, Any]):
    try:
        result = store.import_document(document)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"缺少字段：{exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return success_response(result)


@app.post("/api/v1/pipeline/run")
def run_pipeline(payload: dict[str, Any]):
    document_path = Path(payload.get("document_path") or DEFAULT_DOCUMENT_PATH)
    extraction_result_path = Path(
        payload.get("extraction_result_path") or DEFAULT_EXTRACTION_RESULT_PATH
    )
    if not document_path.exists():
        raise HTTPException(status_code=404, detail=f"文档不存在：{document_path}")
    if not extraction_result_path.exists():
        raise HTTPException(status_code=404, detail=f"抽取结果不存在：{extraction_result_path}")

    summary = OfflineExtractionPipeline(store.db_path).run(
        document_path=document_path,
        extraction_result_path=extraction_result_path,
    )
    graph_path_value = None
    if payload.get("export_graph", True):
        output_path = Path(payload.get("graph_output_path") or DEFAULT_OUTPUT_PATH)
        graph_path_value = str(export_graph_json(store.db_path, output_path, seed_demo=False))

    return success_response(
        {
            "target_group": payload.get("target_group", "APT28"),
            "summary": {
                "doc_id": summary.doc_id,
                "run_id": summary.run_id,
                "chunks": summary.chunks,
                "extracted_entities": summary.extracted_entities,
                "extracted_relations": summary.extracted_relations,
                "canonical_entities": summary.canonical_entities,
                "canonical_relations": summary.canonical_relations,
                "evidence": summary.evidence,
                "behavior_patterns": summary.behavior_patterns,
            },
            "graph_path": graph_path_value,
        }
    )


@app.get("/api/v1/analysis/{target_group}/behavior")
def behavior_analysis(target_group: str):
    analysis = store.get_analysis(target_group)
    return success_response({"target_group": target_group, "patterns": analysis["behavior_patterns"]})


@app.get("/api/v1/analysis/{target_group}/mitre")
def mitre_analysis(target_group: str):
    analysis = store.get_analysis(target_group)
    return success_response({"target_group": target_group, "mappings": analysis["mitre_mappings"]})


@app.get("/api/v1/analysis/{target_group}/inferences")
def inference_analysis(target_group: str):
    analysis = store.get_analysis(target_group)
    return success_response({"target_group": target_group, "inferences": analysis["inferred_relations"]})


@app.get("/api/v1/analysis/{target_group}/threat-assessment")
def threat_assessment(target_group: str):
    return success_response(
        {
            "target_group": target_group,
            "risk_level": "MEDIUM",
            "risk_score": 50,
            "rationale": "当前 P0 接口尚未生成结构化威胁评分，保留默认占位结果。",
            "recommendations": [],
            "evidence_ids": [],
        }
    )


@app.get("/api/v1/reports/{target_group}")
def report(target_group: str):
    result = store.get_report(target_group)
    if result is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return success_response(result)
