import hashlib
import json

from scripts.convert_raw_documents import (
    ConversionStats,
    build_documents,
    build_parser,
    convert_raw_record,
    light_clean_text,
)


def test_light_clean_text_removes_obvious_page_noise() -> None:
    raw_text = (
        "正文第一段。\n\n"
        "（图1：攻击流程图）\n\n"
        "正文第二段。\n\n\n"
        "*本文作者：测试作者，转载请注明来自FreeBuf.COM"
    )

    clean_text = light_clean_text(raw_text)

    assert clean_text == "正文第一段。\n\n正文第二段。"


def test_convert_raw_record_maps_legacy_fields_to_document_contract() -> None:
    raw_record = {
        "doc_id": "apt28_001",
        "target_group": "apt28",
        "source_url": "https://example.com/report",
        "source_type": "threat_report",
        "source_name": "Palo Alto Unit 42",
        "title": "Example Report",
        "language": "en",
        "raw_text": "Executive Summary\n\nAPT28 uses HeadLace.",
        "published_date": "2024-08-06",
        "crawl_time": "2026-07-07T16:43:23Z",
        "tags": ["APT28", "HeadLace"],
    }

    document = convert_raw_record(raw_record, raw_path="data/raw/crawler_output_apt28/apt28_001.json")

    assert document["doc_id"] == "apt28_001"
    assert document["schema_version"] == "1.0"
    assert document["target_group"] == "APT28"
    assert document["target_groups"] == ["APT28"]
    assert document["source_type"] == "vendor_report"
    assert document["source_reliability"] == "A"
    assert document["published_at"] == "2024-08-06"
    assert document["retrieved_at"] == "2026-07-07T16:43:23Z"
    assert document["clean_text"] == "Executive Summary\n\nAPT28 uses HeadLace."
    assert document["content_hash"] == "sha256:" + hashlib.sha256(
        document["clean_text"].encode("utf-8")
    ).hexdigest()
    assert document["tlp"] == "TLP:CLEAR"
    assert document["metadata"]["legacy_doc_id"] == "apt28_001"
    assert document["metadata"]["raw_path"] == "data/raw/crawler_output_apt28/apt28_001.json"


def test_build_documents_merges_duplicate_url_target_groups() -> None:
    records = [
        (
            {
                "doc_id": "kimsuky_001",
                "target_group": "kimsuky",
                "source_url": "https://example.com/shared",
                "source_type": "news_article",
                "source_name": "FreeBuf",
                "title": "Shared Article",
                "language": "zh",
                "raw_text": "Kimsuky 和 Lazarus 相关活动。",
                "published_date": "2025-01-02",
                "crawl_time": "2026-07-07T00:00:00Z",
                "tags": ["APT"],
            },
            "data/raw/crawler_output_kimsuky/kimsuky_001.json",
        ),
        (
            {
                "doc_id": "lazarus_001",
                "target_group": "lazarus",
                "source_url": "https://example.com/shared",
                "source_type": "news_article",
                "source_name": "FreeBuf",
                "title": "Shared Article",
                "language": "zh",
                "raw_text": "Kimsuky 和 Lazarus 相关活动。",
                "published_date": "2025-01-02",
                "crawl_time": "2026-07-07T00:00:00Z",
                "tags": ["APT"],
            },
            "data/raw/crawler_output_lazarus/lazarus_001.json",
        ),
    ]

    documents, stats = build_documents(records)

    assert isinstance(stats, ConversionStats)
    assert stats.input_records == 2
    assert stats.output_documents == 1
    assert stats.merged_duplicates == 1
    assert documents[0]["doc_id"] == "kimsuky_001"
    assert documents[0]["target_group"] == "Kimsuky"
    assert documents[0]["target_groups"] == ["Kimsuky", "Lazarus"]
    assert documents[0]["metadata"]["merged_legacy_doc_ids"] == ["kimsuky_001", "lazarus_001"]
    assert documents[0]["metadata"]["merged_raw_paths"] == [
        "data/raw/crawler_output_kimsuky/kimsuky_001.json",
        "data/raw/crawler_output_lazarus/lazarus_001.json",
    ]


def test_cli_defaults_skip_low_value_short_documents() -> None:
    args = build_parser().parse_args([])

    assert args.min_clean_chars == 500
