import hashlib
import json
from pathlib import Path

import pytest

from scripts.promote_cleaned_documents import promote_documents
from scripts import filter_by_relevance


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


def test_promote_ignores_hidden_checkpoint_json(tmp_path: Path) -> None:
    source = tmp_path / "cleaned" / "apt28"
    target = tmp_path / "documents"
    source.mkdir(parents=True)
    (source / ".checkpoint_apt28.json").write_text("{}", encoding="utf-8")

    stats = promote_documents(tmp_path / "cleaned", target)

    assert stats.promoted == 0
    assert stats.errors == 0


def test_filter_renumber_rewrites_metadata_identity_and_paths(tmp_path: Path) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    output.mkdir(parents=True)
    payload = document("apt28_009", "https://example.test", "text")
    (output / "apt28_009.json").write_text(json.dumps(payload), encoding="utf-8")

    filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")

    result = json.loads((output / "apt28_001.json").read_text(encoding="utf-8"))
    assert result["doc_id"] == "apt28_001"
    assert result["metadata"]["doc_id"] == "apt28_001"
    assert result["metadata"]["document_id"] == "apt28_001"
    assert result["metadata"]["legacy_doc_id"] == "apt28_001"
    assert result["metadata"]["cleaned_path"].endswith("data/cleaned_filtered/apt28/apt28_001.json")
    assert result["metadata"]["document_path"].endswith("data/documents/apt28/apt28_001.json")


def test_filter_renumber_preserves_files_when_target_name_already_exists(tmp_path: Path) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    output.mkdir(parents=True)
    first = document("apt28_000", "https://example.test/first", "first")
    second = document("apt28_001", "https://example.test/second", "second")
    (output / "apt28_000.json").write_text(json.dumps(first), encoding="utf-8")
    (output / "apt28_001.json").write_text(json.dumps(second), encoding="utf-8")

    filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")

    result_001 = json.loads((output / "apt28_001.json").read_text(encoding="utf-8"))
    result_002 = json.loads((output / "apt28_002.json").read_text(encoding="utf-8"))
    assert result_001["source_url"] == "https://example.test/first"
    assert result_002["source_url"] == "https://example.test/second"


def test_filter_renumber_reports_when_restore_also_fails(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    output.mkdir(parents=True)
    payload = document("apt28_000", "https://example.test", "text")
    (output / "apt28_000.json").write_text(json.dumps(payload), encoding="utf-8")
    real_rename = Path.rename
    calls = 0

    def fail_swap_and_restore(self: Path, target: Path):
        nonlocal calls
        if self.parent == output.parent and self.name.startswith(".renumber_"):
            raise OSError("directory swap failed")
        if self.parent == output.parent and self.name.startswith(".apt28.renumber-backup-"):
            if target == output:
                raise OSError("restore failed")
            return real_rename(self, target)
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_swap_and_restore)

    with pytest.raises(RuntimeError, match="原目录保留在"):
        filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")

    assert not output.exists()
    assert any(tmp_path.joinpath("cleaned_filtered").glob(".apt28.renumber-backup-*"))

    with pytest.raises(RuntimeError, match="残留目录"):
        filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")


def test_filter_renumber_keeps_originals_when_directory_swap_fails(
    monkeypatch, tmp_path: Path
) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    output.mkdir(parents=True)
    original = document("apt28_000", "https://example.test/original", "original")
    (output / "apt28_000.json").write_text(json.dumps(original), encoding="utf-8")
    real_rename = Path.rename

    def fail_new_directory_rename(self: Path, target: Path):
        if self.parent == output.parent and self.name.startswith(".renumber_"):
            raise OSError("directory swap failed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", fail_new_directory_rename)

    try:
        filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")
    except OSError as exc:
        assert str(exc) == "directory swap failed"
    else:
        raise AssertionError("renumber_folder should propagate directory swap failure")

    result = json.loads((output / "apt28_000.json").read_text(encoding="utf-8"))
    assert result["source_url"] == "https://example.test/original"


def test_filter_renumber_preserves_non_json_files(tmp_path: Path) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    output.mkdir(parents=True)
    payload = document("apt28_000", "https://example.test", "text")
    (output / "apt28_000.json").write_text(json.dumps(payload), encoding="utf-8")
    (output / "README.txt").write_text("keep me", encoding="utf-8")

    filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")

    assert (output / "README.txt").read_text(encoding="utf-8") == "keep me"


def test_filter_renumber_preserves_nested_json_files(tmp_path: Path) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    nested = output / "archives"
    nested.mkdir(parents=True)
    payload = document("apt28_000", "https://example.test", "text")
    (output / "apt28_000.json").write_text(json.dumps(payload), encoding="utf-8")
    (nested / "archived.json").write_text('{"keep": true}', encoding="utf-8")

    filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")

    assert (nested / "archived.json").read_text(encoding="utf-8") == '{"keep": true}'


def test_filter_renumber_allows_retry_with_stale_backup(tmp_path: Path) -> None:
    output = tmp_path / "cleaned_filtered" / "apt28"
    output.mkdir(parents=True)
    stale_backup = output.parent / ".apt28.renumber-backup"
    stale_backup.mkdir()
    (stale_backup / "stale.txt").write_text("stale", encoding="utf-8")
    payload = document("apt28_000", "https://example.test", "text")
    (output / "apt28_000.json").write_text(json.dumps(payload), encoding="utf-8")

    filter_by_relevance.renumber_folder(tmp_path / "cleaned_filtered", "apt28")

    assert (output / "apt28_001.json").exists()
    assert stale_backup.exists()
