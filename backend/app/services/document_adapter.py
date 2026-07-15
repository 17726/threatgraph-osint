from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.app.core.document_contract import document_content_hash, require_valid_document


class DocumentContractError(ValueError):
    """标准文档无法满足 document.schema.json 契约。"""


def adapt_document(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise DocumentContractError("文档必须是 JSON 对象")
    adapted = deepcopy(document)

    text = adapted.get("clean_text")
    if not isinstance(text, str) or not text.strip():
        for field in ("text", "raw_text", "content"):
            candidate = adapted.get(field)
            if isinstance(candidate, str) and candidate.strip():
                text = candidate
                break
    if not isinstance(text, str) or not text.strip():
        raise DocumentContractError("文档缺少必要正文语义字段: clean_text、text、raw_text 或 content")
    adapted["clean_text"] = text

    required_semantic_fields = ("doc_id", "target_group", "title", "language")
    missing_fields = [
        field
        for field in required_semantic_fields
        if not isinstance(adapted.get(field), str) or not adapted[field].strip()
    ]
    if missing_fields:
        raise DocumentContractError(
            "文档缺少必要语义字段: " + ", ".join(missing_fields)
        )

    adapted.pop("text", None)
    adapted.pop("raw_text", None)
    adapted.pop("content", None)
    adapted.setdefault("schema_version", "1.0")
    adapted.setdefault("target_groups", [adapted["target_group"]])
    adapted["content_hash"] = document_content_hash(text)
    adapted.setdefault("tags", [])
    adapted.setdefault("metadata", {})
    adapted.setdefault("tlp", "TLP:CLEAR")
    adapted.setdefault("source_reliability", "unknown")

    try:
        require_valid_document(adapted)
    except ValueError as error:
        raise DocumentContractError(str(error)) from error
    return adapted
