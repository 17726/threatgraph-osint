from __future__ import annotations

import os
from collections.abc import Mapping


REQUIRED_LLM_VARS = ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY")


def missing_llm_config(environ: Mapping[str, str] | None = None) -> list[str]:
    values = environ if environ is not None else os.environ
    return [name for name in REQUIRED_LLM_VARS if not str(values.get(name, "")).strip()]


def has_valid_llm_config(environ: Mapping[str, str] | None = None) -> bool:
    return not missing_llm_config(environ)


def get_llm_config_status(environ: Mapping[str, str] | None = None) -> str:
    return "configured" if has_valid_llm_config(environ) else "not_configured"
