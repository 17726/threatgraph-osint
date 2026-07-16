import pytest

from scripts import filter_by_relevance


@pytest.mark.parametrize("missing", ["LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"])
def test_llm_config_requires_all_environment_values(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(RuntimeError, match=missing):
        filter_by_relevance.require_llm_config()


def test_llm_config_does_not_read_deepseek_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1/chat/completions")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "legacy-key")

    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        filter_by_relevance.require_llm_config()


def test_call_api_uses_runtime_llm_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "runtime-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY", "runtime-key")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = request.data
        captured["timeout"] = timeout
        return _FakeResponse(
            b'{"choices":[{"message":{"content":"{\\"is_relevant\\":true,\\"cleaned_text\\":\\"text\\"}"}}]}'
        )

    monkeypatch.setattr(filter_by_relevance.urllib.request, "urlopen", fake_urlopen)

    result = filter_by_relevance.call_api("system", "user")

    assert result == {"is_relevant": True, "cleaned_text": "text"}
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["authorization"] == "Bearer runtime-key"
    assert b'"model": "runtime-model"' in captured["payload"]


def test_provider_root_url_is_normalized_to_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "runtime-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "runtime-key")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return _FakeResponse(
            b'{"choices":[{"message":{"content":"{\\"is_relevant\\":true,\\"cleaned_text\\":\\"text\\"}"}}]}'
        )

    monkeypatch.setattr(filter_by_relevance.urllib.request, "urlopen", fake_urlopen)

    filter_by_relevance.call_api("system", "user")

    assert captured["url"] == "https://api.deepseek.com/chat/completions"


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self.body


def test_filter_parser_accepts_folder() -> None:
    parser = filter_by_relevance.build_parser()
    args = parser.parse_args(["--folder", "apt28"])

    assert args.folder == "apt28"


def test_filter_main_returns_nonzero_when_processing_errors(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["filter_by_relevance.py"])
    monkeypatch.setattr(filter_by_relevance, "require_llm_config", lambda: ("model", "url", "key"))
    monkeypatch.setattr(filter_by_relevance.Path, "is_dir", lambda self: True)
    monkeypatch.setattr(filter_by_relevance, "process_folder", lambda *args, **kwargs: {
        "total": 1,
        "kept": 0,
        "discarded": 0,
        "errors": 1,
    })
    assert filter_by_relevance.main() == 1
