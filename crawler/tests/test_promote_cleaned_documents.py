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
        "metadata": {},
    }


def test_promote_assigns_next_id_and_deduplicates(tmp_path: Path) -> None:
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

    stats = promote_documents(tmp_path / "cleaned", tmp_path / "documents")

    assert stats.promoted == 1
    assert stats.skipped == 1
    promoted = json.loads((target / "apt28_008.json").read_text(encoding="utf-8"))
    assert promoted["doc_id"] == "apt28_008"
