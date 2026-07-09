import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = REPO_ROOT / "data/raw"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/documents"
CONVERTER_NAME = "scripts/convert_raw_documents.py"

LEGACY_REQUIRED_FIELDS = [
    "doc_id",
    "target_group",
    "source_url",
    "source_type",
    "source_name",
    "title",
    "language",
    "raw_text",
    "published_date",
    "crawl_time",
    "tags",
]

TARGET_GROUP_NAMES = {
    "apt28": "APT28",
    "kimsuky": "Kimsuky",
    "lazarus": "Lazarus",
}

SOURCE_RELIABILITY_BY_NAME = {
    "Palo Alto Unit 42": "A",
    "奇安信威胁情报中心": "A",
    "The Hacker News": "B",
    "FreeBuf": "C",
    "Reddit": "D",
}

VENDOR_REPORT_SOURCES = {
    "Palo Alto Unit 42",
    "奇安信威胁情报中心",
    "Kaspersky Securelist",
    "Microsoft",
    "Mandiant",
    "ESET",
}

TRUNCATE_MARKERS = [
    "\n*本文作者",
    "\n转载请注明",
    "\nFound this article interesting? Follow us on",
    "\nBack to top\nTAGS\n",
    "\nRELATED ARTICLES\n",
    "\nRelated Resources\n",
]

DROP_LINE_PATTERNS = [
    re.compile(r"^（?图\s*\d+[:：].*[）)]?$", re.IGNORECASE),
    re.compile(r"^Figure\s+\d+[.:].*$", re.IGNORECASE),
    re.compile(r"^Share this article$", re.IGNORECASE),
    re.compile(r"^Read now$", re.IGNORECASE),
    re.compile(r"^Read more$", re.IGNORECASE),
    re.compile(r"^Back to top$", re.IGNORECASE),
]


@dataclass
class ConversionStats:
    input_records: int = 0
    output_documents: int = 0
    merged_duplicates: int = 0
    skipped_empty_text: int = 0
    skipped_too_short: int = 0


def normalize_raw_path(raw_path: str | Path) -> str:
    return str(raw_path).replace("\\", "/")


def normalize_target_group(value: str) -> str:
    normalized = str(value).strip()
    return TARGET_GROUP_NAMES.get(normalized.lower(), normalized)


def target_group_sort_key(value: str) -> tuple[int, str]:
    order = {"APT28": 0, "Kimsuky": 1, "Lazarus": 2}
    return (order.get(value, 100), value.lower())


def normalize_tags(tags: Iterable[Any] | None) -> list[str]:
    if not tags:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = str(tag).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def map_source_type(legacy_source_type: str, source_name: str) -> str:
    legacy = str(legacy_source_type).strip()
    if legacy == "news_article":
        return "news"
    if legacy == "threat_report":
        return "vendor_report" if source_name in VENDOR_REPORT_SOURCES else "security_report"
    if legacy in {"social_media", "forum_post", "social_forum"}:
        return "social_forum"
    if legacy == "cve_database":
        return "knowledge_base"
    if legacy == "cert_alert":
        return "government_notice"
    if legacy == "blog":
        return "blog"
    return "other"


def source_reliability(source_name: str) -> str:
    return SOURCE_RELIABILITY_BY_NAME.get(source_name, "unknown")


def light_clean_text(raw_text: str) -> str:
    text = str(raw_text or "")
    text = text.replace("\ufeff", "").replace("\xa0", " ").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    for marker in TRUNCATE_MARKERS:
        index = text.find(marker)
        if index >= 0:
            text = text[:index]

    cleaned_lines: list[str] = []
    previous_blank = False
    for line in text.split("\n"):
        stripped = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if any(pattern.match(stripped) for pattern in DROP_LINE_PATTERNS):
            continue

        if not stripped:
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue

        cleaned_lines.append(stripped)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_legacy_record(record: dict[str, Any], raw_path: str | Path) -> None:
    missing = [field for field in LEGACY_REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValueError(f"{normalize_raw_path(raw_path)} 缺少旧字段: {', '.join(missing)}")

    if record.get("language") not in {"zh", "en"}:
        raise ValueError(f"{normalize_raw_path(raw_path)} language 非法: {record.get('language')!r}")
    if not isinstance(record.get("tags"), list):
        raise ValueError(f"{normalize_raw_path(raw_path)} tags 必须是数组")


def convert_raw_record(record: dict[str, Any], raw_path: str | Path) -> dict[str, Any]:
    validate_legacy_record(record, raw_path)

    clean_text = light_clean_text(record["raw_text"])
    target_group = normalize_target_group(record["target_group"])
    source_name = str(record["source_name"]).strip()
    source_type = map_source_type(record["source_type"], source_name)
    raw_path_text = normalize_raw_path(raw_path)

    tags = normalize_tags(record.get("tags"))
    if source_type not in tags:
        tags.append(source_type)

    return {
        "doc_id": str(record["doc_id"]).strip(),
        "schema_version": "1.0",
        "target_group": target_group,
        "target_groups": [target_group],
        "source_url": str(record["source_url"]).strip(),
        "source_type": source_type,
        "source_name": source_name,
        "title": str(record["title"]).strip(),
        "language": record["language"],
        "clean_text": clean_text,
        "content_hash": sha256_text(clean_text),
        "published_at": record["published_date"] or None,
        "retrieved_at": record["crawl_time"],
        "source_reliability": source_reliability(source_name),
        "tlp": "TLP:CLEAR",
        "tags": tags,
        "metadata": {
            "collector": "data",
            "legacy_doc_id": record["doc_id"],
            "legacy_source_type": record["source_type"],
            "raw_path": raw_path_text,
            "converter": CONVERTER_NAME,
            "cleaning": "light_format_cleaning",
        },
    }


def merge_document(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    for target_group in incoming["target_groups"]:
        if target_group not in existing["target_groups"]:
            existing["target_groups"].append(target_group)
    existing["target_groups"].sort(key=target_group_sort_key)

    existing["tags"] = normalize_tags([*existing.get("tags", []), *incoming.get("tags", [])])

    metadata = existing.setdefault("metadata", {})
    if "merged_legacy_doc_ids" not in metadata:
        metadata["merged_legacy_doc_ids"] = [metadata.get("legacy_doc_id")]
    if "merged_raw_paths" not in metadata:
        metadata["merged_raw_paths"] = [metadata.get("raw_path")]

    incoming_metadata = incoming.get("metadata", {})
    incoming_doc_id = incoming_metadata.get("legacy_doc_id")
    incoming_raw_path = incoming_metadata.get("raw_path")
    if incoming_doc_id and incoming_doc_id not in metadata["merged_legacy_doc_ids"]:
        metadata["merged_legacy_doc_ids"].append(incoming_doc_id)
    if incoming_raw_path and incoming_raw_path not in metadata["merged_raw_paths"]:
        metadata["merged_raw_paths"].append(incoming_raw_path)

    if incoming["content_hash"] != existing["content_hash"]:
        hashes = metadata.setdefault("merged_content_hashes", [existing["content_hash"]])
        if incoming["content_hash"] not in hashes:
            hashes.append(incoming["content_hash"])


def build_documents(
    records: Iterable[tuple[dict[str, Any], str | Path]],
    *,
    min_clean_chars: int = 1,
) -> tuple[list[dict[str, Any]], ConversionStats]:
    stats = ConversionStats()
    documents_by_url: dict[str, dict[str, Any]] = {}
    ordered_urls: list[str] = []

    for record, raw_path in records:
        stats.input_records += 1
        document = convert_raw_record(record, raw_path)
        clean_text = document["clean_text"]
        if not clean_text:
            stats.skipped_empty_text += 1
            continue
        if len(clean_text) < min_clean_chars:
            stats.skipped_too_short += 1
            continue

        key = document["source_url"]
        if key in documents_by_url:
            merge_document(documents_by_url[key], document)
            stats.merged_duplicates += 1
            continue

        documents_by_url[key] = document
        ordered_urls.append(key)

    documents = [documents_by_url[url] for url in ordered_urls]
    stats.output_documents = len(documents)
    return documents, stats


def load_raw_records(input_dir: Path) -> list[tuple[dict[str, Any], str]]:
    records: list[tuple[dict[str, Any], str]] = []
    for path in sorted(input_dir.rglob("*.json")):
        with path.open(encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        try:
            raw_path = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            raw_path = path.as_posix()
        records.append((payload, raw_path))
    return records


def document_output_path(document: dict[str, Any], output_dir: Path) -> Path:
    group_dir = document["target_group"].lower()
    return output_dir / group_dir / f"{document['doc_id']}.json"


def write_documents(documents: list[dict[str, Any]], output_dir: Path, *, overwrite: bool) -> None:
    for document in documents:
        output_path = document_output_path(document, output_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"{output_path} 已存在；如需覆盖请传 --overwrite")
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将旧版 data/raw 爬虫输出转换为 P0 document.json 契约。"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_DIR, help="旧版 raw JSON 根目录")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="标准 document.json 输出根目录",
    )
    parser.add_argument(
        "--min-clean-chars",
        type=int,
        default=500,
        help="清洗正文少于该长度时跳过，默认 500 用于过滤低价值短页面",
    )
    parser.add_argument("--write", action="store_true", help="实际写入输出目录；默认只 dry-run")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出文件")
    parser.add_argument("--json", action="store_true", help="用 JSON 输出统计结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = load_raw_records(args.input)
    documents, stats = build_documents(records, min_clean_chars=args.min_clean_chars)

    if args.write:
        write_documents(documents, args.output, overwrite=args.overwrite)

    payload = {
        **asdict(stats),
        "input": str(args.input),
        "output": str(args.output),
        "dry_run": not args.write,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "写入完成" if args.write else "dry-run 完成"
        print(
            f"{action}: 输入 {stats.input_records} 条，输出 {stats.output_documents} 份，"
            f"合并重复 {stats.merged_duplicates} 条，空文本跳过 {stats.skipped_empty_text} 条，"
            f"过短跳过 {stats.skipped_too_short} 条。"
        )
        if not args.write:
            print("未写入文件；确认无误后加 --write 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
