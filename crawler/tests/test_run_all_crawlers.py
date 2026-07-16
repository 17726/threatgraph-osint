import json
from pathlib import Path

import pytest

from scripts import run_all_crawlers


def _write_cleaned_document(path: Path, source_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"doc_id": "apt28_001", "source_name": source_name}),
        encoding="utf-8",
    )


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


def test_all_sources_mask_dispatches_all_twelve_sources() -> None:
    grouped = run_all_crawlers.group_source_masks(4095)

    assert grouped == {
        "crawler_v1": 15,
        "crawler_supplementary": 15,
        "crawler_supplementary_v2": 15,
    }


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


def test_build_commands_passes_start_number_to_promote() -> None:
    parser = run_all_crawlers.build_parser()
    args = parser.parse_args(
        ["--keyword", "APT28", "--limit", "2", "--sources", "1", "--start-number", "108"]
    )

    promote_command = run_all_crawlers.build_commands(args)[-1]

    assert promote_command[-2:] == ["--start-number", "108"]


def test_start_number_defaults_to_one() -> None:
    parser = run_all_crawlers.build_parser()
    args = parser.parse_args(["--keyword", "APT28", "--limit", "2", "--sources", "1"])

    assert args.start_number == 1


def test_filter_failure_stops_before_promote(monkeypatch) -> None:
    commands = run_all_crawlers.build_commands(
        run_all_crawlers.build_parser().parse_args(
            ["--keyword", "APT28", "--limit", "1", "--sources", "1", "--filter"]
        )
    )
    executed: list[list[str]] = []

    def fake_run(command, check, cwd):
        executed.append(command)
        return type("Result", (), {"returncode": 1 if "filter_by_relevance.py" in command[1] else 0})()

    monkeypatch.setattr(run_all_crawlers.subprocess, "run", fake_run)

    assert run_all_crawlers.main.__name__ == "main"
    failed = False
    for command in commands:
        result = run_all_crawlers.subprocess.run(command, check=False, cwd=run_all_crawlers.PROJECT_ROOT)
        if result.returncode:
            failed = True
            break

    assert failed is True
    assert not any("promote_cleaned_documents.py" in command[1] for command in executed)


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


def test_merge_cleaned_documents_keeps_same_legacy_filename_from_each_crawler(
    tmp_path: Path,
) -> None:
    _write_cleaned_document(
        tmp_path / "crawler_v1" / "cleaned" / "apt28" / "apt28_001.json",
        "Qianxin",
    )
    _write_cleaned_document(
        tmp_path / "crawler_supplementary" / "cleaned" / "apt28" / "apt28_001.json",
        "SecureList",
    )

    count = run_all_crawlers.merge_cleaned_documents(tmp_path, tmp_path / "merged")

    assert count == 2
    merged = list((tmp_path / "merged" / "apt28").glob("*.json"))
    assert len(merged) == 2
    assert {json.loads(path.read_text(encoding="utf-8"))["source_name"] for path in merged} == {
        "Qianxin",
        "SecureList",
    }
