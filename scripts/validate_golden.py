import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.validate_extraction_result import (
    REPO_ROOT,
    ValidationReport,
    load_json,
    validate_relation_matrix,
    validate_schema,
    validate_text_span,
)


DEFAULT_SCHEMA_PATH = REPO_ROOT / "docs/schemas/golden.schema.json"
IPV4_PATTERN = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def looks_like_infrastructure(name: str) -> bool:
    normalized = name.strip().lower().replace("[.]", ".")
    return (
        "://" in normalized
        or "[.]" in name
        or bool(IPV4_PATTERN.fullmatch(normalized))
    )


def validate_document_alignment(
    payload: dict[str, Any],
    documents: dict[str, dict[str, Any]],
    report: ValidationReport,
) -> None:
    declared_doc_ids = set(payload.get("doc_ids", []))
    if declared_doc_ids != set(documents):
        report.add_error(
            "doc_ids 与传入文档不一致: "
            f"golden={sorted(declared_doc_ids)!r}, documents={sorted(documents)!r}"
        )

    for chunk_index, chunk in enumerate(payload.get("chunks", [])):
        doc_id = chunk.get("doc_id")
        chunk_id = chunk.get("chunk_id", f"chunks[{chunk_index}]")
        document = documents.get(doc_id)
        if document is None:
            report.add_error(f"{chunk_id}: 找不到 doc_id={doc_id!r} 对应的 document")
            continue
        if not chunk_id.startswith(f"{doc_id}_c"):
            report.add_error(f"{chunk_id}: chunk_id 未使用 {doc_id}_cNNN 形式")

        clean_text = document.get("clean_text") or document.get("raw_text", "")
        if not clean_text:
            report.add_error(f"{doc_id}: document.clean_text 不能为空")
            continue

        for entity_index, entity in enumerate(chunk.get("entities", [])):
            entity_path = f"{chunk_id}.entities[{entity_index}]"
            validate_text_span(
                item=entity,
                clean_text=clean_text,
                item_path=entity_path,
                report=report,
            )
            if looks_like_infrastructure(entity.get("name", "")) and entity.get(
                "type"
            ) != "INFRASTRUCTURE":
                report.add_error(
                    f"{entity_path}: 明显的域名、IP 或 URL 应标注为 INFRASTRUCTURE"
                )

        for relation_index, relation in enumerate(chunk.get("relations", [])):
            validate_text_span(
                item=relation,
                clean_text=clean_text,
                item_path=f"{chunk_id}.relations[{relation_index}]",
                report=report,
            )


def validate_golden_payload(
    payload: dict[str, Any],
    *,
    documents: dict[str, dict[str, Any]],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> ValidationReport:
    report = ValidationReport()
    validate_schema(payload, schema_path, report)
    if report.errors:
        return report

    validate_relation_matrix(payload, report)
    validate_document_alignment(payload, documents, report)
    return report


def validate_golden_file(
    golden_path: Path,
    *,
    document_paths: list[Path],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> ValidationReport:
    documents = {}
    for document_path in document_paths:
        document = load_json(document_path)
        doc_id = document.get("doc_id")
        if doc_id:
            documents[doc_id] = document
    return validate_golden_payload(
        load_json(golden_path), documents=documents, schema_path=schema_path
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验 ThreatGraph 正式黄金集。")
    parser.add_argument("golden", type=Path, help="待校验的 golden.json")
    parser.add_argument("documents", type=Path, nargs="+", help="黄金集引用的 document.json")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出校验报告")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_golden_file(
        args.golden, document_paths=args.documents, schema_path=args.schema
    )
    if args.json:
        print(
            json.dumps(
                {"ok": report.ok, "errors": report.errors, "warnings": report.warnings},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for warning in report.warnings:
            print(f"警告: {warning}")
        for error in report.errors:
            print(f"错误: {error}", file=sys.stderr)
        if report.ok:
            print(f"校验通过: {args.golden}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
