"""
端到端 LLM 抽取脚本：文档 → LLM 抽取 → 保存 extraction_result → (可选)导入 SQLite。

用法:
    python scripts/run_llm_extraction.py \\
        --document data/documents/apt28/apt28_001.json \\
        --output data/extracted

    # 抽取并直接导入数据库
    python scripts/run_llm_extraction.py \\
        --document data/documents/apt28/apt28_001.json \\
        --import

    # 批量抽取整个目录
    python scripts/run_llm_extraction.py \\
        --directory data/documents/apt28/ \\
        --limit 5
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.llm_service import LLMExtractionService
from backend.app.services.demo_store import DEFAULT_DB_PATH
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from scripts.export_graph_json import DEFAULT_OUTPUT_PATH, export_graph_json


def run_single(
    document_path: Path,
    service: LLMExtractionService,
    output_dir: Path = Path("data/extracted"),
    *,
    import_to_db: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
    export_graph: bool = False,
    prompt_version: str = "extract-v1",
) -> dict:
    print(f"[1/3] 加载文档: {document_path}")
    document = json.loads(document_path.read_text(encoding="utf-8"))
    doc_id = document["doc_id"]
    print(f"  doc_id={doc_id}, title={document.get('title', '')}")
    print(f"  clean_text 长度: {len(document['clean_text'])} 字符")

    print(f"[2/3] LLM 抽取中 (model={service.model})...")
    result = service.extract(document, prompt_version=prompt_version)

    total_entities = sum(len(chunk["entities"]) for chunk in result["chunks"])
    total_relations = sum(len(chunk["relations"]) for chunk in result["chunks"])
    print(f"  抽取完成: {total_entities} 实体, {total_relations} 关系")

    output_path = service.save_result(result, output_dir)
    print(f"  已保存: {output_path}")

    summary = {
        "doc_id": doc_id,
        "run_id": result["run_id"],
        "model": result["model_name"],
        "entities": total_entities,
        "relations": total_relations,
        "output_path": str(output_path),
    }

    if import_to_db:
        print("[3/3] 导入数据库...")
        pipeline = OfflineExtractionPipeline(db_path)
        pipe_summary = pipeline.run(str(document_path), str(output_path))
        summary["import"] = {
            "extracted_entities": pipe_summary.extracted_entities,
            "extracted_relations": pipe_summary.extracted_relations,
            "canonical_entities": pipe_summary.canonical_entities,
            "canonical_relations": pipe_summary.canonical_relations,
            "evidence": pipe_summary.evidence,
        }
        print(
            f"  导入完成: 候选实体={pipe_summary.extracted_entities}, "
            f"候选关系={pipe_summary.extracted_relations}, "
            f"正式实体={pipe_summary.canonical_entities}, "
            f"正式关系={pipe_summary.canonical_relations}"
        )

        if export_graph:
            graph_path = export_graph_json(db_path, DEFAULT_OUTPUT_PATH, seed_demo=False)
            print(f"  图谱已导出: {graph_path}")
            summary["graph_export"] = str(graph_path)
    else:
        print("[3/3] 跳过数据库导入 (使用 --import 开启)")

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM 驱动威胁情报抽取：加载文档，调用 LLM 抽取实体关系，可选导入 SQLite。"
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--document", type=Path, help="单个 document.json 路径")
    src.add_argument("--directory", type=Path, help="批量抽取目录下所有 .json 文件")

    parser.add_argument("--output", type=Path, default=Path("data/extracted"), help="extraction_result 输出目录")
    parser.add_argument("--prompt-version", default="extract-v1", help="prompt 版本标识")
    parser.add_argument("--model", help="覆盖 LLM_MODEL 环境变量")
    parser.add_argument("--base-url", help="覆盖 LLM_BASE_URL 环境变量")
    parser.add_argument("--api-key", help="覆盖 LLM_API_KEY 环境变量")
    parser.add_argument("--limit", type=int, help="批量模式最多处理 N 个文件")
    parser.add_argument("--import", dest="import_to_db", action="store_true", help="抽取后导入 SQLite")
    parser.add_argument("--export-graph", action="store_true", help="导入后导出 graph.json")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 数据库路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出摘要")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    service = LLMExtractionService(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
    )

    if args.document:
        doc_path = args.document
        if not doc_path.exists():
            print(f"错误: 文件不存在: {doc_path}", file=sys.stderr)
            return 1
        summary = run_single(
            doc_path,
            service,
            output_dir=args.output,
            import_to_db=args.import_to_db,
            db_path=args.db,
            export_graph=args.export_graph,
            prompt_version=args.prompt_version,
        )
        summaries = [summary]
    else:
        dir_path: Path = args.directory
        if not dir_path.is_dir():
            print(f"错误: 目录不存在: {dir_path}", file=sys.stderr)
            return 1
        files = sorted(dir_path.glob("*.json"))
        if args.limit:
            files = files[: args.limit]
        print(f"批量抽取 {len(files)} 个文件\n")

        summaries = []
        for i, fp in enumerate(files, 1):
            print(f"\n--- [{i}/{len(files)}] ---")
            try:
                summary = run_single(
                    fp,
                    service,
                    output_dir=args.output,
                    import_to_db=args.import_to_db,
                    db_path=args.db,
                    export_graph=args.export_graph,
                    prompt_version=args.prompt_version,
                )
                summaries.append(summary)
            except Exception as exc:
                print(f"  失败: {exc}")
                summaries.append({"doc_id": fp.stem, "error": str(exc)})

    if args.json:
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
    else:
        ok = sum(1 for s in summaries if "error" not in s)
        fail = sum(1 for s in summaries if "error" in s)
        total_entities = sum(s.get("entities", 0) for s in summaries)
        total_relations = sum(s.get("relations", 0) for s in summaries)
        print(f"\n{'='*50}")
        print(f"完成: {ok} 成功, {fail} 失败, 共 {total_entities} 实体, {total_relations} 关系")

    return 0 if not any("error" in s for s in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
