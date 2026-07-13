"""Evaluate an extraction_result.json against a manually reviewed golden file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.extraction_evaluator import (
    evaluate_extraction,
    validate_golden_payload,
    validate_golden_schema,
)
from backend.app.services.artifact_naming import evaluation_filename
from scripts.validate_extraction_result import load_json, validate_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="计算 LLM 候选抽取相对 golden 的实体/关系 Precision、Recall 和 F1。"
    )
    parser.add_argument("--extraction-result", type=Path, required=True)
    parser.add_argument("--golden", type=Path, required=True)
    parser.add_argument("--document", type=Path, help="用于同时校验证据和字符位置")
    parser.add_argument(
        "--candidate-audit",
        type=Path,
        help="可选：runner 保存的被过滤原始候选审计，计入 false positive",
    )
    parser.add_argument("--output", type=Path, help="可选：写入完整 JSON 评测报告")
    parser.add_argument("--golden-schema", type=Path)
    parser.add_argument("--min-entity-f1", type=float, default=0.0)
    parser.add_argument("--min-relation-f1", type=float, default=0.0)
    parser.add_argument("--json", action="store_true", help="向标准输出打印完整 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    extraction_result = load_json(args.extraction_result)
    golden = load_json(args.golden)
    document = load_json(args.document) if args.document else None
    candidate_audit = load_json(args.candidate_audit) if args.candidate_audit else None

    extraction_report = validate_payload(extraction_result, document=document)
    golden_errors = [
        *validate_golden_schema(golden, args.golden_schema),
        *validate_golden_payload(golden, document=document),
    ]
    if not extraction_report.ok or golden_errors:
        for error in extraction_report.errors:
            print(f"extraction_result 错误: {error}", file=sys.stderr)
        for error in golden_errors:
            print(f"golden 错误: {error}", file=sys.stderr)
        return 1

    try:
        result = evaluate_extraction(
            extraction_result,
            golden,
            candidate_audit=candidate_audit,
        )
    except ValueError as exc:
        print(f"评测输入错误: {exc}", file=sys.stderr)
        return 1

    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        args.output = Path("data/evaluation") / evaluation_filename(
            doc_id=result["extraction"]["doc_id"],
            model_name=result["extraction"]["model_name"],
            prompt_version=result["extraction"]["prompt_version"],
            schema_version=result["extraction"]["schema_version"],
            golden_version=result["golden"]["golden_version"],
            evaluated_at=result["evaluated_at"],
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")

    if args.json:
        print(serialized, end="")
    else:
        entity = result["entity_metrics"]
        relation = result["relation_metrics"]
        print(
            "实体: "
            f"P={entity['precision']:.4f} R={entity['recall']:.4f} F1={entity['f1']:.4f} "
            f"(TP={entity['true_positive']} FP={entity['false_positive']} FN={entity['false_negative']})"
        )
        print(
            "关系: "
            f"P={relation['precision']:.4f} R={relation['recall']:.4f} F1={relation['f1']:.4f} "
            f"(TP={relation['true_positive']} FP={relation['false_positive']} FN={relation['false_negative']})"
        )
        print(f"完整报告: {args.output}")

    entity_failed = result["entity_metrics"]["f1"] < args.min_entity_f1
    relation_failed = result["relation_metrics"]["f1"] < args.min_relation_f1
    return 2 if entity_failed or relation_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
