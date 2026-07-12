"""
LLM 驱动的威胁情报实体关系抽取服务。

支持 OpenAI-compatible API，从清洗后的文档文本中抽取
实体 (NER) 和关系 (RE)，输出为 extraction-result schema 格式。
"""

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema
from jsonschema import ValidationError as SchemaValidationError


DEFAULT_EXTRACTION_SCHEMA_PATH = Path("docs/schemas/extraction-result.schema.json")

ENTITY_TYPES = [
    "APT_GROUP", "ORGANIZATION", "PERSON", "MALWARE", "TOOL", "CVE",
    "TECHNIQUE", "INFRASTRUCTURE", "LOCATION", "FINANCIAL_ACCOUNT",
    "COUNTRY", "REGION", "INDUSTRY", "TIME", "EVENT", "CAMPAIGN",
    "BEHAVIOR_PATTERN",
]

RELATION_TYPES = [
    "USES", "TARGETS", "EXPLOITS", "ATTRIBUTED_TO", "AFFILIATED_WITH",
    "LOCATED_IN", "HAPPENED_AT", "PART_OF", "LEADS_TO", "RELATED_TO",
    "DISCOVERED_BY", "CAUSES", "HAS_BEHAVIOR", "MEMBER_OF",
    "CONTROLS", "TRANSFERS_TO", "INSTANCE_OF", "PRECEDES",
]

ALLOWED_RELATIONS: dict[str, dict[str, Any]] = {
    "USES": {
        "heads": ["PERSON", "ORGANIZATION", "COUNTRY", "APT_GROUP", "CAMPAIGN"],
        "tails": ["MALWARE", "TOOL", "TECHNIQUE", "INFRASTRUCTURE"],
        "pairs": [
            ("PERSON", "MALWARE"), ("PERSON", "TOOL"), ("PERSON", "TECHNIQUE"), ("PERSON", "INFRASTRUCTURE"),
            ("ORGANIZATION", "MALWARE"), ("ORGANIZATION", "TOOL"), ("ORGANIZATION", "TECHNIQUE"), ("ORGANIZATION", "INFRASTRUCTURE"),
            ("COUNTRY", "MALWARE"), ("COUNTRY", "TOOL"), ("COUNTRY", "TECHNIQUE"), ("COUNTRY", "INFRASTRUCTURE"),
            ("APT_GROUP", "MALWARE"), ("APT_GROUP", "TOOL"), ("APT_GROUP", "TECHNIQUE"), ("APT_GROUP", "INFRASTRUCTURE"),
            ("CAMPAIGN", "MALWARE"), ("CAMPAIGN", "TOOL"), ("CAMPAIGN", "TECHNIQUE"), ("CAMPAIGN", "INFRASTRUCTURE"),
        ],
    },
    "TARGETS": {
        "heads": ["APT_GROUP", "CAMPAIGN", "MALWARE"],
        "tails": ["COUNTRY", "REGION", "INDUSTRY", "ORGANIZATION", "PERSON", "LOCATION"],
        "pairs": [
            ("APT_GROUP", "COUNTRY"), ("APT_GROUP", "REGION"), ("APT_GROUP", "INDUSTRY"), ("APT_GROUP", "ORGANIZATION"), ("APT_GROUP", "PERSON"), ("APT_GROUP", "LOCATION"),
            ("CAMPAIGN", "COUNTRY"), ("CAMPAIGN", "REGION"), ("CAMPAIGN", "INDUSTRY"), ("CAMPAIGN", "ORGANIZATION"), ("CAMPAIGN", "PERSON"), ("CAMPAIGN", "LOCATION"),
            ("MALWARE", "COUNTRY"), ("MALWARE", "REGION"), ("MALWARE", "INDUSTRY"), ("MALWARE", "ORGANIZATION"), ("MALWARE", "PERSON"), ("MALWARE", "LOCATION"),
        ],
    },
    "EXPLOITS": {
        "heads": ["PERSON", "ORGANIZATION", "COUNTRY", "APT_GROUP", "CAMPAIGN", "MALWARE", "TOOL"],
        "tails": ["CVE"],
        "pairs": [
            ("PERSON", "CVE"), ("ORGANIZATION", "CVE"), ("COUNTRY", "CVE"), ("APT_GROUP", "CVE"),
            ("CAMPAIGN", "CVE"), ("MALWARE", "CVE"), ("TOOL", "CVE"),
        ],
    },
    "ATTRIBUTED_TO": {
        "heads": ["APT_GROUP", "CAMPAIGN", "MALWARE"],
        "tails": ["COUNTRY", "ORGANIZATION"],
        "pairs": [
            ("APT_GROUP", "COUNTRY"), ("APT_GROUP", "ORGANIZATION"),
            ("CAMPAIGN", "COUNTRY"), ("CAMPAIGN", "ORGANIZATION"),
            ("MALWARE", "COUNTRY"), ("MALWARE", "ORGANIZATION"),
        ],
    },
    "AFFILIATED_WITH": {
        "heads": ["APT_GROUP", "ORGANIZATION"],
        "tails": ["APT_GROUP", "ORGANIZATION", "COUNTRY"],
        "pairs": [
            ("APT_GROUP", "APT_GROUP"), ("APT_GROUP", "ORGANIZATION"), ("APT_GROUP", "COUNTRY"),
            ("ORGANIZATION", "APT_GROUP"), ("ORGANIZATION", "ORGANIZATION"), ("ORGANIZATION", "COUNTRY"),
        ],
    },
    "LOCATED_IN": {
        "heads": ["ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE", "EVENT"],
        "tails": ["COUNTRY", "REGION", "LOCATION"],
        "pairs": [
            ("ORGANIZATION", "COUNTRY"), ("ORGANIZATION", "REGION"), ("ORGANIZATION", "LOCATION"),
            ("PERSON", "COUNTRY"), ("PERSON", "REGION"), ("PERSON", "LOCATION"),
            ("LOCATION", "COUNTRY"), ("LOCATION", "REGION"), ("LOCATION", "LOCATION"),
            ("INFRASTRUCTURE", "COUNTRY"), ("INFRASTRUCTURE", "REGION"), ("INFRASTRUCTURE", "LOCATION"),
            ("EVENT", "COUNTRY"), ("EVENT", "REGION"), ("EVENT", "LOCATION"),
        ],
    },
    "HAPPENED_AT": {
        "heads": ["EVENT", "CAMPAIGN"],
        "tails": ["TIME"],
        "pairs": [("EVENT", "TIME"), ("CAMPAIGN", "TIME")],
    },
    "PART_OF": {
        "heads": ["ORGANIZATION", "EVENT", "CAMPAIGN"],
        "tails": ["ORGANIZATION", "CAMPAIGN", "APT_GROUP"],
        "pairs": [
            ("ORGANIZATION", "ORGANIZATION"), ("ORGANIZATION", "CAMPAIGN"), ("ORGANIZATION", "APT_GROUP"),
            ("EVENT", "ORGANIZATION"), ("EVENT", "CAMPAIGN"), ("EVENT", "APT_GROUP"),
            ("CAMPAIGN", "ORGANIZATION"), ("CAMPAIGN", "CAMPAIGN"), ("CAMPAIGN", "APT_GROUP"),
        ],
    },
    "LEADS_TO": {
        "heads": ["TECHNIQUE", "BEHAVIOR_PATTERN", "EVENT"],
        "tails": ["TECHNIQUE", "BEHAVIOR_PATTERN", "EVENT"],
        "pairs": [
            ("TECHNIQUE", "TECHNIQUE"), ("TECHNIQUE", "BEHAVIOR_PATTERN"), ("TECHNIQUE", "EVENT"),
            ("BEHAVIOR_PATTERN", "TECHNIQUE"), ("BEHAVIOR_PATTERN", "BEHAVIOR_PATTERN"), ("BEHAVIOR_PATTERN", "EVENT"),
            ("EVENT", "TECHNIQUE"), ("EVENT", "BEHAVIOR_PATTERN"), ("EVENT", "EVENT"),
        ],
    },
    "DISCOVERED_BY": {
        "heads": ["CVE", "MALWARE", "TOOL", "CAMPAIGN"],
        "tails": ["ORGANIZATION", "PERSON"],
        "pairs": [
            ("CVE", "ORGANIZATION"), ("CVE", "PERSON"),
            ("MALWARE", "ORGANIZATION"), ("MALWARE", "PERSON"),
            ("TOOL", "ORGANIZATION"), ("TOOL", "PERSON"),
            ("CAMPAIGN", "ORGANIZATION"), ("CAMPAIGN", "PERSON"),
        ],
    },
    "CAUSES": {
        "heads": ["CVE", "TECHNIQUE", "MALWARE"],
        "tails": ["EVENT", "BEHAVIOR_PATTERN"],
        "pairs": [
            ("CVE", "EVENT"), ("CVE", "BEHAVIOR_PATTERN"),
            ("TECHNIQUE", "EVENT"), ("TECHNIQUE", "BEHAVIOR_PATTERN"),
            ("MALWARE", "EVENT"), ("MALWARE", "BEHAVIOR_PATTERN"),
        ],
    },
    "HAS_BEHAVIOR": {
        "heads": ["APT_GROUP", "CAMPAIGN"],
        "tails": ["BEHAVIOR_PATTERN", "TECHNIQUE"],
        "pairs": [
            ("APT_GROUP", "BEHAVIOR_PATTERN"), ("APT_GROUP", "TECHNIQUE"),
            ("CAMPAIGN", "BEHAVIOR_PATTERN"), ("CAMPAIGN", "TECHNIQUE"),
        ],
    },
    "MEMBER_OF": {
        "heads": ["PERSON"],
        "tails": ["APT_GROUP", "ORGANIZATION"],
        "pairs": [("PERSON", "APT_GROUP"), ("PERSON", "ORGANIZATION")],
    },
    "CONTROLS": {
        "heads": ["PERSON", "APT_GROUP", "ORGANIZATION"],
        "tails": ["FINANCIAL_ACCOUNT", "INFRASTRUCTURE", "ORGANIZATION"],
        "pairs": [
            ("PERSON", "FINANCIAL_ACCOUNT"), ("PERSON", "INFRASTRUCTURE"), ("PERSON", "ORGANIZATION"),
            ("APT_GROUP", "FINANCIAL_ACCOUNT"), ("APT_GROUP", "INFRASTRUCTURE"), ("APT_GROUP", "ORGANIZATION"),
            ("ORGANIZATION", "FINANCIAL_ACCOUNT"), ("ORGANIZATION", "INFRASTRUCTURE"), ("ORGANIZATION", "ORGANIZATION"),
        ],
    },
    "TRANSFERS_TO": {
        "heads": ["FINANCIAL_ACCOUNT"],
        "tails": ["FINANCIAL_ACCOUNT"],
        "pairs": [("FINANCIAL_ACCOUNT", "FINANCIAL_ACCOUNT")],
    },
    "INSTANCE_OF": {
        "heads": ["ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE"],
        "tails": ["ORGANIZATION", "PERSON", "LOCATION", "INFRASTRUCTURE"],
        "pairs": [
            ("ORGANIZATION", "ORGANIZATION"), ("ORGANIZATION", "PERSON"), ("ORGANIZATION", "LOCATION"), ("ORGANIZATION", "INFRASTRUCTURE"),
            ("PERSON", "PERSON"), ("LOCATION", "LOCATION"), ("INFRASTRUCTURE", "INFRASTRUCTURE"),
        ],
    },
    "PRECEDES": {
        "heads": ["EVENT", "CAMPAIGN", "TECHNIQUE", "BEHAVIOR_PATTERN"],
        "tails": ["EVENT", "CAMPAIGN", "TECHNIQUE", "BEHAVIOR_PATTERN"],
        "pairs": [
            ("EVENT", "EVENT"), ("EVENT", "CAMPAIGN"), ("EVENT", "TECHNIQUE"), ("EVENT", "BEHAVIOR_PATTERN"),
            ("CAMPAIGN", "EVENT"), ("CAMPAIGN", "CAMPAIGN"), ("CAMPAIGN", "TECHNIQUE"), ("CAMPAIGN", "BEHAVIOR_PATTERN"),
            ("TECHNIQUE", "EVENT"), ("TECHNIQUE", "CAMPAIGN"), ("TECHNIQUE", "TECHNIQUE"), ("TECHNIQUE", "BEHAVIOR_PATTERN"),
            ("BEHAVIOR_PATTERN", "EVENT"), ("BEHAVIOR_PATTERN", "CAMPAIGN"), ("BEHAVIOR_PATTERN", "TECHNIQUE"), ("BEHAVIOR_PATTERN", "BEHAVIOR_PATTERN"),
        ],
    },
    "RELATED_TO": {
        "heads": [],
        "tails": [],
        "pairs": [],
    },
}


SYSTEM_PROMPT = """你是一个威胁情报分析助手，负责从安全报告中提取威胁实体和关系。

## 任务

从给定的文本片段中识别所有威胁情报相关实体及其关系，输出严格 JSON 格式。

## 实体类型

从以下 17 种类型中选择最合适的：
- APT_GROUP: APT 组织 (如 APT28, Lazarus, Kimsuky)
- ORGANIZATION: 组织/机构 (如 CERT-UA, GRU, Mandiant, 政府机构)
- PERSON: 人员
- MALWARE: 恶意软件 (如 BEARDSHELL, X-Agent, WannaCry)
- TOOL: 工具/软件 (如 Signal, PowerShell, Cobalt Strike, Metasploit)
- CVE: 漏洞编号 (如 CVE-2020-35730)
- TECHNIQUE: 攻击技术 (如 鱼叉式钓鱼, XSS, SQL注入)
- INFRASTRUCTURE: 基础设施 (域名, IP, C2服务器)
- LOCATION: 地理位置
- FINANCIAL_ACCOUNT: 金融账户/钱包
- COUNTRY: 国家 (如 Russia, Ukraine, North Korea)
- REGION: 地区
- INDUSTRY: 行业 (如 政府, 金融, 能源)
- TIME: 时间点
- EVENT: 事件
- CAMPAIGN: 攻击活动/行动
- BEHAVIOR_PATTERN: 行为模式

## 关系类型

| 关系 | 含义 | 主体类型 | 客体类型 |
| USES | 使用 | APT_GROUP/CAMPAIGN/ORGANIZATION/COUNTRY | MALWARE/TOOL/TECHNIQUE/INFRASTRUCTURE |
| TARGETS | 攻击目标 | APT_GROUP/CAMPAIGN/MALWARE | COUNTRY/INDUSTRY/ORGANIZATION/LOCATION |
| EXPLOITS | 利用漏洞 | APT_GROUP/CAMPAIGN/MALWARE/TOOL | CVE |
| ATTRIBUTED_TO | 归因于 | APT_GROUP/CAMPAIGN/MALWARE | COUNTRY/ORGANIZATION |
| AFFILIATED_WITH | 关联/合作 | APT_GROUP/ORGANIZATION | APT_GROUP/ORGANIZATION/COUNTRY |
| LOCATED_IN | 位于 | ORGANIZATION/PERSON/LOCATION | COUNTRY/REGION/LOCATION |
| DISCOVERED_BY | 被发现/披露 | MALWARE/CVE/TOOL/CAMPAIGN | ORGANIZATION/PERSON |
| HAPPENED_AT | 发生于 | EVENT/CAMPAIGN | TIME |
| RELATED_TO | 通用关联 | 任意 | 任意 |

## 规则

1. evidence_text 必须从原文逐字复制，不要改写
2. char_start/char_end 标注 evidence_text 在原文中的起止位置
3. 只抽取文中明确提及的实体，不要推测
4. 置信度 confidence 0-1，文中明确提及的给 0.85-0.95，推断的给 0.6-0.75
5. 不要编造关系，每个关系必须有原文证据支撑

## 输出格式

严格按以下 JSON 输出，不要输出其他内容：

```json
{
  "entities": [
    {
      "name": "实体名称",
      "type": "APT_GROUP",
      "aliases": ["别名1"],
      "description": "一句话描述",
      "mention_text": "文中出现的原文字段",
      "evidence_text": "包含该实体的原文证据段落",
      "char_start": 0,
      "char_end": 150,
      "confidence": 0.92
    }
  ],
  "relations": [
    {
      "head_name": "主体实体名称",
      "head_type": "APT_GROUP",
      "relation_type": "USES",
      "tail_name": "客体实体名称",
      "tail_type": "MALWARE",
      "evidence_text": "支持该关系的原文证据段落",
      "char_start": 0,
      "char_end": 150,
      "confidence": 0.88
    }
  ]
}
```"""

FEW_SHOT_EXAMPLE = """
## 示例

原文：
"The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities."

输出：
```json
{
  "entities": [
    {
      "name": "APT28",
      "type": "APT_GROUP",
      "aliases": [],
      "description": "俄罗斯关联的 APT 威胁组织",
      "mention_text": "APT28",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.95
    },
    {
      "name": "Russia",
      "type": "COUNTRY",
      "aliases": [],
      "description": "APT28 的归因国家",
      "mention_text": "Russia-linked",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.94
    },
    {
      "name": "X-Agent",
      "type": "MALWARE",
      "aliases": [],
      "description": "APT28 使用的恶意软件",
      "mention_text": "X-Agent malware",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.92
    },
    {
      "name": "Ukrainian government entities",
      "type": "ORGANIZATION",
      "aliases": [],
      "description": "APT28 的攻击目标",
      "mention_text": "Ukrainian government entities",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.91
    }
  ],
  "relations": [
    {
      "head_name": "APT28",
      "head_type": "APT_GROUP",
      "relation_type": "ATTRIBUTED_TO",
      "tail_name": "Russia",
      "tail_type": "COUNTRY",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.93
    },
    {
      "head_name": "APT28",
      "head_type": "APT_GROUP",
      "relation_type": "USES",
      "tail_name": "X-Agent",
      "tail_type": "MALWARE",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.92
    },
    {
      "head_name": "APT28",
      "head_type": "APT_GROUP",
      "relation_type": "TARGETS",
      "tail_name": "Ukrainian government entities",
      "tail_type": "ORGANIZATION",
      "evidence_text": "The Russia-linked APT28 group has been using X-Agent malware to target Ukrainian government entities.",
      "char_start": 0,
      "char_end": 106,
      "confidence": 0.92
    }
  ]
}
```"""


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    path = schema_path or DEFAULT_EXTRACTION_SCHEMA_PATH
    return json.loads(Path(path).read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def generate_run_id(doc_id: str, prompt_version: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"extract_{doc_id}_{prompt_version}_{ts}"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_entity(entity: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not entity.get("name", "").strip():
        errors.append("name 不能为空")
    if entity.get("type") not in ENTITY_TYPES:
        errors.append(f"未知实体类型: {entity.get('type')}")
    if not entity.get("evidence_text", "").strip():
        errors.append("evidence_text 不能为空")
    confidence = entity.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        errors.append(f"confidence 不在 [0,1] 范围内: {confidence}")
    return errors


def validate_relation(
    relation: dict[str, Any],
    known_entities: set[tuple[str, str]],
) -> list[str]:
    errors: list[str] = []
    relation_type = relation.get("relation_type", "")
    rule = ALLOWED_RELATIONS.get(relation_type)
    if rule is None:
        return [f"未知关系类型: {relation_type}"]
    if relation_type != "RELATED_TO":
        head_type = relation.get("head_type", "")
        tail_type = relation.get("tail_type", "")
        if rule.get("heads") and head_type not in rule["heads"]:
            errors.append(f"{relation_type} 不允许 head_type={head_type}")
        if rule.get("tails") and tail_type not in rule["tails"]:
            errors.append(f"{relation_type} 不允许 tail_type={tail_type}")
        if rule.get("pairs") and (head_type, tail_type) not in rule["pairs"]:
            errors.append(f"不允许组合 ({head_type},{relation_type},{tail_type})")
    head_key = (relation.get("head_name", ""), relation.get("head_type", ""))
    tail_key = (relation.get("tail_name", ""), relation.get("tail_type", ""))
    if head_key not in known_entities:
        errors.append(f"head ({head_key[0]}, {head_key[1]}) 不在候选实体中")
    if tail_key not in known_entities:
        errors.append(f"tail ({tail_key[0]}, {tail_key[1]}) 不在候选实体中")
    if not relation.get("evidence_text", "").strip():
        errors.append("evidence_text 不能为空")
    confidence = relation.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        errors.append(f"confidence 不在 [0,1] 范围内: {confidence}")
    return errors


def parse_llm_response(response_text: str, chunk_id: str, clean_text: str) -> dict[str, Any]:
    """从 LLM 返回的文本中解析出实体和关系列表。"""
    # 提取 JSON 块
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        raise ValueError("LLM 返回内容中未找到合法 JSON")

    data = json.loads(json_match.group(0))
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    known_entities: set[tuple[str, str]] = set()
    processed_entities: list[dict[str, Any]] = []
    for ent in entities:
        e = {
            "name": ent.get("name", ""),
            "type": ent.get("type", ""),
            "aliases": ent.get("aliases", []),
            "description": ent.get("description", ""),
            "mention_text": ent.get("mention_text", ""),
            "evidence_text": ent.get("evidence_text", ""),
            "char_start": _find_char_start(clean_text, ent.get("evidence_text", "")),
            "char_end": _find_char_end(clean_text, ent.get("evidence_text", "")),
            "confidence": ent.get("confidence", 0.5),
            "candidate_status": "candidate",
            "validation_status": "unchecked",
            "validation_errors": [],
        }
        errors = validate_entity(e)
        e["validation_status"] = "valid" if not errors else "invalid"
        e["validation_errors"] = errors
        processed_entities.append(e)
        known_entities.add((e["name"], e["type"]))
        for alias in e["aliases"]:
            known_entities.add((alias, e["type"]))

    processed_relations: list[dict[str, Any]] = []
    for rel in relations:
        r = {
            "head_name": rel.get("head_name", ""),
            "head_type": rel.get("head_type", ""),
            "relation_type": rel.get("relation_type", ""),
            "tail_name": rel.get("tail_name", ""),
            "tail_type": rel.get("tail_type", ""),
            "evidence_text": rel.get("evidence_text", ""),
            "char_start": _find_char_start(clean_text, rel.get("evidence_text", "")),
            "char_end": _find_char_end(clean_text, rel.get("evidence_text", "")),
            "confidence": rel.get("confidence", 0.5),
            "candidate_status": "candidate",
            "validation_status": "unchecked",
            "validation_errors": [],
        }
        errors = validate_relation(r, known_entities)
        r["validation_status"] = "valid" if not errors else "invalid"
        r["validation_errors"] = errors
        processed_relations.append(r)

    return {"entities": processed_entities, "relations": processed_relations}


def _find_char_start(clean_text: str, evidence: str) -> int | None:
    if not evidence:
        return None
    idx = clean_text.find(evidence)
    return idx if idx >= 0 else None


def _find_char_end(clean_text: str, evidence: str) -> int | None:
    if not evidence:
        return None
    idx = clean_text.find(evidence)
    return idx + len(evidence) if idx >= 0 else None


class LLMExtractionService:
    """调用 OpenAI-compatible API 进行威胁情报实体关系抽取。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        self.max_retries = max_retries

    def extract(self, document: dict[str, Any], prompt_version: str = "extract-v1") -> dict[str, Any]:
        """从单篇文档中抽取实体和关系，返回 extraction_result。"""
        doc_id = document["doc_id"]
        clean_text = document.get("clean_text", "") or document.get("raw_text", "")
        run_id = generate_run_id(doc_id, prompt_version)

        # 单 chunk 模式：整篇文档作为一个 chunk
        chunk_id = f"{doc_id}_c001"

        user_prompt = f"## 文档原文\n\n{clean_text}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + FEW_SHOT_EXAMPLE},
            {"role": "user", "content": user_prompt},
        ]

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response_text = self._call_api(messages)
                chunk_result = parse_llm_response(response_text, chunk_id, clean_text)
                break
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    continue
                raise RuntimeError(
                    f"LLM 抽取失败 (已重试 {self.max_retries} 次): {last_error}"
                ) from last_error

        result = {
            "schema_version": "1.0",
            "run_id": run_id,
            "doc_id": doc_id,
            "model_name": self.model,
            "prompt_version": prompt_version,
            "chunks": [
                {
                    "chunk_id": chunk_id,
                    "entities": chunk_result["entities"],
                    "relations": chunk_result["relations"],
                }
            ],
        }

        self._validate_schema(result)
        return result

    def _call_api(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return content

    def _validate_schema(self, result: dict[str, Any]) -> None:
        schema = load_schema()
        try:
            jsonschema.validate(result, schema)
        except SchemaValidationError as exc:
            raise ValueError(f"抽取结果不符合 schema: {exc.message}") from exc

    def save_result(self, result: dict[str, Any], output_dir: str | Path = "data/extracted") -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        filepath = out / f"{result['run_id']}.json"
        filepath.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return filepath
