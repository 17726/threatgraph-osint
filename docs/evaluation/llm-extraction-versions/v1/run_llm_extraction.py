"""Run real LLM extraction, optional golden evaluation, and SQLite import."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.demo_store import DEFAULT_DB_PATH
from backend.app.services.extraction_evaluator import (
    evaluate_extraction,
    validate_golden_payload,
    validate_golden_schema,
)
from backend.app.services.llm_service import LLMExtractionService
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from scripts.export_graph_json import DEFAULT_OUTPUT_PATH, export_graph_json
from scripts.validate_extraction_result import load_json


def progress(message: str) -> None:
    print(message, file=sys.stderr)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")


def run_single(
    document_path: Path,
    service: LLMExtractionService,
    output_dir: Path = Path("data/extracted"),
    *,
    import_to_db: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
    export_graph: bool = False,
    prompt_version: str = "extract-v1",
    golden_path: Path | None = None,
    evaluation_output: Path | None = None,
) -> dict[str, Any]:
    progress(f"[1/4] 加载文档: {document_path}")
    document = load_json(document_path)
    doc_id = document["doc_id"]
    progress(f"  doc_id={doc_id}, clean_text={len(document['clean_text'])} 字符")
    golden = load_json(golden_path) if golden_path else None
    if golden is not None:
        golden_errors = [
            *validate_golden_schema(golden),
            *validate_golden_payload(golden, document=document),
        ]
        if golden_errors:
            raise ValueError("golden 校验失败: " + "; ".join(golden_errors))

    progress(f"[2/4] 调用 LLM (model={service.model})")
    result = service.extract(document, prompt_version=prompt_version)
    total_entities = sum(len(chunk["entities"]) for chunk in result["chunks"])
    total_relations = sum(len(chunk["relations"]) for chunk in result["chunks"])
    output_path = service.save_result(result, output_dir)
    audit_path = service.save_candidate_audit(output_dir)
    audit_chunks = service.last_candidate_audit["chunks"] if service.last_candidate_audit else []
    rejected_entities = sum(len(chunk["rejected_entities"]) for chunk in audit_chunks)
    rejected_relations = sum(len(chunk["rejected_relations"]) for chunk in audit_chunks)
    progress(f"  已保存候选结果: {output_path}")
    progress(f"  已保存被过滤候选审计: {audit_path}")

    summary: dict[str, Any] = {
        "doc_id": doc_id,
        "run_id": result["run_id"],
        "model": result["model_name"],
        "entities": total_entities,
        "relations": total_relations,
        "output_path": str(output_path),
        "candidate_audit": {
            "output_path": str(audit_path),
            "rejected_entities": rejected_entities,
            "rejected_relations": rejected_relations,
        },
    }
    if service.last_warnings:
        summary["warnings"] = service.last_warnings
        for warning in service.last_warnings:
            progress(f"  警告: {warning}")

    if golden_path:
        progress(f"[3/4] 对照 golden 评测: {golden_path}")
        evaluation = evaluate_extraction(
            result,
            golden,
            candidate_audit=service.last_candidate_audit,
        )
        if evaluation_output is None:
            filename = (
                f"evaluation_result.{doc_id}.{_safe_filename(service.model)}."
                f"{_safe_filename(prompt_version)}.json"
            )
            evaluation_output = Path("data/evaluation") / filename
        evaluation_output.parent.mkdir(parents=True, exist_ok=True)
        evaluation_output.write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summary["evaluation"] = {
            "entity_metrics": evaluation["entity_metrics"],
            "relation_metrics": evaluation["relation_metrics"],
            "output_path": str(evaluation_output),
        }
        progress(
            "  F1: "
            f"entity={evaluation['entity_metrics']['f1']:.4f}, "
            f"relation={evaluation['relation_metrics']['f1']:.4f}"
        )
    else:
        progress("[3/4] 未提供 --golden，跳过评测")

    if import_to_db:
        progress("[4/4] 导入 SQLite canonical graph")
        pipeline = OfflineExtractionPipeline(db_path)
        pipeline_summary = pipeline.run(str(document_path), str(output_path))
        summary["import"] = {
            "extracted_entities": pipeline_summary.extracted_entities,
            "extracted_relations": pipeline_summary.extracted_relations,
            "canonical_entities": pipeline_summary.canonical_entities,
            "canonical_relations": pipeline_summary.canonical_relations,
            "evidence": pipeline_summary.evidence,
        }
        if export_graph:
            graph_path = export_graph_json(db_path, DEFAULT_OUTPUT_PATH, seed_demo=False)
            summary["graph_export"] = str(graph_path)
            progress(f"  图谱已导出: {graph_path}")
    else:
        progress("[4/4] 未提供 --import，跳过 SQLite 导入")

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="调用 OpenAI-compatible API 抽取威胁情报候选，并可选评测和导入 SQLite。"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--document", type=Path, help="单个 document.json 路径")
    source.add_argument("--directory", type=Path, help="批量抽取目录下所有 .json 文件")
    parser.add_argument("--preflight-only", action="store_true", help="只做最小真实 API 连通性检查")
    parser.add_argument("--output", type=Path, default=Path("data/extracted"))
    parser.add_argument("--prompt-version", default="extract-v1")
    parser.add_argument("--model", help="覆盖 LLM_MODEL 环境变量")
    parser.add_argument("--base-url", help="覆盖 LLM_BASE_URL 环境变量")
    parser.add_argument("--timeout", type=float, help="覆盖 LLM_TIMEOUT_SECONDS")
    parser.add_argument("--max-retries", type=int, help="覆盖 LLM_MAX_RETRIES")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        help="覆盖 LLM_MAX_OUTPUT_TOKENS",
    )
    parser.add_argument(
        "--relation-review-passes",
        type=int,
        help="覆盖 LLM_RELATION_REVIEW_PASSES",
    )
    parser.add_argument(
        "--trust-env",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否读取 HTTP_PROXY/HTTPS_PROXY 等代理环境变量",
    )
    parser.add_argument("--limit", type=int, help="批量模式最多处理 N 个文件")
    parser.add_argument("--golden", type=Path, help="单篇模式对应的 golden.json")
    parser.add_argument("--evaluation-output", type=Path, help="完整评测结果输出路径")
    parser.add_argument("--import", dest="import_to_db", action="store_true")
    parser.add_argument("--export-graph", action="store_true")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json", action="store_true", help="标准输出仅打印 JSON 摘要")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.preflight_only and not args.document and not args.directory:
        parser.error("必须提供 --document、--directory 或 --preflight-only")
    if args.preflight_only and (args.document or args.directory):
        parser.error("--preflight-only 不能与文档输入同时使用")
    if args.golden and not args.document:
        parser.error("--golden 当前只支持单篇 --document 模式")
    if args.evaluation_output and not args.golden:
        parser.error("--evaluation-output 必须与 --golden 一起使用")
    if args.export_graph and not args.import_to_db:
        parser.error("--export-graph 必须与 --import 一起使用")

    service = LLMExtractionService(
        base_url=args.base_url,
        model=args.model,
        timeout=args.timeout,
        max_retries=args.max_retries,
        max_output_tokens=args.max_output_tokens,
        relation_review_passes=args.relation_review_passes,
        trust_env=args.trust_env,
    )

    try:
        if args.preflight_only:
            result: Any = service.preflight()
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(
                    "LLM API 预检通过: "
                    f"model={result['response_model'] or result['requested_model']}, "
                    f"tokens={result['usage'].get('total_tokens', 'unknown')}"
                )
            return 0

        if args.document:
            if not args.document.is_file():
                parser.error(f"文件不存在: {args.document}")
            summaries = [
                run_single(
                    args.document,
                    service,
                    output_dir=args.output,
                    import_to_db=args.import_to_db,
                    db_path=args.db,
                    export_graph=args.export_graph,
                    prompt_version=args.prompt_version,
                    golden_path=args.golden,
                    evaluation_output=args.evaluation_output,
                )
            ]
        else:
            if not args.directory.is_dir():
                parser.error(f"目录不存在: {args.directory}")
            files = sorted(args.directory.glob("*.json"))
            if args.limit is not None:
                files = files[: args.limit]
            summaries = []
            for index, document_path in enumerate(files, 1):
                progress(f"--- [{index}/{len(files)}] {document_path.name} ---")
                try:
                    summaries.append(
                        run_single(
                            document_path,
                            service,
                            output_dir=args.output,
                            import_to_db=args.import_to_db,
                            db_path=args.db,
                            export_graph=args.export_graph,
                            prompt_version=args.prompt_version,
                        )
                    )
                except Exception as exc:
                    progress(f"  失败: {exc}")
                    summaries.append({"doc_id": document_path.stem, "error": str(exc)})
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
    else:
        succeeded = sum("error" not in summary for summary in summaries)
        failed = len(summaries) - succeeded
        print(f"完成: {succeeded} 成功, {failed} 失败")
    return 0 if all("error" not in summary for summary in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
