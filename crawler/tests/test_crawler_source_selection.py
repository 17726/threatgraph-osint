from scripts import crawler_supplementary, crawler_supplementary_v2, crawler_v1
from pathlib import Path
import asyncio


def test_crawler_v1_writes_cleaned_documents() -> None:
    assert crawler_v1.output_dir_for("APT28").as_posix().endswith("data/cleaned/apt28")


def test_source_selection_accepts_comma_separated_values() -> None:
    assert crawler_v1.sources_from_mask(0b1001) == ["qianxin", "freebuf"]
    assert crawler_supplementary.sources_from_mask(0b1010) == ["trmlabs", "securelist"]
    assert crawler_supplementary_v2.sources_from_mask(0b0110) == ["groupib", "ofac"]


def test_local_source_mask_selects_sources_by_lowest_bit() -> None:
    assert crawler_v1.sources_from_mask(0b0101) == ["qianxin", "unit42"]
    assert crawler_supplementary.sources_from_mask(0b1010) == ["trmlabs", "securelist"]
    assert crawler_supplementary_v2.sources_from_mask(0b0101) == ["crowdstrike", "ofac"]


def test_source_selection_rejects_invalid_masks() -> None:
    try:
        crawler_v1.sources_from_mask(0)
    except ValueError as exc:
        assert "greater than zero" in str(exc)
    else:
        raise AssertionError("unknown source should fail")


def test_crawler_requirements_include_http_crawler_dependencies() -> None:
    requirements = Path("crawler/requirements.txt").read_text(encoding="utf-8")

    assert "beautifulsoup4" in requirements
    assert "lxml" in requirements
    assert "requests" in requirements


def test_crawler_v1_returns_failure_when_selected_crawler_fails(monkeypatch) -> None:
    class FailingCrawler:
        @classmethod
        def run(cls, keyword, limit):
            raise RuntimeError("crawler failed")

    monkeypatch.setattr(crawler_v1, "QianxinCrawler", FailingCrawler)
    monkeypatch.setattr(
        "sys.argv",
        ["crawler_v1.py", "--keyword", "APT28", "--sources", "1"],
    )

    assert asyncio.run(crawler_v1.main()) == 1
