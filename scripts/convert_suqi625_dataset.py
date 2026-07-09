import argparse
import copy
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.convert_raw_documents import (
    REPO_ROOT,
    convert_raw_record,
    document_output_path,
    merge_document,
    normalize_tags,
    normalize_target_group,
    source_reliability,
    target_group_sort_key,
    write_documents,
)


CONVERTER_NAME = "scripts/convert_suqi625_dataset.py"
DEFAULT_INPUT_DIR = REPO_ROOT / "tmp/cleaned"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/documents"
DEFAULT_SOURCES_INPUT = REPO_ROOT / "tmp/sources/sources_index.json"
DEFAULT_SOURCES_OUTPUT = REPO_ROOT / "data/sources/sources_index.suqi625.json"
DEFAULT_GOLDEN_INPUT = REPO_ROOT / "tmp/evaluation/golden.json"
DEFAULT_GOLDEN_OUTPUT = REPO_ROOT / "data/evaluation/golden.suqi625.json"
DOC_ID_PREFIX = "suqi625"
COLLECTOR_GITHUB = "SuQi625"


@dataclass
class Suqi625ConversionStats:
    input_records: int = 0
    output_documents: int = 0
    merged_duplicates: int = 0
    skipped_empty_text: int = 0
    skipped_too_short: int = 0
    skipped_existing_url: int = 0
    skipped_duplicate_content: int = 0
    skipped_low_relevance: int = 0


SOCIAL_SECURITY_KEYWORDS = re.compile(
    r"\bAPT(?:\d+)?\b|(?i:\b("
    r"kimsuky|cyber|malware|phish|exploit|vulnerab|cve|backdoor|threat|hacker|"
    r"ransom|trojan|stealer|campaign|credential|npm|opsec|zero[- ]day|"
    r"breach|defen[cs]e|blueNoroff|fancy bear|lazarus group|remote[- ]worker"
    r")\b)",
)


def normalize_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def prefixed_doc_id(doc_id: str) -> str:
    doc_id = str(doc_id).strip()
    return doc_id if doc_id.startswith(f"{DOC_ID_PREFIX}_") else f"{DOC_ID_PREFIX}_{doc_id}"


def convert_cleaned_record(record: dict[str, Any], cleaned_path: str | Path) -> dict[str, Any]:
    document = convert_raw_record(record, cleaned_path)
    legacy_content_hash = record.get("content_hash")

    document["doc_id"] = prefixed_doc_id(document["doc_id"])
    document["metadata"].update(
        {
            "collector_github": COLLECTOR_GITHUB,
            "cleaned_path": normalize_path(cleaned_path),
            "converter": CONVERTER_NAME,
        }
    )
    if legacy_content_hash:
        document["metadata"]["legacy_content_hash"] = str(legacy_content_hash)
        document["metadata"]["legacy_content_hash_algorithm"] = "md5"
    return document


def build_new_documents(
    records: Iterable[tuple[dict[str, Any], str | Path]],
    *,
    existing_source_urls: set[str],
    existing_content_hashes: set[str] | None = None,
    min_clean_chars: int = 500,
) -> tuple[list[dict[str, Any]], Suqi625ConversionStats]:
    stats = Suqi625ConversionStats()
    documents_by_url: dict[str, dict[str, Any]] = {}
    ordered_urls: list[str] = []
    seen_content_hashes = set(existing_content_hashes or set())

    for record, cleaned_path in records:
        stats.input_records += 1
        document = convert_cleaned_record(record, cleaned_path)
        clean_text = document["clean_text"]
        if not clean_text:
            stats.skipped_empty_text += 1
            continue
        if len(clean_text) < min_clean_chars:
            stats.skipped_too_short += 1
            continue
        if document["source_url"] in existing_source_urls:
            stats.skipped_existing_url += 1
            continue
        if not is_relevant_social_document(document):
            stats.skipped_low_relevance += 1
            continue

        key = document["source_url"]
        if key in documents_by_url:
            merge_document(documents_by_url[key], document)
            stats.merged_duplicates += 1
            continue
        if document["content_hash"] in seen_content_hashes:
            stats.skipped_duplicate_content += 1
            continue

        documents_by_url[key] = document
        ordered_urls.append(key)
        seen_content_hashes.add(document["content_hash"])

    documents = [documents_by_url[url] for url in ordered_urls]
    stats.output_documents = len(documents)
    return documents, stats


def is_relevant_social_document(document: dict[str, Any]) -> bool:
    if document["source_type"] != "social_forum":
        return True
    text = f"{document.get('title', '')}\n{document.get('clean_text', '')}"
    return bool(SOCIAL_SECURITY_KEYWORDS.search(text))


def load_json_records(input_dir: Path) -> list[tuple[dict[str, Any], str]]:
    records: list[tuple[dict[str, Any], str]] = []
    for path in sorted(input_dir.rglob("*.json")):
        with path.open(encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        try:
            cleaned_path = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            cleaned_path = path.as_posix()
        records.append((payload, cleaned_path))
    return records


def load_existing_source_urls(documents_dir: Path) -> set[str]:
    urls: set[str] = set()
    for path in sorted(documents_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        source_url = payload.get("source_url")
        if isinstance(source_url, str) and source_url:
            urls.add(source_url)
    return urls


def load_existing_content_hashes(documents_dir: Path) -> set[str]:
    hashes: set[str] = set()
    for path in sorted(documents_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        content_hash = payload.get("content_hash")
        if isinstance(content_hash, str) and content_hash:
            hashes.add(content_hash)
    return hashes


def build_sources_index(
    original_index: dict[str, Any],
    documents: list[dict[str, Any]],
    stats: Suqi625ConversionStats,
) -> dict[str, Any]:
    original_sources_by_name = {
        source.get("name"): source for source in original_index.get("sources", []) if isinstance(source, dict)
    }
    docs_by_source: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        docs_by_source.setdefault(document["source_name"], []).append(document)

    sources: list[dict[str, Any]] = []
    for source_name in sorted(docs_by_source):
        docs = docs_by_source[source_name]
        original = copy.deepcopy(original_sources_by_name.get(source_name, {}))
        source_type = docs[0]["source_type"]
        reliability = source_reliability(source_name)
        group_counts = Counter(doc["target_group"] for doc in docs)
        source = {
            "source_id": original.get("source_id") or source_name.lower().replace(" ", "_"),
            "name": source_name,
            "source_type": source_type,
            "collector_type": original.get("collector_type", "local_json"),
            "url": original.get("url", ""),
            "target_groups_json": sorted(group_counts, key=target_group_sort_key),
            "source_reliability": reliability,
            "tags_json": normalize_tags([source_type, *original.get("tags_json", [])]),
            "enabled": original.get("enabled", True),
            "config_json": {
                **original.get("config_json", {}),
                "document_count_by_group": dict(group_counts),
                "total_document_count": len(docs),
            },
            "created_at": original.get("created_at") or original_index.get("created_at"),
            "updated_at": original_index.get("created_at"),
        }
        sources.append(source)

    documents_by_group = Counter(document["target_group"] for document in documents)
    documents_by_reliability = Counter(document["source_reliability"] for document in documents)
    return {
        "schema_version": original_index.get("schema_version", "1.0"),
        "created_at": original_index.get("created_at"),
        "description": "SuQi625 数据组补充数据的来源索引，仅统计本次新增入库文档。",
        "sources": sources,
        "summary": {
            "total_sources": len(sources),
            "total_documents": len(documents),
            "documents_by_group": dict(documents_by_group),
            "documents_by_reliability": dict(documents_by_reliability),
            "skipped_existing_url": stats.skipped_existing_url,
            "skipped_too_short": stats.skipped_too_short,
            "merged_duplicates": stats.merged_duplicates,
            "original_summary": original_index.get("summary", {}),
        },
    }


def normalize_golden_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    for document in result.get("documents", []):
        if "published_date" in document:
            document["published_at"] = document.pop("published_date") or None
        if "text" in document:
            document["clean_text"] = document.pop("text")
        document["target_group"] = normalize_target_group(document.get("target_group", ""))
        document["source_type"] = {
            "threat_report": "vendor_report",
            "news_article": "news",
            "social_forum": "social_forum",
        }.get(document.get("source_type"), document.get("source_type"))

    result["metadata"] = {
        "collector_github": COLLECTOR_GITHUB,
        "source_path": "tmp/evaluation/golden.json",
        "normalizer": CONVERTER_NAME,
        "note": "该文件用于人工评测，不是 LLM 候选抽取结果。",
    }
    return result


def write_json(payload: dict[str, Any], path: Path, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} 已存在；如需覆盖请传 --overwrite")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="转换 SuQi625 数据组补充数据为仓库标准格式。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_DIR, help="SuQi625 cleaned JSON 根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="标准 document 输出根目录")
    parser.add_argument("--sources-input", type=Path, default=DEFAULT_SOURCES_INPUT, help="来源索引输入文件")
    parser.add_argument("--sources-output", type=Path, default=DEFAULT_SOURCES_OUTPUT, help="来源索引输出文件")
    parser.add_argument("--golden-input", type=Path, default=DEFAULT_GOLDEN_INPUT, help="golden 输入文件")
    parser.add_argument("--golden-output", type=Path, default=DEFAULT_GOLDEN_OUTPUT, help="golden 输出文件")
    parser.add_argument("--min-clean-chars", type=int, default=500, help="清洗正文少于该长度时跳过")
    parser.add_argument("--write", action="store_true", help="实际写入输出文件；默认只 dry-run")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出文件")
    parser.add_argument("--json", action="store_true", help="用 JSON 输出统计结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    records = load_json_records(args.input)
    existing_urls = load_existing_source_urls(args.output)
    existing_hashes = load_existing_content_hashes(args.output)
    documents, stats = build_new_documents(
        records,
        existing_source_urls=existing_urls,
        existing_content_hashes=existing_hashes,
        min_clean_chars=args.min_clean_chars,
    )

    if args.write:
        write_documents(documents, args.output, overwrite=args.overwrite)
        if args.sources_input.exists():
            source_index = json.loads(args.sources_input.read_text(encoding="utf-8-sig"))
            write_json(build_sources_index(source_index, documents, stats), args.sources_output, overwrite=args.overwrite)
        if args.golden_input.exists():
            golden = json.loads(args.golden_input.read_text(encoding="utf-8-sig"))
            write_json(normalize_golden_payload(golden), args.golden_output, overwrite=args.overwrite)

    payload = {
        **asdict(stats),
        "input": str(args.input),
        "output": str(args.output),
        "dry_run": not args.write,
        "candidate_output_paths": [str(document_output_path(document, args.output)) for document in documents],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "写入完成" if args.write else "dry-run 完成"
        print(
            f"{action}: 输入 {stats.input_records} 条，输出 {stats.output_documents} 份，"
            f"跳过已入库 URL {stats.skipped_existing_url} 条，过短跳过 {stats.skipped_too_short} 条，"
            f"低相关跳过 {stats.skipped_low_relevance} 条，重复正文跳过 {stats.skipped_duplicate_content} 条，"
            f"合并重复 {stats.merged_duplicates} 条。"
        )
        if not args.write:
            print("未写入文件；确认无误后加 --write 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
