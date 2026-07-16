from backend.app.core.llm_config import (
    get_llm_config_status,
    has_valid_llm_config,
    missing_llm_config,
)


def test_all_llm_values_non_empty_are_configured() -> None:
    environ = {
        "LLM_MODEL": "model",
        "LLM_BASE_URL": "https://example.test/v1/chat/completions",
        "LLM_API_KEY": "secret",
    }

    assert has_valid_llm_config(environ) is True
    assert get_llm_config_status(environ) == "configured"
    assert missing_llm_config(environ) == []


def test_blank_llm_values_are_reported_in_stable_order() -> None:
    environ = {"LLM_MODEL": " ", "LLM_BASE_URL": "", "LLM_API_KEY": "key"}

    assert has_valid_llm_config(environ) is False
    assert get_llm_config_status(environ) == "not_configured"
    assert missing_llm_config(environ) == ["LLM_MODEL", "LLM_BASE_URL"]
