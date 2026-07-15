import hashlib

import pytest

from backend.app.services.document_adapter import DocumentContractError, adapt_document


def make_document(**overrides):
    document = {
        "doc_id": "apt28-report-1",
        "target_group": "APT28",
        "source_url": "https://example.com/report",
        "source_type": "vendor_report",
        "source_name": "Example Security",
        "title": "APT28 Report",
        "language": "en",
        "clean_text": "APT28 uses malware.",
        "published_at": None,
        "retrieved_at": "2026-07-15T00:00:00Z",
    }
    document.update(overrides)
    return document


def test_adapt_standard_document_keeps_clean_text_and_hash():
    adapted = adapt_document(make_document())

    assert adapted["clean_text"] == "APT28 uses malware."
    assert adapted["content_hash"] == "sha256:" + hashlib.sha256(
        adapted["clean_text"].encode("utf-8")
    ).hexdigest()


def test_adapt_legacy_text_fields_to_clean_text():
    for field in ("text", "raw_text", "content"):
        document = make_document(clean_text=None, **{field: "APT28 uses malware."})

        adapted = adapt_document(document)

        assert adapted["clean_text"] == "APT28 uses malware."
        assert field not in adapted
        assert adapted["content_hash"].startswith("sha256:")


def test_adapt_document_fills_safe_schema_defaults():
    adapted = adapt_document(make_document())

    assert adapted["schema_version"] == "1.0"
    assert adapted["target_groups"] == ["APT28"]
    assert adapted["tags"] == []
    assert adapted["metadata"] == {}
    assert adapted["tlp"] == "TLP:CLEAR"
    assert adapted["source_reliability"] == "unknown"


def test_adapt_document_preserves_existing_optional_values():
    adapted = adapt_document(
        make_document(
            target_groups=["APT28", "Lazarus"],
            tags=["apt", "report"],
            metadata={"collector": "manual"},
            tlp="TLP:GREEN",
            source_reliability="A",
            content_hash="sha256:stale",
        )
    )

    assert adapted["target_groups"] == ["APT28", "Lazarus"]
    assert adapted["tags"] == ["apt", "report"]
    assert adapted["metadata"] == {"collector": "manual"}
    assert adapted["tlp"] == "TLP:GREEN"
    assert adapted["source_reliability"] == "A"
    assert adapted["content_hash"] != "sha256:stale"


def test_adapt_document_rejects_missing_semantic_fields_with_clear_error():
    for field in ("doc_id", "target_group", "title", "language"):
        document = make_document()
        document.pop(field)

        with pytest.raises(DocumentContractError, match=field):
            adapt_document(document)


def test_adapt_document_rejects_missing_body_with_clear_error():
    document = make_document(clean_text=None, text=None, raw_text=None, content=None)

    with pytest.raises(DocumentContractError, match="clean_text|正文"):
        adapt_document(document)
