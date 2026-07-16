import pytest

from scripts import run_all_crawlers


def test_group_sources_skips_unselected_crawlers() -> None:
    grouped = run_all_crawlers.group_sources("qianxin,ofac")

    assert grouped == {
        "crawler_v1": ["qianxin"],
        "crawler_supplementary_v2": ["ofac"],
    }


def test_group_sources_all_selects_every_source() -> None:
    grouped = run_all_crawlers.group_sources("all")

    assert set(grouped) == {
        "crawler_v1",
        "crawler_supplementary",
        "crawler_supplementary_v2",
    }
    assert grouped["crawler_v1"] == list(run_all_crawlers.CRAWLER_SOURCES["crawler_v1"])


def test_group_sources_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="missing"):
        run_all_crawlers.group_sources("missing")


def test_build_commands_uses_filtered_input_only_when_enabled() -> None:
    parser = run_all_crawlers.build_parser()
    plain_args = parser.parse_args(
        ["--keyword", "APT28", "--limit", "2", "--sources", "ofac"]
    )
    filtered_args = parser.parse_args(
        ["--keyword", "APT28", "--limit", "2", "--sources", "ofac", "--filter"]
    )

    plain_commands = run_all_crawlers.build_commands(plain_args)
    filtered_commands = run_all_crawlers.build_commands(filtered_args)

    plain_input = plain_commands[-1][plain_commands[-1].index("--input") + 1]
    filtered_input = filtered_commands[-1][filtered_commands[-1].index("--input") + 1]
    assert plain_input.endswith("data\\cleaned") or plain_input.endswith("data/cleaned")
    assert filtered_input.endswith("data\\cleaned_filtered") or filtered_input.endswith(
        "data/cleaned_filtered"
    )
