import json
from pathlib import Path

import httpx
import pytest

from backend.app.services.llm_service import (
    ENTITY_TYPES,
    RELATION_TYPES,
    LLMExtractionService,
    load_system_prompt,
    parse_llm_response,
)


ROOT = Path(__file__).resolve().parents[2]


def api_response(content: dict, model: str = "test-model") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [
                {"message": {"content": json.dumps(content)}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def test_llm_service_uses_schema_enums_and_repository_prompt():
    schema = json.loads(
        (ROOT / "docs/schemas/extraction-result.schema.json").read_text(encoding="utf-8")
    )

    assert ENTITY_TYPES == tuple(schema["$defs"]["entity_type"]["enum"])
    assert RELATION_TYPES == tuple(schema["$defs"]["relation_type"]["enum"])
    system_prompt = load_system_prompt()
    assert "不要生成 entity_id" in system_prompt
    assert "USES:" in system_prompt
    assert "APT_GROUP" in system_prompt and "MALWARE" in system_prompt


def test_parse_llm_response_accepts_code_fence_and_computes_spans():
    clean_text = "APT28 used X-Agent malware."
    payload = {
        "entities": [
            {
                "name": "APT28",
                "type": "APT_GROUP",
                "aliases": ["Fancy Bear"],
                "description": "Threat group",
                "mention_text": "APT28",
                "evidence_text": clean_text,
                "confidence": 0.95,
            },
            {
                "name": "X-Agent",
                "type": "MALWARE",
                "aliases": [],
                "description": "Malware",
                "mention_text": "X-Agent",
                "evidence_text": "X-Agent malware",
                "confidence": 0.92,
            },
        ],
        "relations": [
            {
                "head_name": "Fancy Bear",
                "head_type": "APT_GROUP",
                "relation_type": "USES",
                "tail_name": "X-Agent",
                "tail_type": "MALWARE",
                "evidence_text": clean_text,
                "confidence": 0.9,
            }
        ],
    }

    result = parse_llm_response(f"```json\n{json.dumps(payload)}\n```", "doc_c001", clean_text)

    assert result["entities"][0]["char_start"] == 0
    assert result["entities"][0]["char_end"] == len(clean_text)
    assert result["relations"][0]["validation_status"] == "valid"


def test_parse_llm_response_rejects_candidates_without_grounded_evidence():
    payload = {
        "entities": [
            {
                "name": "APT28",
                "type": "APT_GROUP",
                "aliases": [],
                "evidence_text": "APT28",
                "confidence": 0.9,
            },
            {
                "name": "Invented malware",
                "type": "MALWARE",
                "aliases": [],
                "evidence_text": "",
                "confidence": 0.9,
            },
        ],
        "relations": [
            {
                "head_name": "APT28",
                "head_type": "APT_GROUP",
                "relation_type": "USES",
                "tail_name": "Invented malware",
                "tail_type": "MALWARE",
                "evidence_text": "",
                "confidence": 0.9,
            }
        ],
    }

    result = parse_llm_response(json.dumps(payload), "doc_c001", "APT28")

    assert [entity["name"] for entity in result["entities"]] == ["APT28"]
    assert result["relations"] == []


def test_parse_llm_response_merges_alias_entities_and_deduplicates_relations():
    clean_text = "Sofacy, also known as STRONTIUM, used X-Agent."
    payload = {
        "entities": [
            {
                "name": "Sofacy",
                "type": "APT_GROUP",
                "aliases": ["STRONTIUM"],
                "evidence_text": clean_text,
                "confidence": 0.9,
            },
            {
                "name": "STRONTIUM",
                "type": "APT_GROUP",
                "aliases": [],
                "evidence_text": clean_text,
                "confidence": 0.8,
            },
            {
                "name": "X-Agent",
                "type": "MALWARE",
                "aliases": [],
                "evidence_text": clean_text,
                "confidence": 0.9,
            },
        ],
        "relations": [
            {
                "head_name": "Sofacy",
                "head_type": "APT_GROUP",
                "relation_type": "USES",
                "tail_name": "X-Agent",
                "tail_type": "MALWARE",
                "evidence_text": clean_text,
                "confidence": 0.9,
            },
            {
                "head_name": "STRONTIUM",
                "head_type": "APT_GROUP",
                "relation_type": "USES",
                "tail_name": "X-Agent",
                "tail_type": "MALWARE",
                "evidence_text": clean_text,
                "confidence": 0.8,
            },
            {
                "head_name": "Sofacy",
                "head_type": "APT_GROUP",
                "relation_type": "AFFILIATED_WITH",
                "tail_name": "STRONTIUM",
                "tail_type": "APT_GROUP",
                "evidence_text": clean_text,
                "confidence": 0.8,
            },
        ],
    }

    result = parse_llm_response(json.dumps(payload), "doc_c001", clean_text)

    assert [entity["name"] for entity in result["entities"]] == ["Sofacy", "X-Agent"]
    assert len(result["relations"]) == 1
    assert result["relations"][0]["head_name"] == "Sofacy"


def test_preflight_makes_real_shape_request_without_exposing_key():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == httpx.URL("https://example.test/v1/chat/completions")
        assert request.headers["authorization"] == "Bearer test-secret"
        assert body["model"] == "test-model"
        assert body["response_format"] == {"type": "json_object"}
        return api_response({"ok": True})

    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=1,
        relation_review_passes=0,
        transport=httpx.MockTransport(handler),
    )

    result = service.preflight()

    assert result["ok"] is True
    assert result["response_model"] == "test-model"
    assert result["usage"]["total_tokens"] == 15


def test_extract_returns_contract_valid_candidate_result():
    clean_text = "APT28 used X-Agent malware."

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "extract-v1" in body["messages"][0]["content"] or "ThreatGraph" in body["messages"][0]["content"]
        return api_response(
            {
                "entities": [
                    {
                        "name": "APT28",
                        "type": "APT_GROUP",
                        "aliases": [],
                        "description": "Threat group",
                        "mention_text": "APT28",
                        "evidence_text": clean_text,
                        "confidence": 0.95,
                    },
                    {
                        "name": "X-Agent",
                        "type": "MALWARE",
                        "aliases": [],
                        "description": "Malware",
                        "mention_text": "X-Agent",
                        "evidence_text": clean_text,
                        "confidence": 0.9,
                    },
                ],
                "relations": [
                    {
                        "head_name": "APT28",
                        "head_type": "APT_GROUP",
                        "relation_type": "USES",
                        "tail_name": "X-Agent",
                        "tail_type": "MALWARE",
                        "evidence_text": clean_text,
                        "confidence": 0.9,
                    }
                ],
            }
        )

    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=1,
        relation_review_passes=0,
        transport=httpx.MockTransport(handler),
    )

    result = service.extract({"doc_id": "doc", "clean_text": clean_text})

    assert result["doc_id"] == "doc"
    assert result["model_name"] == "test-model"
    assert result["chunks"][0]["chunk_id"] == "doc_c001"
    assert len(result["chunks"][0]["entities"]) == 2
    assert len(result["chunks"][0]["relations"]) == 1


def test_service_requires_environment_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    service = LLMExtractionService(api_key="", max_retries=1, relation_review_passes=0)

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        service.preflight()


def test_http_error_does_not_include_api_key():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "invalid never-print-this-secret"}},
        )

    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="never-print-this-secret",
        model="test-model",
        max_retries=1,
        relation_review_passes=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        service.preflight()

    assert "never-print-this-secret" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_relation_review_adds_only_grounded_relations():
    clean_text = "APT28 used X-Agent malware."
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        entities = [
            {
                "name": "APT28",
                "type": "APT_GROUP",
                "aliases": [],
                "description": "Threat group",
                "mention_text": "APT28",
                "evidence_text": clean_text,
                "confidence": 0.95,
            },
            {
                "name": "X-Agent",
                "type": "MALWARE",
                "aliases": [],
                "description": "Malware",
                "mention_text": "X-Agent",
                "evidence_text": clean_text,
                "confidence": 0.9,
            },
        ]
        if calls == 1:
            return api_response({"entities": entities, "relations": []})
        return api_response(
            {
                "entities": [],
                "relations": [
                    {
                        "head_name": "APT28",
                        "head_type": "APT_GROUP",
                        "relation_type": "USES",
                        "tail_name": "X-Agent",
                        "tail_type": "MALWARE",
                        "evidence_text": clean_text,
                        "confidence": 0.9,
                    }
                ],
            }
        )

    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=1,
        relation_review_passes=1,
        transport=httpx.MockTransport(handler),
    )

    result = service.extract({"doc_id": "doc", "clean_text": clean_text})

    assert calls == 2
    assert len(result["chunks"][0]["relations"]) == 1
    assert service.last_warnings == []
