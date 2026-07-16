import os

import pytest

from scripts import filter_by_relevance


def test_call_api_requires_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        filter_by_relevance.call_api("system", "user")


def test_filter_parser_accepts_folder() -> None:
    parser = filter_by_relevance.build_parser()
    args = parser.parse_args(["--folder", "apt28"])

    assert args.folder == "apt28"
