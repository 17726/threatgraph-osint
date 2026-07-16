import json
import time
from pathlib import Path

import httpx
import pytest

from backend.app.core.document_contract import document_content_hash
from backend.app.services.llm_service import (
    DEFAULT_PROMPT_PATH,
    ENTITY_TYPES,
    RELATION_TYPES,
    LLMExtractionService,
    generate_run_id,
    load_system_prompt,
    parse_llm_response,
    parse_llm_response_with_audit,
)


ROOT = Path(__file__).resolve().parents[2]


def build_document(doc_id: str, clean_text: str) -> dict:
    document = json.loads(
        (ROOT / "data/examples/document.apt28.thn.beardshell.example.json").read_text(
            encoding="utf-8"
        )
    )
    document["doc_id"] = doc_id
    document["clean_text"] = clean_text
    document["content_hash"] = document_content_hash(clean_text)
    return document


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
    assert DEFAULT_PROMPT_PATH.name == "extract-1.0.md"
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

    result, audit = parse_llm_response_with_audit(
        json.dumps(payload),
        "doc_c001",
        "APT28",
    )

    assert [entity["name"] for entity in result["entities"]] == ["APT28"]
    assert result["relations"] == []
    assert [entity["name"] for entity in audit["rejected_entities"]] == [
        "Invented malware"
    ]
    assert audit["rejected_entities"][0]["audit_reason"] == "validation_failed"
    assert len(audit["rejected_relations"]) == 1


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

    result, audit = parse_llm_response_with_audit(
        json.dumps(payload),
        "doc_c001",
        clean_text,
    )

    assert [entity["name"] for entity in result["entities"]] == ["Sofacy", "X-Agent"]
    assert len(result["relations"]) == 1
    assert result["relations"][0]["head_name"] == "Sofacy"
    assert len(audit["rejected_entities"]) == 1
    assert audit["rejected_entities"][0]["audit_reason"] == "duplicate_or_alias_merged"
    assert {item["audit_reason"] for item in audit["rejected_relations"]} == {
        "duplicate_relation_removed",
        "self_relation_removed",
    }


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


def test_extract_returns_contract_valid_candidate_result(tmp_path):
    clean_text = "APT28 used X-Agent malware."

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "ThreatGraph" in body["messages"][0]["content"]
        assert "prompt_version=1.0" in body["messages"][1]["content"]
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

    result = service.extract(build_document("doc", clean_text))

    assert result["doc_id"] == "doc"
    assert result["model_name"] == "test-model"
    assert result["prompt_version"] == "1.0"
    assert result["generated_at"].endswith("+00:00")
    assert result["run_id"].startswith("extract-doc-test-model-1.0-1.0-")
    assert result["chunks"][0]["chunk_id"] == "doc_c001"
    assert len(result["chunks"][0]["entities"]) == 2
    assert len(result["chunks"][0]["relations"]) == 1
    assert service.last_candidate_audit is not None
    assert service.last_api_observation["calls"] == 1
    assert service.last_api_observation["duration_ms"] >= 0
    assert service.last_api_observation["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    audit_path = service.save_candidate_audit(tmp_path)
    saved_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert saved_audit["run_id"] == result["run_id"]
    assert saved_audit["generated_at"] == result["generated_at"]
    assert audit_path.name == f"{result['run_id']}-candidate-audit.json"
    assert saved_audit["chunks"][0]["rejected_entities"] == []


def test_slow_api_request_emits_heartbeat_progress():
    messages: list[str] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        time.sleep(0.04)
        return api_response({"ok": True})

    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=1,
        relation_review_passes=0,
        heartbeat_interval_seconds=0.01,
        progress_callback=messages.append,
        transport=httpx.MockTransport(handler),
    )

    service.preflight()

    assert any("API 请求已等待" in message for message in messages)


def test_extract_reports_retry_attempts(monkeypatch):
    messages: list[str] = []
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [
                        {"message": {"content": "not-json"}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                },
            )
        return api_response({"entities": [], "relations": []})

    monkeypatch.setattr("backend.app.services.llm_service.time.sleep", lambda _seconds: None)
    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=2,
        relation_review_passes=0,
        progress_callback=messages.append,
        transport=httpx.MockTransport(handler),
    )

    service.extract(build_document("doc", "APT28 activity."))

    assert any("开始第 1/2 次抽取请求" in message for message in messages)
    assert any("第 1/2 次抽取请求失败" in message for message in messages)
    assert any("开始第 2/2 次抽取请求" in message for message in messages)


def test_truncated_response_retries_with_same_budget_and_compaction_prompt(monkeypatch):
    request_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        request_bodies.append(body)
        if len(request_bodies) == 1:
            return httpx.Response(
                200,
                json={
                    "model": "test-model",
                    "choices": [
                        {
                            "message": {"content": '{"entities": ['},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 512,
                        "total_tokens": 522,
                    },
                },
            )
        return api_response({"entities": [], "relations": []})

    monkeypatch.setattr("backend.app.services.llm_service.time.sleep", lambda _seconds: None)
    service = LLMExtractionService(
        base_url="https://example.test/v1",
        api_key="test-secret",
        model="test-model",
        max_retries=2,
        max_output_tokens=512,
        relation_review_passes=0,
        transport=httpx.MockTransport(handler),
    )

    result = service.extract(build_document("doc", "APT28 activity."))

    assert result["chunks"][0]["entities"] == []
    assert [body["max_tokens"] for body in request_bodies] == [512, 512]
    retry_prompt = request_bodies[1]["messages"][-1]["content"]
    assert "相同 token 预算" in retry_prompt
    assert "最多保留 48 个高置信实体" in retry_prompt


def test_generate_run_id_uses_versioned_artifact_contract():
    first = generate_run_id(
        "apt28_080",
        "deepseek-v4-flash",
        "1.0",
        generated_at="2026-07-13T08:39:26.515108+00:00",
    )
    second = generate_run_id(
        "apt28_080",
        "deepseek-v4-flash",
        "1.0",
        generated_at="2026-07-13T08:39:26.515108+00:00",
    )

    assert first.startswith(
        "extract-apt28_080-deepseek-v4-flash-1.0-1.0-20260713083926515108-"
    )
    assert first != second


def test_save_result_rejects_run_id_metadata_mismatch(tmp_path):
    service = LLMExtractionService(
        api_key="test-secret",
        max_retries=1,
        relation_review_passes=0,
    )
    result = json.loads(
        (ROOT / "data/examples/extraction_result.apt28.thn.beardshell.example.json").read_text(
            encoding="utf-8"
        )
    )
    result["model_name"] = "another-model"

    with pytest.raises(ValueError, match="run_id"):
        service.save_result(result, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_save_candidate_audit_rejects_run_id_metadata_mismatch(tmp_path):
    service = LLMExtractionService(
        api_key="test-secret",
        max_retries=1,
        relation_review_passes=0,
    )
    extraction = json.loads(
        (ROOT / "data/examples/extraction_result.apt28.thn.beardshell.example.json").read_text(
            encoding="utf-8"
        )
    )
    service.last_candidate_audit = {
        "schema_version": extraction["schema_version"],
        "run_id": extraction["run_id"],
        "doc_id": extraction["doc_id"],
        "model_name": "another-model",
        "prompt_version": extraction["prompt_version"],
        "generated_at": extraction["generated_at"],
        "chunks": [],
    }

    with pytest.raises(ValueError, match="run_id"):
        service.save_candidate_audit(tmp_path)

    assert list(tmp_path.iterdir()) == []


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

    result = service.extract(build_document("doc", clean_text))

    assert calls == 2
    assert len(result["chunks"][0]["relations"]) == 1
    assert service.last_warnings == []
