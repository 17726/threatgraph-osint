"""OpenAI-compatible LLM extraction service for ThreatGraph candidate data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts.validate_extraction_result import (
    ALLOWED_RELATIONS,
    load_json,
    validate_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EXTRACTION_SCHEMA_PATH = REPO_ROOT / "docs/schemas/extraction-result.schema.json"
DEFAULT_PROMPT_PATH = REPO_ROOT / "docs/prompts/extract-v5.md"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    return load_json(schema_path or DEFAULT_EXTRACTION_SCHEMA_PATH)


def _load_prompt_block(heading: str, prompt_path: Path | None = None) -> str:
    path = prompt_path or DEFAULT_PROMPT_PATH
    prompt_document = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*```text\s*(.*?)\s*```",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(prompt_document)
    if not match:
        raise ValueError(f"无法从 Prompt 文档读取 {heading}: {path}")
    return match.group(1).strip()


def load_system_prompt(prompt_path: Path | None = None) -> str:
    base_prompt = _load_prompt_block("系统提示词", prompt_path)
    runtime_managed_prefixes = (
        "2. JSON 必须符合",
        "7. char_start",
        "8. candidate_status",
        "9. validation_status",
    )
    base_prompt = "\n".join(
        line
        for line in base_prompt.splitlines()
        if not line.strip().startswith(runtime_managed_prefixes)
    )
    entity_types = "\n".join(f"- {entity_type}" for entity_type in ENTITY_TYPES)
    relation_types = "\n".join(f"- {relation_type}" for relation_type in RELATION_TYPES)
    allowed_pairs = []
    for relation_type, rule in ALLOWED_RELATIONS.items():
        if relation_type == "RELATED_TO":
            allowed_pairs.append("- RELATED_TO: 任意实体类型 -> 任意实体类型（仅人工兜底）")
            continue
        heads = set(rule.get("heads") or set())
        tails = set(rule.get("tails") or set())
        pairs = set(rule.get("pairs") or set())
        cartesian_pairs = {(head, tail) for head in heads for tail in tails}
        if pairs == cartesian_pairs:
            allowed_pairs.append(
                f"- {relation_type}: {'/'.join(sorted(heads))} -> {'/'.join(sorted(tails))}"
            )
        else:
            pair_text = ", ".join(f"{head}->{tail}" for head, tail in sorted(pairs))
            allowed_pairs.append(f"- {relation_type}: {pair_text}")
    return (
        f"{base_prompt}\n\n"
        f"实体类型白名单：\n{entity_types}\n\n"
        f"关系类型白名单：\n{relation_types}\n\n"
        f"关系类型配对矩阵：\n{'\n'.join(allowed_pairs)}\n\n"
        "重要：关系矩阵只是合法类型白名单，不是待生成清单。"
        "不得枚举实体组合；只有原文明示且能逐字给出非空 evidence_text 的关系才可输出。\n"
        "当前 API 调用只生成紧凑语义草稿；字符位置、候选状态、校验字段和顶层元数据由运行器补全。"
    )


def _schema_enum(name: str) -> tuple[str, ...]:
    values = load_schema()["$defs"][name]["enum"]
    return tuple(str(value) for value in values)


ENTITY_TYPES = _schema_enum("entity_type")
RELATION_TYPES = _schema_enum("relation_type")

BENIGN_CONNECTIVITY_DOMAINS = {
    "google.com", "amazon.com", "apple.com", "bing.com",
    "facebook.com", "microsoft.com", "yahoo.com", "twitter.com",
    "join.me", "youtube.com", "instagram.com", "linkedin.com",
    "github.com", "dropbox.com", "office.com", "live.com",
    "outlook.com", "azure.com", "cloudflare.com", "akamai.net",
}

_HASH_PATTERN = re.compile(r"^[A-Fa-f0-9]{32,64}$")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def generate_run_id(doc_id: str, prompt_version: str, model_name: str = "") -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    safe_model = re.sub(r"[^a-zA-Z0-9._-]+", "-", model_name).strip("-") if model_name else ""
    model_tag = f"_{safe_model}" if safe_model else ""
    return f"extract_{doc_id}_{prompt_version}{model_tag}_{timestamp}"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _extract_json_object(response_text: str) -> dict[str, Any]:
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, count=1)

    start = text.find("{")
    if start < 0:
        raise ValueError("LLM 返回内容中未找到 JSON 对象")

    try:
        payload, end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 返回的 JSON 无法解析: {exc.msg}") from exc

    trailing = text[start + end :].strip()
    if trailing:
        raise ValueError("LLM 在 JSON 对象后返回了多余内容")
    if not isinstance(payload, dict):
        raise ValueError("LLM 返回的 JSON 顶层必须是对象")
    return payload


def _find_text_span(clean_text: str, evidence: str) -> tuple[int | None, int | None]:
    if not evidence:
        return None, None
    # 1. Exact match (fast path, preserves accuracy)
    start = clean_text.find(evidence)
    if start >= 0:
        return start, start + len(evidence)
    # 2. Fuzzy match: each whitespace char in evidence becomes \s+,
    #    and \s* is inserted between every adjacent pair, so whitespace
    #    can appear anywhere (not just where evidence has it).
    #    Handles "Kimusky, also" vs "Kimusky\n, also" (whitespace shifted).
    pattern = r"\s*".join(
        r"\s+" if ch.isspace() else re.escape(ch) for ch in evidence
    )
    try:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            return match.start(), match.end()
    except re.error:
        pass
    return None, None


def _normalize_candidate_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


def _candidate_names(candidate: dict[str, Any]) -> set[str]:
    values = [candidate.get("name", ""), *candidate.get("aliases", [])]
    return {
        _normalize_candidate_name(value)
        for value in values
        if isinstance(value, str) and value.strip()
    }


def _audit_candidate(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    disposition = "merged" if "duplicate" in reason or "merged" in reason else "rejected"
    return {
        **candidate,
        "candidate_status": disposition,
        "audit_reason": reason,
    }


def _deduplicate_entities(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deduplicated: list[dict[str, Any]] = []
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        existing = next(
            (
                item
                for item in deduplicated
                if item["type"] == candidate["type"]
                and _candidate_names(item) & _candidate_names(candidate)
            ),
            None,
        )
        if existing is None:
            deduplicated.append(candidate)
            continue

        merged.append(_audit_candidate(candidate, "duplicate_or_alias_merged"))

        merged_aliases = [
            *existing["aliases"],
            candidate["name"],
            *candidate["aliases"],
        ]
        primary_name = _normalize_candidate_name(existing["name"])
        seen = {primary_name}
        existing["aliases"] = []
        for alias in merged_aliases:
            normalized_alias = _normalize_candidate_name(alias)
            if not normalized_alias or normalized_alias in seen:
                continue
            seen.add(normalized_alias)
            existing["aliases"].append(alias)
        existing["confidence"] = max(existing["confidence"], candidate["confidence"])
    return deduplicated, merged


def validate_entity(entity: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(entity.get("name"), str) or not entity["name"].strip():
        errors.append("name 不能为空")
    if entity.get("type") not in ENTITY_TYPES:
        errors.append(f"未知实体类型: {entity.get('type')}")
    aliases = entity.get("aliases")
    if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
        errors.append("aliases 必须是字符串数组")
    if not isinstance(entity.get("description"), str):
        errors.append("description 必须是字符串")
    if not isinstance(entity.get("mention_text"), str):
        errors.append("mention_text 必须是字符串")
    if not isinstance(entity.get("evidence_text"), str) or not entity["evidence_text"].strip():
        errors.append("evidence_text 不能为空")
    confidence = entity.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        errors.append(f"confidence 必须是数字: {confidence}")
    elif not 0 <= confidence <= 1:
        errors.append(f"confidence 不在 [0,1] 范围内: {confidence}")
    return errors


def validate_relation(
    relation: dict[str, Any],
    known_entities: set[tuple[str, str]],
) -> list[str]:
    errors: list[str] = []
    relation_type = relation.get("relation_type")
    rule = ALLOWED_RELATIONS.get(relation_type)
    if rule is None:
        return [f"未知关系类型: {relation_type}"]

    head_type = relation.get("head_type")
    tail_type = relation.get("tail_type")
    for field_name in (
        "head_name",
        "head_type",
        "relation_type",
        "tail_name",
        "tail_type",
    ):
        if not isinstance(relation.get(field_name), str) or not relation[field_name].strip():
            errors.append(f"{field_name} 必须是非空字符串")
    if relation_type != "RELATED_TO" and (head_type, tail_type) not in rule["pairs"]:
        errors.append(f"不允许组合 ({head_type},{relation_type},{tail_type})")

    head_key = (relation.get("head_name", ""), head_type or "")
    tail_key = (relation.get("tail_name", ""), tail_type or "")
    if head_key not in known_entities:
        errors.append(f"head ({head_key[0]}, {head_key[1]}) 不在候选实体中")
    if tail_key not in known_entities:
        errors.append(f"tail ({tail_key[0]}, {tail_key[1]}) 不在候选实体中")
    if not isinstance(relation.get("evidence_text"), str) or not relation["evidence_text"].strip():
        errors.append("evidence_text 不能为空")
    confidence = relation.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        errors.append(f"confidence 必须是数字: {confidence}")
    elif not 0 <= confidence <= 1:
        errors.append(f"confidence 不在 [0,1] 范围内: {confidence}")
    return errors


def _candidate_chunk(payload: dict[str, Any], chunk_id: str) -> dict[str, Any]:
    if "chunks" not in payload:
        return payload
    chunks = payload.get("chunks")
    if not isinstance(chunks, list) or len(chunks) != 1:
        raise ValueError("当前单文档模式要求 LLM 返回且仅返回一个 chunk")
    chunk = chunks[0]
    if not isinstance(chunk, dict):
        raise ValueError("LLM 返回的 chunk 必须是对象")
    returned_chunk_id = chunk.get("chunk_id")
    if returned_chunk_id not in {None, "", chunk_id}:
        raise ValueError(f"LLM 返回的 chunk_id 不一致: {returned_chunk_id!r}")
    return chunk


def parse_llm_response_with_audit(
    response_text: str,
    chunk_id: str,
    clean_text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split raw model candidates into a valid extraction chunk and rejected audit."""
    payload = _extract_json_object(response_text)
    chunk = _candidate_chunk(payload, chunk_id)
    entities = chunk.get("entities", [])
    relations = chunk.get("relations", [])
    if not isinstance(entities, list) or not isinstance(relations, list):
        raise ValueError("entities 和 relations 必须是数组")

    processed_entities: list[dict[str, Any]] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise ValueError(f"entities[{index}] 必须是对象")
        evidence = entity.get("evidence_text", "")
        char_start, char_end = _find_text_span(clean_text, evidence)
        # Auto-correct evidence_text to match the actual clean_text slice
        # (handles whitespace differences like space↔newline from LLM output)
        if char_start is not None and clean_text[char_start:char_end] != evidence:
            evidence = clean_text[char_start:char_end]
        aliases = entity.get("aliases", [])
        if isinstance(aliases, list) and all(isinstance(alias, str) for alias in aliases):
            aliases = list(dict.fromkeys(alias for alias in aliases if alias))
        candidate = {
            "name": entity.get("name", ""),
            "type": entity.get("type", ""),
            "aliases": aliases,
            "description": entity.get("description", ""),
            "mention_text": entity.get("mention_text", ""),
            "evidence_text": evidence,
            "char_start": char_start,
            "char_end": char_end,
            "confidence": entity.get("confidence", 0.5),
            "candidate_status": "candidate",
            "validation_status": "unchecked",
            "validation_errors": [],
        }
        errors = validate_entity(candidate)
        if evidence and char_start is None:
            errors.append("evidence_text 未出现在 document.clean_text 中")

        name = candidate.get("name", "")
        if _HASH_PATTERN.match(name) and candidate["type"] == "MALWARE":
            errors.append("SHA256/MD5/SHA1 哈希值不能作为 MALWARE 实体")
        if candidate["type"] == "INFRASTRUCTURE":
            name_lower = name.lower().rstrip(".")
            for domain in BENIGN_CONNECTIVITY_DOMAINS:
                if name_lower == domain or name_lower.endswith("." + domain):
                    errors.append(f"良性连通性检测域名不能作为 INFRASTRUCTURE")
                    break

        candidate["validation_status"] = "valid" if not errors else "invalid"
        candidate["validation_errors"] = errors
        processed_entities.append(candidate)

    accepted_entities, merged_entities = _deduplicate_entities(
        [
            candidate
            for candidate in processed_entities
            if candidate["validation_status"] == "valid"
        ]
    )
    rejected_entities = [
        _audit_candidate(candidate, "validation_failed")
        for candidate in processed_entities
        if candidate["validation_status"] != "valid"
    ]
    rejected_entities.extend(merged_entities)
    known_entities: set[tuple[str, str]] = set()
    endpoint_names: dict[tuple[str, str], str] = {}
    for candidate in accepted_entities:
        known_entities.add((candidate["name"], candidate["type"]))
        endpoint_names[
            (candidate["type"], _normalize_candidate_name(candidate["name"]))
        ] = candidate["name"]
        known_entities.update(
            (alias, candidate["type"])
            for alias in candidate["aliases"]
            if isinstance(alias, str) and alias
        )
        for alias in candidate["aliases"]:
            endpoint_names[(candidate["type"], _normalize_candidate_name(alias))] = candidate[
                "name"
            ]

    processed_relations: list[dict[str, Any]] = []
    rejected_relations: list[dict[str, Any]] = []
    seen_relations: set[tuple[str, str, str, str, str]] = set()
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            raise ValueError(f"relations[{index}] 必须是对象")
        evidence = relation.get("evidence_text", "")
        char_start, char_end = _find_text_span(clean_text, evidence)
        if char_start is not None and clean_text[char_start:char_end] != evidence:
            evidence = clean_text[char_start:char_end]
        head_name = relation.get("head_name", "")
        tail_name = relation.get("tail_name", "")
        head_type = relation.get("head_type", "")
        tail_type = relation.get("tail_type", "")
        if isinstance(head_name, str) and isinstance(head_type, str):
            head_name = endpoint_names.get(
                (head_type, _normalize_candidate_name(head_name)),
                head_name,
            )
        if isinstance(tail_name, str) and isinstance(tail_type, str):
            tail_name = endpoint_names.get(
                (tail_type, _normalize_candidate_name(tail_name)),
                tail_name,
            )
        candidate = {
            "head_name": head_name,
            "head_type": relation.get("head_type", ""),
            "relation_type": relation.get("relation_type", ""),
            "tail_name": tail_name,
            "tail_type": relation.get("tail_type", ""),
            "evidence_text": evidence,
            "char_start": char_start,
            "char_end": char_end,
            "confidence": relation.get("confidence", 0.5),
            "candidate_status": "candidate",
            "validation_status": "unchecked",
            "validation_errors": [],
        }
        errors = validate_relation(candidate, known_entities)
        if evidence and char_start is None:
            errors.append("evidence_text 未出现在 document.clean_text 中")
        candidate["validation_status"] = "valid" if not errors else "invalid"
        candidate["validation_errors"] = errors
        if candidate["validation_status"] != "valid":
            rejected_relations.append(_audit_candidate(candidate, "validation_failed"))
            continue
        if (
            candidate["head_type"] == candidate["tail_type"]
            and _normalize_candidate_name(candidate["head_name"])
            == _normalize_candidate_name(candidate["tail_name"])
        ):
            rejected_relations.append(_audit_candidate(candidate, "self_relation_removed"))
            continue
        signature = (
            _normalize_candidate_name(candidate["head_name"]),
            candidate["head_type"],
            candidate["relation_type"],
            _normalize_candidate_name(candidate["tail_name"]),
            candidate["tail_type"],
        )
        if signature in seen_relations:
            rejected_relations.append(_audit_candidate(candidate, "duplicate_relation_removed"))
            continue
        seen_relations.add(signature)
        processed_relations.append(candidate)

    return (
        {"entities": accepted_entities, "relations": processed_relations},
        {
            "rejected_entities": rejected_entities,
            "rejected_relations": rejected_relations,
        },
    )


def parse_llm_response(response_text: str, chunk_id: str, clean_text: str) -> dict[str, Any]:
    """Parse a model response and return only schema-valid import candidates."""
    result, _audit = parse_llm_response_with_audit(response_text, chunk_id, clean_text)
    return result


def build_user_prompt(
    *,
    run_id: str,
    doc_id: str,
    chunk_id: str,
    clean_text: str,
    model_name: str,
    prompt_version: str,
) -> str:
    return f"""请从下面唯一一个 chunk 抽取候选实体和关系。

运行信息：run_id={run_id}, doc_id={doc_id}, chunk_id={chunk_id},
model_name={model_name}, prompt_version={prompt_version}。

为了减少模型生成错误，本次只输出紧凑草稿；运行器会补全顶层元数据、char_start、char_end、
candidate_status、validation_status 和 validation_errors，再校验最终 extraction_result schema。

只输出以下 JSON 结构，不要输出 Markdown，不要输出上述由运行器补全的字段：
{{
  "entities": [
    {{
      "name": "标准名称",
      "type": "实体类型白名单值",
      "aliases": [],
      "description": "简短描述",
      "mention_text": "原文提及",
      "evidence_text": "最短连续原文证据",
      "confidence": 0.9
    }}
  ],
  "relations": [
    {{
      "head_name": "必须等于 entities.name 或 aliases",
      "head_type": "主体类型",
      "relation_type": "关系类型白名单值",
      "tail_name": "必须等于 entities.name 或 aliases",
      "tail_type": "客体类型",
      "evidence_text": "最短连续原文证据",
      "confidence": 0.9
    }}
  ]
}}

同一实体和同一关系只输出一次。禁止枚举关系矩阵；原文没有明示的关系不要输出。
单轮最多输出 80 个实体和 80 个关系。关系复核会另行补漏，不要为了追求数量降低证据标准。

重要提醒：
- evidence_text 必须逐字复制自 <chunk_text>，禁止任何改写、概括、缩写或调整大小写。在 chunk_text 中找到原文句子后直接 copy-paste，不要自己重新打字
- 安全厂商（如 Unit 42、Microsoft、ESET、ThreatConnect、Palo Alto Networks）发现/监测/报告威胁活动 → 不要生成 DISCOVERED_BY、ATTRIBUTED_TO 或 AFFILIATED_WITH 关系
- 安全公司拥有或运营自己的产品/工具（如 WildFire、AutoFocus、Traps）→ 不要生成 CONTROLS 关系
- 工具/技术/基础设施的使用关系必须以 APT_GROUP 或 CAMPAIGN 为主体，恶意软件(MALWARE)不能作为 USES 关系的主体
- 全文扫描所有可执行文件、命令行工具、攻击技术和网络基础设施，不要只关注文章前半部分
- 不要忘记抽取日期、月份、年份等 TIME 类型实体
- 实体名称使用原文措辞，保持单复数一致（如原文是 "Ministries" 不要写成 "Ministry"）

<chunk_text>
{clean_text}
</chunk_text>"""


class LLMExtractionService:
    """Call an OpenAI-compatible chat-completions API for candidate extraction."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        max_output_tokens: int | None = None,
        relation_review_passes: int | None = None,
        *,
        trust_env: bool | None = None,
        transport: httpx.BaseTransport | None = None,
        prompt_path: Path | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        self.max_retries = max_retries or int(os.getenv("LLM_MAX_RETRIES", "3"))
        self.max_output_tokens = max_output_tokens or int(
            os.getenv("LLM_MAX_OUTPUT_TOKENS", "32768")
        )
        self.relation_review_passes = (
            relation_review_passes
            if relation_review_passes is not None
            else int(os.getenv("LLM_RELATION_REVIEW_PASSES", "0"))
        )
        self.trust_env = _env_bool("LLM_TRUST_ENV", False) if trust_env is None else trust_env
        self.transport = transport
        self.system_prompt = load_system_prompt(prompt_path)
        self.last_warnings: list[str] = []
        self.last_candidate_audit: dict[str, Any] | None = None

    def _require_api_key(self) -> None:
        if not self.api_key.strip():
            raise ValueError("未配置 LLM_API_KEY；密钥必须通过环境变量提供")

    def _safe_error_text(self, value: object, limit: int = 1000) -> str:
        text = str(value).replace("\n", " ")
        if self.api_key:
            text = text.replace(self.api_key, "[REDACTED]")
        return text[:limit]

    def preflight(self) -> dict[str, Any]:
        """Make a minimal real request without storing the credential or response."""
        self._require_api_key()
        content, metadata = self._call_api(
            [
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": 'Return exactly {"ok":true}.'},
            ],
            max_tokens=32,
        )
        payload = _extract_json_object(content)
        if payload.get("ok") is not True:
            raise ValueError("LLM 预检返回内容不符合预期")
        return {
            "ok": True,
            "base_url": self.base_url,
            "requested_model": self.model,
            "response_model": metadata.get("model", ""),
            "usage": metadata.get("usage", {}),
        }

    def extract(self, document: dict[str, Any], prompt_version: str = "extract-v5") -> dict[str, Any]:
        """Extract candidate entities and relations from one document."""
        self._require_api_key()
        self.last_warnings = []
        self.last_candidate_audit = None
        doc_id = document["doc_id"]
        clean_text = document.get("clean_text", "")
        if not isinstance(clean_text, str) or not clean_text.strip():
            raise ValueError("document.clean_text 不能为空")

        run_id = generate_run_id(doc_id, prompt_version, self.model)
        chunk_id = f"{doc_id}_c001"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": build_user_prompt(
                    run_id=run_id,
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    clean_text=clean_text,
                    model_name=self.model,
                    prompt_version=prompt_version,
                ),
            },
        ]

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            attempt_max_tokens = min(self.max_output_tokens * (2**attempt), 65536)
            try:
                response_text, metadata = self._call_api(
                    messages,
                    max_tokens=attempt_max_tokens,
                )
                if metadata.get("finish_reason") == "length":
                    raise ValueError(
                        f"LLM 输出达到 max_tokens={attempt_max_tokens}，JSON 被截断"
                    )
                chunk_result, chunk_audit = parse_llm_response_with_audit(
                    response_text,
                    chunk_id,
                    clean_text,
                )
                result = {
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "doc_id": doc_id,
                    "model_name": self.model,
                    "prompt_version": prompt_version,
                    "chunks": [{"chunk_id": chunk_id, **chunk_result}],
                }
                candidate_audit = {
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "doc_id": doc_id,
                    "model_name": self.model,
                    "prompt_version": prompt_version,
                    "chunks": [{"chunk_id": chunk_id, **chunk_audit}],
                }
                result = self._run_relation_review_passes(
                    result,
                    candidate_audit=candidate_audit,
                    clean_text=clean_text,
                    chunk_id=chunk_id,
                )
                report = validate_payload(result, document=document)
                if not report.ok:
                    raise ValueError("; ".join(report.errors))
                self.last_candidate_audit = candidate_audit
                return result
            except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    error_detail = self._safe_error_text(exc)
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "上一次输出未通过校验。请重新生成完整且可解析的 JSON；"
                                "不要输出 Markdown，不要省略必填字段，不要在 JSON 后追加文字。"
                                f"校验错误：{error_detail}"
                            ),
                        }
                    )
                    time.sleep(min(2**attempt, 4))

        raise RuntimeError(
            f"LLM 抽取失败 (已尝试 {self.max_retries} 次): {last_error}"
        ) from last_error

    def _run_relation_review_passes(
        self,
        result: dict[str, Any],
        *,
        candidate_audit: dict[str, Any],
        clean_text: str,
        chunk_id: str,
    ) -> dict[str, Any]:
        for review_index in range(self.relation_review_passes):
            current_chunk = result["chunks"][0]
            entity_reference = [
                {
                    "name": entity["name"],
                    "type": entity["type"],
                    "aliases": entity["aliases"],
                }
                for entity in current_chunk["entities"]
            ]
            review_prompt = f"""执行关系抽取复核第 {review_index + 1} 轮。

只能使用下面已通过证据校验的实体，不得新增实体，不得把 aliases 当成独立实体：
{json.dumps(entity_reference, ensure_ascii=False, indent=2)}

重新通读全文，补充首轮可能遗漏的明确关系。关系主体和客体名称必须使用上面实体的 name。
每条关系必须有最短且非空的连续原文 evidence_text；禁止枚举实体组合或推断关系。
只输出 JSON：{{"entities": [], "relations": [...]}}。

<chunk_text>
{clean_text}
</chunk_text>"""
            try:
                response_text, metadata = self._call_api(
                    [
                        {
                            "role": "system",
                            "content": self.system_prompt
                            + "\n\n当前任务只复核关系，不新增实体。",
                        },
                        {"role": "user", "content": review_prompt},
                    ],
                    max_tokens=min(self.max_output_tokens, 32768),
                )
                if metadata.get("finish_reason") == "length":
                    raise ValueError("关系复核输出被截断")
                review_payload = _extract_json_object(response_text)
                review_chunk = _candidate_chunk(review_payload, chunk_id)
                review_relations = review_chunk.get("relations", [])
                if not isinstance(review_relations, list):
                    raise ValueError("关系复核的 relations 必须是数组")

                merged_chunk, review_audit = parse_llm_response_with_audit(
                    json.dumps(
                        {
                            "entities": current_chunk["entities"],
                            "relations": [
                                *current_chunk["relations"],
                                *review_relations,
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    chunk_id,
                    clean_text,
                )
                result["chunks"] = [{"chunk_id": chunk_id, **merged_chunk}]
                audit_chunk = candidate_audit["chunks"][0]
                audit_chunk["rejected_entities"].extend(
                    review_audit["rejected_entities"]
                )
                audit_chunk["rejected_relations"].extend(
                    review_audit["rejected_relations"]
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.last_warnings.append(
                    f"关系复核第 {review_index + 1} 轮失败，已保留首轮结果: "
                    f"{self._safe_error_text(exc, limit=500)}"
                )
        return result

    def _call_api(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
    ) -> tuple[str, dict[str, Any]]:
        self._require_api_key()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.base_url.startswith("https://api.deepseek.com"):
            body["thinking"] = {"type": "disabled"}

        with httpx.Client(
            timeout=self.timeout,
            trust_env=self.trust_env,
            transport=self.transport,
        ) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = self._safe_error_text(response.text.strip(), limit=500)
                raise httpx.HTTPStatusError(
                    f"LLM API 返回 HTTP {response.status_code}: {detail}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
            payload = response.json()

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("LLM API 响应缺少 choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM API 返回了空 content")
        return content, {
            "model": payload.get("model", ""),
            "usage": payload.get("usage", {}),
            "finish_reason": payload.get("choices", [{}])[0].get("finish_reason", ""),
        }

    def save_result(
        self,
        result: dict[str, Any],
        output_dir: str | Path = "data/extracted",
    ) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        result_path = output_path / f"{result['run_id']}.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return result_path

    def save_candidate_audit(
        self,
        output_dir: str | Path = "data/extracted",
    ) -> Path:
        if self.last_candidate_audit is None:
            raise ValueError("当前没有可保存的候选审计结果")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        audit_path = output_path / f"{self.last_candidate_audit['run_id']}.candidate-audit.json"
        audit_path.write_text(
            json.dumps(self.last_candidate_audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return audit_path
