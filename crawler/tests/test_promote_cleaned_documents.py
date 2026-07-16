import hashlib
import json
from pathlib import Path

from scripts.promote_cleaned_documents import promote_documents


def document(doc_id: str, url: str, text: str) -> dict:
    return {
        "doc_id": doc_id,
        "schema_version": "1.0",
        "target_group": "APT28",
        "target_groups": ["APT28"],
        "source_url": url,
        "source_type": "news",
        "source_name": "Example",
        "title": "Example",
        "language": "en",
        "clean_text": text,
        "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "published_at": None,
        "retrieved_at": "2026-07-16T00:00:00Z",
        "source_reliability": "B",
        "tlp": "TLP:CLEAR",
        "tags": ["news"],
        "crawl_run_id": "crawl_test_001",
        "metadata": {
            "doc_id": doc_id,
            "document_id": doc_id,
            "legacy_doc_id": doc_id,
            "source_path": f"data/cleaned/apt28/{doc_id}.json",
            "cleaned_path": f"data/cleaned/apt28/{doc_id}.json",
            "document_path": f"data/documents/apt28/{doc_id}.json",
            "note": f"来自 {doc_id} 的采集",
        },
    }


def test_promote_assigns_explicit_ids_and_rewrites_metadata(tmp_path: Path) -> None:
    source = tmp_path / "cleaned" / "apt28"
    target = tmp_path / "documents" / "apt28"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    (target / "apt28_007.json").write_text(
        json.dumps(document("old", "https://old", "old")), encoding="utf-8"
    )
    (source / "temporary.json").write_text(
        json.dumps(document("tmp", "https://new", "new")), encoding="utf-8"
    )
    (source / "duplicate.json").write_text(
        json.dumps(document("tmp2", "https://old", "old")), encoding="utf-8"
    )

    stats = promote_documents(tmp_path / "cleaned", tmp_path / "documents", start_number=108)

    assert stats.promoted == 2
    assert stats.skipped == 0
    promoted = json.loads((target / "apt28_108.json").read_text(encoding="utf-8"))
    assert promoted["doc_id"] == "apt28_108"
    assert promoted["crawl_run_id"] == "crawl_test_001"
    assert promoted["metadata"]["doc_id"] == "apt28_108"
    assert promoted["metadata"]["document_id"] == "apt28_108"
    assert promoted["metadata"]["legacy_doc_id"] == "apt28_108"
    assert promoted["metadata"]["source_path"].endswith("data/documents/apt28/apt28_108.json")
    assert promoted["metadata"]["cleaned_path"].endswith("data/cleaned/apt28/apt28_108.json")
    assert promoted["metadata"]["document_path"].endswith("data/documents/apt28/apt28_108.json")
    assert promoted["metadata"]["note"] == "来自 tmp2 的采集"
    assert (target / "apt28_109.json").exists()
