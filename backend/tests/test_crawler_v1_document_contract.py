import hashlib

from scripts import crawler_v1


def test_crawler_v1_defaults_to_document_output_dir() -> None:
    output_dir = crawler_v1.output_dir_for("APT28")

    assert output_dir.as_posix().endswith("data/documents/apt28")


def test_crawler_v1_builds_document_contract_record() -> None:
    document = crawler_v1.build_contract_record(
        doc_id="apt28_999",
        target_group="APT28",
        source_url="https://example.com/report",
        source_type="threat_report",
        source_name="Palo Alto Unit 42",
        title="Example Report",
        language="en",
        raw_text="Figure 1. Noise\n\nAPT28 uses HeadLace.",
        published_date="2024-08-06",
        crawl_time="2026-07-07T16:43:23Z",
        tags=["APT28", "HeadLace"],
    )

    assert list(document.keys()) == crawler_v1.DOCUMENT_KEYS
    assert "raw_text" not in document
    assert document["doc_id"] == "apt28_999"
    assert document["schema_version"] == "1.0"
    assert document["target_group"] == "APT28"
    assert document["target_groups"] == ["APT28"]
    assert document["source_type"] == "vendor_report"
    assert document["source_reliability"] == "A"
    assert document["clean_text"] == "APT28 uses HeadLace."
    assert document["content_hash"] == "sha256:" + hashlib.sha256(
        document["clean_text"].encode("utf-8")
    ).hexdigest()
    assert document["published_at"] == "2024-08-06"
    assert document["retrieved_at"] == "2026-07-07T16:43:23Z"
    assert document["tlp"] == "TLP:CLEAR"
    assert document["metadata"]["crawler"] == "scripts/crawler_v1.py"
