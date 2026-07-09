import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.demo_store import DEFAULT_DB_PATH
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from scripts.export_graph_json import DEFAULT_OUTPUT_PATH, export_graph_json


def import_extraction_result(
    document_path: str | Path,
    extraction_result_path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
    graph_output_path: str | Path | None = None,
):
    pipeline = OfflineExtractionPipeline(db_path)
    summary = pipeline.run(document_path, extraction_result_path)
    if graph_output_path is not None:
        export_graph_json(db_path, graph_output_path, seed_demo=False)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="导入本地 document.json 和 extraction_result.json，写入 SQLite 候选层并归一化为正式图谱。"
    )
    parser.add_argument("--document", required=True, type=Path, help="document.json 路径")
    parser.add_argument(
        "--extraction-result",
        required=True,
        type=Path,
        help="extraction_result.json 路径",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 数据库路径")
    parser.add_argument(
        "--export-graph",
        type=Path,
        nargs="?",
        const=DEFAULT_OUTPUT_PATH,
        help="导入后导出 graph.json；不传值时使用 data/graph/graph.json",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出导入摘要")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = import_extraction_result(
        args.document,
        args.extraction_result,
        args.db,
        args.export_graph,
    )
    payload = {
        "doc_id": summary.doc_id,
        "run_id": summary.run_id,
        "chunks": summary.chunks,
        "extracted_entities": summary.extracted_entities,
        "extracted_relations": summary.extracted_relations,
        "canonical_entities": summary.canonical_entities,
        "canonical_relations": summary.canonical_relations,
        "evidence": summary.evidence,
        "behavior_patterns": summary.behavior_patterns,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "导入完成："
            f"doc_id={summary.doc_id}, run_id={summary.run_id}, "
            f"候选实体={summary.extracted_entities}, 候选关系={summary.extracted_relations}, "
            f"正式实体={summary.canonical_entities}, 正式关系={summary.canonical_relations}, "
            f"证据={summary.evidence}, 行为模式={summary.behavior_patterns}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
