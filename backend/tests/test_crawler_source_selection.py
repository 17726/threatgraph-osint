from scripts import crawler_supplementary, crawler_supplementary_v2, crawler_v1
from pathlib import Path
import asyncio


def test_crawler_v1_writes_cleaned_documents() -> None:
    assert crawler_v1.output_dir_for("APT28").as_posix().endswith("data/cleaned/apt28")


def test_source_selection_accepts_comma_separated_values() -> None:
    assert crawler_v1.parse_sources("qianxin,freebuf") == ["qianxin", "freebuf"]
    assert crawler_supplementary.parse_sources("microsoft,securelist") == [
        "microsoft",
        "securelist",
    ]
    assert crawler_supplementary_v2.parse_sources("ofac,groupib") == ["ofac", "groupib"]


def test_source_selection_rejects_unknown_values() -> None:
    try:
        crawler_v1.parse_sources("missing")
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown source should fail")


def test_backend_requirements_include_http_crawler_dependencies() -> None:
    requirements = Path("backend/requirements.txt").read_text(encoding="utf-8")

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
        ["crawler_v1.py", "--keyword", "APT28", "--source", "qianxin"],
    )

    assert asyncio.run(crawler_v1.main()) == 1
