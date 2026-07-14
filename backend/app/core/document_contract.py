import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOCUMENT_SCHEMA_PATH = REPO_ROOT / "docs/schemas/document.schema.json"


def document_content_hash(clean_text: str) -> str:
    return "sha256:" + hashlib.sha256(clean_text.encode("utf-8")).hexdigest()


def document_contract_errors(
    document: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_DOCUMENT_SCHEMA_PATH,
) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = [
        f"document schema {'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]

    clean_text = document.get("clean_text")
    content_hash = document.get("content_hash")
    if isinstance(clean_text, str) and clean_text:
        expected_hash = document_content_hash(clean_text)
        if content_hash != expected_hash:
            errors.append(
                "document.content_hash 与 clean_text 不一致: "
                f"expected={expected_hash}, actual={content_hash!r}"
            )
    return errors


def require_valid_document(document: dict[str, Any]) -> str:
    errors = document_contract_errors(document)
    if errors:
        raise ValueError("Document 契约校验失败: " + "; ".join(errors))
    return document["clean_text"]
