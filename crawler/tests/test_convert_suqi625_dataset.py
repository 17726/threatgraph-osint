import hashlib
import subprocess
import sys

from scripts.convert_suqi625_dataset import (
    Suqi625ConversionStats,
    build_new_documents,
    convert_cleaned_record,
)


def test_convert_cleaned_record_prefixes_doc_id_and_preserves_legacy_hash() -> None:
    record = {
        "doc_id": "apt28_093",
        "target_group": "apt28",
        "source_url": "https://www.reddit.com/r/example/comments/1/test",
        "source_type": "social_forum",
        "source_name": "Reddit",
        "title": "APT28 discussion",
        "language": "en",
        "raw_text": "APT28 discussion with enough context for evaluation.",
        "published_date": "2026-07-03",
        "crawl_time": "2026-07-09T05:00:00Z",
        "tags": ["reddit", "apt28"],
        "content_hash": "0123456789abcdef0123456789abcdef",
    }

    document = convert_cleaned_record(record, "tmp/cleaned/crawler_output_apt28/apt28_093.json")

    assert document["doc_id"] == "suqi625_apt28_093"
    assert document["target_group"] == "APT28"
    assert document["target_groups"] == ["APT28"]
    assert document["source_type"] == "social_forum"
    assert document["source_reliability"] == "D"
    assert document["content_hash"] == "sha256:" + hashlib.sha256(
        document["clean_text"].encode("utf-8")
    ).hexdigest()
    assert document["metadata"]["collector_github"] == "SuQi625"
    assert document["metadata"]["legacy_doc_id"] == "apt28_093"
    assert document["metadata"]["legacy_content_hash"] == "0123456789abcdef0123456789abcdef"
    assert document["metadata"]["legacy_content_hash_algorithm"] == "md5"


def test_build_new_documents_skips_existing_short_and_merges_duplicate_urls() -> None:
    records = [
        (
            {
                "doc_id": "apt28_001",
                "target_group": "apt28",
                "source_url": "https://example.com/existing",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "Existing",
                "language": "en",
                "raw_text": "Existing document text with enough length.",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": [],
                "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            },
            "tmp/cleaned/crawler_output_apt28/apt28_001.json",
        ),
        (
            {
                "doc_id": "apt28_002",
                "target_group": "apt28",
                "source_url": "https://example.com/short",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "Short",
                "language": "en",
                "raw_text": "too short",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": [],
                "content_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            },
            "tmp/cleaned/crawler_output_apt28/apt28_002.json",
        ),
        (
            {
                "doc_id": "apt28_003",
                "target_group": "apt28",
                "source_url": "https://example.com/shared",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "Shared",
                "language": "en",
                "raw_text": "APT28 and Kimsuky are both discussed in this longer Reddit thread.",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": ["APT28"],
                "content_hash": "cccccccccccccccccccccccccccccccc",
            },
            "tmp/cleaned/crawler_output_apt28/apt28_003.json",
        ),
        (
            {
                "doc_id": "kimsuky_001",
                "target_group": "kimsuky",
                "source_url": "https://example.com/shared",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "Shared",
                "language": "en",
                "raw_text": "APT28 and Kimsuky are both discussed in this longer Reddit thread.",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": ["Kimsuky"],
                "content_hash": "dddddddddddddddddddddddddddddddd",
            },
            "tmp/cleaned/crawler_output_kimsuky/kimsuky_001.json",
        ),
    ]

    documents, stats = build_new_documents(
        records,
        existing_source_urls={"https://example.com/existing"},
        min_clean_chars=20,
    )

    assert isinstance(stats, Suqi625ConversionStats)
    assert stats.input_records == 4
    assert stats.skipped_existing_url == 1
    assert stats.skipped_too_short == 1
    assert stats.merged_duplicates == 1
    assert stats.output_documents == 1
    assert documents[0]["doc_id"] == "suqi625_apt28_003"
    assert documents[0]["target_groups"] == ["APT28", "Kimsuky"]
    assert documents[0]["metadata"]["merged_legacy_doc_ids"] == ["apt28_003", "kimsuky_001"]


def test_build_new_documents_skips_duplicate_content_and_low_relevance_social_posts() -> None:
    records = [
        (
            {
                "doc_id": "lazarus_001",
                "target_group": "lazarus",
                "source_url": "https://example.com/reddit/lazarus-apt",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "Lazarus APT campaign",
                "language": "en",
                "raw_text": "Lazarus APT campaign discusses malware, credential theft, and cyber defense.",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": ["lazarus"],
                "content_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            },
            "tmp/cleaned/crawler_output_lazarus/lazarus_001.json",
        ),
        (
            {
                "doc_id": "lazarus_002",
                "target_group": "lazarus",
                "source_url": "https://example.com/reddit/lazarus-apt-copy",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "Lazarus APT campaign copy",
                "language": "en",
                "raw_text": "Lazarus APT campaign discusses malware, credential theft, and cyber defense.",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": ["lazarus"],
                "content_hash": "ffffffffffffffffffffffffffffffff",
            },
            "tmp/cleaned/crawler_output_lazarus/lazarus_002.json",
        ),
        (
            {
                "doc_id": "lazarus_003",
                "target_group": "lazarus",
                "source_url": "https://example.com/reddit/lazarus-project",
                "source_type": "social_forum",
                "source_name": "Reddit",
                "title": "A character is brought back by the Lazarus Project",
                "language": "en",
                "raw_text": "This post discusses a fictional resurrection trope and has no relevant technical context.",
                "published_date": "2026-07-01",
                "crawl_time": "2026-07-09T05:00:00Z",
                "tags": ["lazarus"],
                "content_hash": "11111111111111111111111111111111",
            },
            "tmp/cleaned/crawler_output_lazarus/lazarus_003.json",
        ),
    ]

    documents, stats = build_new_documents(records, existing_source_urls=set(), min_clean_chars=20)

    assert stats.output_documents == 1
    assert stats.skipped_duplicate_content == 1
    assert stats.skipped_low_relevance == 1
    assert documents[0]["doc_id"] == "suqi625_lazarus_001"


def test_converter_script_can_run_by_file_path() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/convert_suqi625_dataset.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "SuQi625" in result.stdout
