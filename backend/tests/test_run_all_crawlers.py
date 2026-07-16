import pytest

from scripts import run_all_crawlers


def test_group_source_masks_skips_unselected_crawlers() -> None:
    grouped = run_all_crawlers.group_source_masks(1025)

    assert grouped == {
        "crawler_v1": 1,
        "crawler_supplementary_v2": 4,
    }


def test_group_source_masks_all_selects_every_source() -> None:
    grouped = run_all_crawlers.group_source_masks(run_all_crawlers.MAX_SOURCE_MASK)

    assert set(grouped) == {
        "crawler_v1",
        "crawler_supplementary",
        "crawler_supplementary_v2",
    }
    assert grouped["crawler_v1"] == 15


def test_group_source_masks_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        run_all_crawlers.group_source_masks(1 << 12)


def test_build_commands_uses_filtered_input_only_when_enabled() -> None:
    parser = run_all_crawlers.build_parser()
    plain_args = parser.parse_args(
        ["--keyword", "APT28", "--limit", "2", "--sources", "1024"]
    )
    filtered_args = parser.parse_args(
        ["--keyword", "APT28", "--limit", "2", "--sources", "1024", "--filter"]
    )

    plain_commands = run_all_crawlers.build_commands(plain_args)
    filtered_commands = run_all_crawlers.build_commands(filtered_args)

    plain_input = plain_commands[-1][plain_commands[-1].index("--input") + 1]
    filtered_input = filtered_commands[-1][filtered_commands[-1].index("--input") + 1]
    assert plain_input.endswith("data\\cleaned") or plain_input.endswith("data/cleaned")
    assert filtered_input.endswith("data\\cleaned_filtered") or filtered_input.endswith(
        "data/cleaned_filtered"
    )


def test_global_source_integer_is_split_into_local_masks() -> None:
    grouped = run_all_crawlers.group_source_masks(1033)

    assert grouped == {
        "crawler_v1": 9,
        "crawler_supplementary_v2": 4,
    }


def test_global_source_integer_must_be_positive_and_in_range() -> None:
    with pytest.raises(ValueError):
        run_all_crawlers.parse_sources_mask("0")
    with pytest.raises(ValueError):
        run_all_crawlers.parse_sources_mask(str(1 << 12))
