from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = {
    "doc_id",
    "schema_version",
    "target_group",
    "target_groups",
    "source_url",
    "source_type",
    "source_name",
    "title",
    "language",
    "clean_text",
    "content_hash",
    "published_at",
    "retrieved_at",
    "source_reliability",
    "tlp",
    "tags",
    "metadata",
}
VALID_SOURCE_TYPES = {
    "security_report",
    "vendor_report",
    "knowledge_base",
    "government_notice",
    "news",
    "social_forum",
    "blog",
    "other",
}
VALID_LANGUAGES = {"zh", "en"}
DOC_ID_PATTERN = re.compile(r"^(?P<group>[a-z0-9][a-z0-9_-]*)_(?P<number>\d+)$")
HASH_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


@dataclass
class PromotionStats:
    promoted: int = 0
    skipped: int = 0
    errors: int = 0


def positive_start_number(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("start-number must be greater than zero")
    return number


def safe_slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value.strip().lower()).strip("._-") or "unknown"


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def next_document_number(output_dir: Path, target_group: str) -> int:
    group_slug = safe_slug(target_group)
    max_number = 0
    if not output_dir.exists():
        return 1
    for path in output_dir.glob(f"{group_slug}_*.json"):
        match = DOC_ID_PATTERN.fullmatch(path.stem)
        if match and match.group("group") == group_slug:
            max_number = max(max_number, int(match.group("number")))
    return max_number + 1


def validate_document(document: dict[str, Any], path: Path) -> None:
    missing = REQUIRED_FIELDS - document.keys()
    if missing:
        raise ValueError(f"{path}: missing fields: {', '.join(sorted(missing))}")
    if document["schema_version"] != "1.0":
        raise ValueError(f"{path}: schema_version must be 1.0")
    if not isinstance(document["target_group"], str) or not document["target_group"].strip():
        raise ValueError(f"{path}: target_group is empty")
    if not isinstance(document["target_groups"], list) or not document["target_groups"]:
        raise ValueError(f"{path}: target_groups must be a non-empty list")
    if document["source_type"] not in VALID_SOURCE_TYPES:
        raise ValueError(f"{path}: invalid source_type: {document['source_type']}")
    if document["language"] not in VALID_LANGUAGES:
        raise ValueError(f"{path}: invalid language: {document['language']}")
    if not isinstance(document["clean_text"], str) or not document["clean_text"].strip():
        raise ValueError(f"{path}: clean_text is empty")
    content_hash = document["content_hash"]
    if not isinstance(content_hash, str) or not HASH_PATTERN.fullmatch(content_hash):
        raise ValueError(f"{path}: invalid content_hash")
    if content_hash != sha256_text(document["clean_text"]):
        raise ValueError(f"{path}: content_hash does not match clean_text")
    if not isinstance(document["metadata"], dict):
        raise ValueError(f"{path}: metadata must be an object")


def load_documents(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    documents = []
    if not directory.exists():
        return documents
    for path in sorted(directory.rglob("*.json")):
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: document must be an object")
        documents.append((path, payload))
    return documents


def _rewrite_metadata_paths(
    metadata: dict[str, Any],
    old_doc_id: str,
    new_doc_id: str,
    group_slug: str,
    input_root: Path,
    output_root: Path,
) -> None:
    old_input_path = f"data/cleaned/{group_slug}/{old_doc_id}.json"
    new_input_path = f"data/cleaned/{group_slug}/{new_doc_id}.json"
    new_output_path = f"data/documents/{group_slug}/{new_doc_id}.json"
    for key in ("doc_id", "document_id", "legacy_doc_id"):
        if metadata.get(key) == old_doc_id:
            metadata[key] = new_doc_id
    for key in ("source_path", "cleaned_path", "document_path"):
        value = metadata.get(key)
        if not isinstance(value, str):
            continue
        if value == old_input_path or value.endswith(f"/{old_doc_id}.json") or value.endswith(
            f"\\{old_doc_id}.json"
        ):
            metadata[key] = new_output_path if key != "cleaned_path" else new_input_path


def promote_documents(
    input_dir: Path,
    output_dir: Path,
    start_number: int = 1,
) -> PromotionStats:
    if start_number < 1:
        raise ValueError("start_number must be greater than zero")
    stats = PromotionStats()
    next_numbers: dict[str, int] = {}

    for path, document in load_documents(input_dir):
        try:
            validate_document(document, path)
            target_group = document["target_group"]
            group_slug = safe_slug(target_group)

            target_group_dir = output_dir / group_slug
            target_group_dir.mkdir(parents=True, exist_ok=True)
            next_number = next_numbers.setdefault(
                group_slug,
                max(start_number, next_document_number(target_group_dir, target_group)),
            )
            old_doc_id = document["doc_id"]
            document_id = f"{group_slug}_{next_number:03d}"
            document["doc_id"] = document_id
            _rewrite_metadata_paths(
                document["metadata"],
                old_doc_id,
                document_id,
                group_slug,
                input_dir,
                output_dir,
            )
            target_path = target_group_dir / f"{document_id}.json"
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=target_group_dir,
                prefix=f".{document_id}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                temporary_path = Path(handle.name)
            temporary_path.replace(target_path)

            next_numbers[group_slug] = next_number + 1
            stats.promoted += 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            stats.errors += 1
            print(f"错误: {exc}")

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 cleaned Document 提升为正式文档")
    parser.add_argument("--input", type=Path, default=REPO_ROOT / "data" / "cleaned")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "data" / "documents")
    parser.add_argument("--target-group", help="只提升指定目标组织")
    parser.add_argument("--start-number", type=positive_start_number, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_dir = args.input / safe_slug(args.target_group) if args.target_group else args.input
    stats = promote_documents(input_dir, args.output, start_number=args.start_number)
    print(
        f"提升完成: promoted={stats.promoted}, skipped={stats.skipped}, errors={stats.errors}"
    )
    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
