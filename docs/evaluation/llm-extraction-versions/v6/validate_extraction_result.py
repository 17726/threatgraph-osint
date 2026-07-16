import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "docs/schemas/extraction-result.schema.json"

ALLOWED_RELATIONS = {
    "USES": {
        "heads": {"PERSON", "ORGANIZATION", "COUNTRY", "APT_GROUP", "CAMPAIGN", "MALWARE", "TOOL"},
        "tails": {"MALWARE", "TOOL", "TECHNIQUE", "INFRASTRUCTURE"},
        "pairs": {
            (head, tail)
            for head in {"PERSON", "ORGANIZATION", "COUNTRY", "APT_GROUP", "CAMPAIGN", "MALWARE", "TOOL"}
            for tail in {"MALWARE", "TOOL", "TECHNIQUE", "INFRASTRUCTURE"}
        },
    },
    "TARGETS": {
        "heads": {"APT_GROUP", "CAMPAIGN", "MALWARE"},
        "tails": {"COUNTRY", "REGION", "INDUSTRY", "ORGANIZATION", "PERSON", "LOCATION"},
        "pairs": {
            (head, tail)
            for head in {"APT_GROUP", "CAMPAIGN", "MALWARE"}
            for tail in {"COUNTRY", "REGION", "INDUSTRY", "ORGANIZATION", "PERSON", "LOCATION"}
        },
    },
    "EXPLOITS": {
        "heads": {
            "PERSON",
            "ORGANIZATION",
            "COUNTRY",
            "APT_GROUP",
            "CAMPAIGN",
            "MALWARE",
            "TOOL",
        },
        "tails": {"CVE"},
        "pairs": {
            (head, "CVE")
            for head in {
                "PERSON",
                "ORGANIZATION",
                "COUNTRY",
                "APT_GROUP",
                "CAMPAIGN",
                "MALWARE",
                "TOOL",
            }
        },
    },
    "ATTRIBUTED_TO": {
        "heads": {"APT_GROUP", "CAMPAIGN", "MALWARE"},
        "tails": {"COUNTRY", "ORGANIZATION", "APT_GROUP"},
        "pairs": {
            (head, tail)
            for head in {"APT_GROUP", "CAMPAIGN", "MALWARE"}
            for tail in {"COUNTRY", "ORGANIZATION", "APT_GROUP"}
        },
    },
    "AFFILIATED_WITH": {
        "heads": {"APT_GROUP", "ORGANIZATION"},
        "tails": {"APT_GROUP", "ORGANIZATION", "COUNTRY"},
        "pairs": {
            (head, tail)
            for head in {"APT_GROUP", "ORGANIZATION"}
            for tail in {"APT_GROUP", "ORGANIZATION", "COUNTRY"}
        },
    },
    "LOCATED_IN": {
        "heads": {"ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE", "EVENT"},
        "tails": {"COUNTRY", "REGION", "LOCATION"},
        "pairs": {
            (head, tail)
            for head in {"ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE", "EVENT"}
            for tail in {"COUNTRY", "REGION", "LOCATION"}
        },
    },
    "HAPPENED_AT": {
        "heads": {"EVENT", "CAMPAIGN"},
        "tails": {"TIME"},
        "pairs": {(head, "TIME") for head in {"EVENT", "CAMPAIGN"}},
    },
    "PART_OF": {
        "heads": {"ORGANIZATION", "EVENT", "CAMPAIGN", "APT_GROUP"},
        "tails": {"ORGANIZATION", "CAMPAIGN", "APT_GROUP"},
        "pairs": {
            ("ORGANIZATION", "ORGANIZATION"),
            ("ORGANIZATION", "APT_GROUP"),
            ("EVENT", "CAMPAIGN"),
            ("CAMPAIGN", "APT_GROUP"),
            ("APT_GROUP", "APT_GROUP"),
            ("APT_GROUP", "ORGANIZATION"),
        },
    },
    "LEADS_TO": {
        "heads": {"TECHNIQUE", "BEHAVIOR_PATTERN", "EVENT"},
        "tails": {"TECHNIQUE", "BEHAVIOR_PATTERN", "EVENT"},
        "pairs": {
            (head, tail)
            for head in {"TECHNIQUE", "BEHAVIOR_PATTERN", "EVENT"}
            for tail in {"TECHNIQUE", "BEHAVIOR_PATTERN", "EVENT"}
        },
    },
    "DISCOVERED_BY": {
        "heads": {"CVE", "MALWARE", "TOOL", "CAMPAIGN"},
        "tails": {"ORGANIZATION", "PERSON"},
        "pairs": {
            (head, tail)
            for head in {"CVE", "MALWARE", "TOOL", "CAMPAIGN"}
            for tail in {"ORGANIZATION", "PERSON"}
        },
    },
    "CAUSES": {
        "heads": {"CVE", "TECHNIQUE", "MALWARE"},
        "tails": {"EVENT", "BEHAVIOR_PATTERN"},
        "pairs": {
            (head, tail)
            for head in {"CVE", "TECHNIQUE", "MALWARE"}
            for tail in {"EVENT", "BEHAVIOR_PATTERN"}
        },
    },
    "HAS_BEHAVIOR": {
        "heads": {"APT_GROUP", "CAMPAIGN", "MALWARE"},
        "tails": {"BEHAVIOR_PATTERN", "TECHNIQUE"},
        "pairs": {
            (head, tail)
            for head in {"APT_GROUP", "CAMPAIGN", "MALWARE"}
            for tail in {"BEHAVIOR_PATTERN", "TECHNIQUE"}
        },
    },
    "MEMBER_OF": {
        "heads": {"PERSON"},
        "tails": {"APT_GROUP", "ORGANIZATION"},
        "pairs": {("PERSON", tail) for tail in {"APT_GROUP", "ORGANIZATION"}},
    },
    "CONTROLS": {
        "heads": {"PERSON", "APT_GROUP", "ORGANIZATION"},
        "tails": {"FINANCIAL_ACCOUNT", "INFRASTRUCTURE", "ORGANIZATION"},
        "pairs": {
            (head, tail)
            for head in {"PERSON", "APT_GROUP", "ORGANIZATION"}
            for tail in {"FINANCIAL_ACCOUNT", "INFRASTRUCTURE", "ORGANIZATION"}
        },
    },
    "TRANSFERS_TO": {
        "heads": {"FINANCIAL_ACCOUNT"},
        "tails": {"FINANCIAL_ACCOUNT"},
        "pairs": {("FINANCIAL_ACCOUNT", "FINANCIAL_ACCOUNT")},
    },
    "INSTANCE_OF": {
        "heads": {"ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE", "MALWARE", "TOOL"},
        "tails": {"ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE", "MALWARE", "TOOL"},
        "pairs": {
            (entity_type, entity_type)
            for entity_type in {"ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE", "MALWARE", "TOOL"}
        },
    },
    "PRECEDES": {
        "heads": {"EVENT", "CAMPAIGN", "TECHNIQUE", "BEHAVIOR_PATTERN"},
        "tails": {"EVENT", "CAMPAIGN", "TECHNIQUE", "BEHAVIOR_PATTERN"},
        "pairs": {
            (head, tail)
            for head in {"EVENT", "CAMPAIGN", "TECHNIQUE", "BEHAVIOR_PATTERN"}
            for tail in {"EVENT", "CAMPAIGN", "TECHNIQUE", "BEHAVIOR_PATTERN"}
        },
    },
    "RELATED_TO": {
        "heads": None,
        "tails": None,
    },
}


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def format_json_path(error_path: Any) -> str:
    parts = [str(part) for part in error_path]
    return "$" if not parts else "$." + ".".join(parts)


def validate_schema(payload: dict[str, Any], schema_path: Path, report: ValidationReport) -> None:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        report.add_error(f"schema {format_json_path(error.path)}: {error.message}")


def validate_relation_matrix(payload: dict[str, Any], report: ValidationReport) -> None:
    for chunk in payload.get("chunks", []):
        chunk_id = chunk.get("chunk_id", "<unknown>")
        entities = {
            (entity.get("name"), entity.get("type"))
            for entity in chunk.get("entities", [])
            if entity.get("name") and entity.get("type")
        }
        aliases = {
            (alias, entity.get("type"))
            for entity in chunk.get("entities", [])
            for alias in entity.get("aliases", [])
            if alias and entity.get("type")
        }
        known_entities = entities | aliases

        for index, relation in enumerate(chunk.get("relations", [])):
            prefix = f"{chunk_id}.relations[{index}]"
            relation_type = relation.get("relation_type")
            head_type = relation.get("head_type")
            tail_type = relation.get("tail_type")
            rule = ALLOWED_RELATIONS.get(relation_type)

            if rule is None:
                report.add_error(f"{prefix}: 未知关系类型 {relation_type!r}")
                continue

            if relation_type == "RELATED_TO":
                report.add_warning(f"{prefix}: RELATED_TO 只能作为人工确认的兜底关系")
            else:
                if head_type not in rule["heads"]:
                    report.add_error(
                        f"{prefix}: {relation_type} 不允许主体类型 {head_type}"
                    )
                if tail_type not in rule["tails"]:
                    report.add_error(
                        f"{prefix}: {relation_type} 不允许客体类型 {tail_type}"
                    )
                if (head_type, tail_type) not in rule["pairs"]:
                    report.add_error(
                        f"{prefix}: 不允许类型组合 {head_type} -> {relation_type} -> {tail_type}"
                    )

            head = (relation.get("head_name"), head_type)
            tail = (relation.get("tail_name"), tail_type)
            if head not in known_entities:
                report.add_error(f"{prefix}: 主体实体未在同一 chunk 的候选实体中声明")
            if tail not in known_entities:
                report.add_error(f"{prefix}: 客体实体未在同一 chunk 的候选实体中声明")


def validate_unique_chunk_ids(payload: dict[str, Any], report: ValidationReport) -> None:
    seen: set[str] = set()
    for chunk_index, chunk in enumerate(payload.get("chunks", [])):
        chunk_id = chunk.get("chunk_id", "")
        if chunk_id in seen:
            report.add_error(f"chunks[{chunk_index}]: 重复 chunk_id {chunk_id!r}")
        seen.add(chunk_id)


def validate_text_span(
    *,
    item: dict[str, Any],
    clean_text: str,
    item_path: str,
    report: ValidationReport,
) -> None:
    evidence_text = item.get("evidence_text", "")
    if not evidence_text.strip():
        report.add_error(f"{item_path}: evidence_text 不能为空")
        return

    if evidence_text not in clean_text:
        report.add_error(f"{item_path}: evidence_text 未出现在 document.clean_text 中")
        return

    char_start = item.get("char_start")
    char_end = item.get("char_end")
    if char_start is None and char_end is None:
        return
    if char_start is None or char_end is None:
        report.add_error(f"{item_path}: char_start 和 char_end 必须同时为空或同时填写")
        return
    if not isinstance(char_start, int) or not isinstance(char_end, int):
        report.add_error(f"{item_path}: char_start 和 char_end 必须是整数或 null")
        return
    if not (0 <= char_start < char_end <= len(clean_text)):
        report.add_error(f"{item_path}: 字符范围 {char_start}:{char_end} 超出 clean_text")
        return
    if clean_text[char_start:char_end] != evidence_text:
        report.add_error(f"{item_path}: 字符范围与 evidence_text 不一致")


def validate_document_alignment(
    payload: dict[str, Any], document: dict[str, Any], report: ValidationReport
) -> None:
    doc_id = payload.get("doc_id")
    document_doc_id = document.get("doc_id")
    clean_text = document.get("clean_text") or document.get("raw_text", "")

    if doc_id != document_doc_id:
        report.add_error(f"doc_id 不一致: result={doc_id!r}, document={document_doc_id!r}")
    if not clean_text:
        report.add_error("document.clean_text 不能为空")
        return

    for chunk_index, chunk in enumerate(payload.get("chunks", [])):
        chunk_id = chunk.get("chunk_id", "")
        if doc_id and not chunk_id.startswith(f"{doc_id}_c"):
            report.add_error(f"chunks[{chunk_index}]: chunk_id 未使用 {doc_id}_cNNN 形式")

        for entity_index, entity in enumerate(chunk.get("entities", [])):
            validate_text_span(
                item=entity,
                clean_text=clean_text,
                item_path=f"{chunk_id}.entities[{entity_index}]",
                report=report,
            )
        for relation_index, relation in enumerate(chunk.get("relations", [])):
            validate_text_span(
                item=relation,
                clean_text=clean_text,
                item_path=f"{chunk_id}.relations[{relation_index}]",
                report=report,
            )


def validate_payload(
    payload: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    document: dict[str, Any] | None = None,
) -> ValidationReport:
    report = ValidationReport()
    validate_schema(payload, schema_path, report)

    if report.errors:
        return report

    validate_unique_chunk_ids(payload, report)
    validate_relation_matrix(payload, report)
    if document is not None:
        validate_document_alignment(payload, document, report)
    return report


def validate_file(
    extraction_path: Path,
    *,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    document_path: Path | None = None,
) -> ValidationReport:
    payload = load_json(extraction_path)
    document = load_json(document_path) if document_path else None
    return validate_payload(payload, schema_path=schema_path, document=document)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="校验 ThreatGraph LLM extraction_result.json 候选抽取结果。"
    )
    parser.add_argument("extraction_result", type=Path, help="待校验的 extraction_result.json")
    parser.add_argument(
        "--document",
        type=Path,
        help="可选：对应 document.json，用于校验 doc_id、chunk_id、evidence_text 和字符范围。",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"JSON schema 路径，默认 {DEFAULT_SCHEMA_PATH}",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出校验报告")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    report = validate_file(
        args.extraction_result,
        schema_path=args.schema,
        document_path=args.document,
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
        if report.ok:
            print(f"校验通过: {args.extraction_result}")
        else:
            for error in report.errors:
                print(f"错误: {error}", file=sys.stderr)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
