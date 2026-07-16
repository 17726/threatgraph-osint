"""LLM 驱动的智能报告生成服务。

从 SQLite 图谱读取指定组织的全量数据，构建 prompt 发给 DeepSeek，
让大模型生成 5 个章节的自然语言分析报告。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_DB_PATH = Path("data/threatgraph_osint.db")

SECTION_TYPES = [
    ("profile", "组织画像"),
    ("behavior_patterns", "行为模式总结"),
    ("network", "关联网络分析"),
    ("timeline", "时间线"),
    ("threat_assessment", "威胁评估与预警建议"),
]

SECTION_PROMPTS = {
    "profile": (
        "请分析该组织的**组织画像**，包括：正式名称、所有已知别名、组织类型、"
        "活跃时间范围（首次发现和最近活跃）、主要活跃地区、目标行业、描述总结。"
        "基于下方图谱数据给出客观描述，注明信息来源数量。"
    ),
    "behavior_patterns": (
        "请总结该组织的**行为模式**，包括：使用的攻击技术和工具（TTPs）、"
        "关系图谱中 USES/TARGETS/EXPLOITS 等行为关系、攻击阶段分布。"
        "如果有 MITRE ATT&CK 映射信息，请一并说明。按攻击阶段组织内容。"
    ),
    "network": (
        "请分析该组织的**关联网络**，包括：与哪些其他实体存在关联、关联类型分布、"
        "主要关联对象及其角色。说明该组织在网络中的位置和关系模式。"
    ),
    "timeline": (
        "请整理该组织的**关键时间线**，包括：首次发现时间、各阶段活跃时间、"
        "关键事件的时间序列。按时间先后顺序组织。"
    ),
    "threat_assessment": (
        "请给出**威胁评估与预警建议**，包括：综合威胁等级评估、"
        "风险评分（0-100）、评估依据、具体的可操作的预警建议。"
        "威胁等级参考 CVSS 3.1 规范：CRITICAL（≥75）、HIGH（≥60）、MEDIUM（≥40）、LOW（<40）。"
        "基于图谱数据量、关系复杂度和证据丰富度给出客观评估。"
        "评分要考虑：实体置信度、来源数量、关系类型多样性、时间跨度、证据充分性。"
    ),
}

REPORT_PROMPT_TEMPLATE = """你是一名专业的网络安全威胁情报分析师。请根据下面提供的知识图谱数据，为组织 {target_group} 撰写一份高质量的威胁情报分析报告。

## 图谱数据概览

### 目标组织基本信息
- 名称：{target_name}
- 类型：{target_type}
- 别名：{aliases}
- 描述：{description}
- 置信度：{confidence}
- 来源数：{source_count}
- 首次发现：{first_seen}
- 最近活跃：{last_seen}

### 实体列表（共 {entity_count} 个）
{entity_list}

### 关系列表（共 {relation_count} 条）
{relation_list}

### 证据样本（共 {evidence_count} 条，展示前 20 条）
{evidence_samples}

### 行为模式（如有）
{behavior_patterns}

### MITRE ATT&CK 映射（如有）
{mitre_mappings}

## 报告要求

请按以下 5 个章节撰写报告，每个章节用 "## 章节类型" 标题开头：

1. ## profile — {profile_prompt}
2. ## behavior_patterns — {behavior_prompt}
3. ## network — {network_prompt}
4. ## timeline — {timeline_prompt}
5. ## threat_assessment — {assessment_prompt}

格式要求：
- 使用中文撰写，专业客观的语气
- 正文使用 markdown 格式
- 每个章节以 "## 章节类型" 开头
- 章节之间用 "---" 分隔
- 基于图谱数据撰写，不要添加没有数据支持的断言
- 不要编造数据"""


class LLMReportService:
    """LLM 驱动的智能报告生成服务。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float = 0.7,
        db_path: Path | None = None,
    ):
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)
        self.timeout = timeout or float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        self.temperature = temperature
        self.db_path = db_path or DEFAULT_DB_PATH
        self.last_response_text: str | None = None

    def _chat(self, messages: list[dict[str, str]]) -> str:
        """调用 LLM chat completion API。"""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 8192,
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=body)

        if response.status_code != 200:
            raise RuntimeError(
                f"LLM API 返回 {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("LLM API 返回空 choices")

        content = choices[0].get("message", {}).get("content", "")
        self.last_response_text = content
        return content

    def _build_prompt(self, target_group: str) -> str:
        """从 SQLite 读取图谱数据并构建 prompt。"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        entity_id = f"apt_group:{target_group.lower()}"

        # 目标组织
        target = conn.execute(
            "SELECT * FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()

        if target is None:
            # 尝试按名称匹配
            target = conn.execute(
                "SELECT * FROM entities WHERE name = ? AND type = 'APT_GROUP'",
                (target_group,),
            ).fetchone()

        if target is None:
            # 尝试按别名匹配（应对实体合并后 entity_id 变更）
            target = conn.execute(
                "SELECT * FROM entities WHERE aliases_json LIKE ? AND type = 'APT_GROUP'",
                (f"%{target_group}%",),
            ).fetchone()

        if target is None:
            conn.close()
            raise ValueError(f"图谱中未找到目标组织: {target_group}")

        target_name = target["name"]
        target_type = target["type"]
        aliases = json.loads(target["aliases_json"]) if target["aliases_json"] else []
        aliases_str = "、".join(aliases) if aliases else "无"
        description = target["description"] or "暂无"
        confidence = target["confidence"]
        source_count = target["source_count"]
        first_seen = target["first_seen"] or "未知"
        last_seen = target["last_seen"] or "未知"

        # 所有实体（排除自身）
        entities = conn.execute(
            """
            SELECT name, type, COALESCE(aliases_json, '[]') AS aliases_json,
                   COALESCE(description, '') AS description, confidence
            FROM entities
            WHERE entity_id != ?
            ORDER BY type, name
            """,
            (target["entity_id"],),
        ).fetchall()

        entity_lines = []
        for e in entities:
            ea = json.loads(e["aliases_json"]) if e["aliases_json"] else []
            ea_str = f" ({'、'.join(ea)})" if ea else ""
            desc = e["description"][:80] if e["description"] else ""
            entity_lines.append(
                f"- {e['name']}{ea_str} | type={e['type']} | confidence={e['confidence']} | {desc}"
            )
        entity_list = "\n".join(entity_lines) if entity_lines else "无"

        # 关系
        relations = conn.execute(
            """
            SELECT r.relation_type, r.label, r.confidence, r.evidence_count,
                   e1.name AS source_name, e2.name AS target_name
            FROM relations r
            JOIN entities e1 ON r.source_entity_id = e1.entity_id
            JOIN entities e2 ON r.target_entity_id = e2.entity_id
            WHERE r.source_entity_id = ? OR r.target_entity_id = ?
            ORDER BY r.relation_type
            """,
            (target["entity_id"], target["entity_id"]),
        ).fetchall()

        relation_lines = []
        for r in relations:
            direction = "→" if r["source_name"] == target_name else "←"
            other = r["target_name"] if r["source_name"] == target_name else r["source_name"]
            relation_lines.append(
                f"- {r['relation_type']}（{r['label']}）{direction} {other} "
                f"| confidence={r['confidence']} | evidence_count={r['evidence_count']}"
            )
        relation_list = "\n".join(relation_lines) if relation_lines else "无"

        # 证据样本
        evidence = conn.execute(
            """
            SELECT evidence_id, source_name, evidence_text, published_at
            FROM evidence
            WHERE entity_id = ?
            ORDER BY published_at DESC
            LIMIT 20
            """,
            (target["entity_id"],),
        ).fetchall()

        evidence_lines = []
        for e in evidence:
            text = e["evidence_text"][:200] if e["evidence_text"] else ""
            evidence_lines.append(
                f"- [{e['evidence_id']}] {e['source_name']} | {e['published_at'] or '未知'} | {text}"
            )
        evidence_samples = "\n".join(evidence_lines) if evidence_lines else "无"
        evidence_count = conn.execute(
            "SELECT count(*) AS cnt FROM evidence WHERE entity_id = ?",
            (target["entity_id"],),
        ).fetchone()["cnt"]

        # 行为模式
        patterns = conn.execute(
            """
            SELECT stage, description, technique_ids_json, confidence
            FROM behavior_patterns
            WHERE target_group = ?
            ORDER BY stage
            """,
            (target_group,),
        ).fetchall()

        if patterns:
            pattern_lines = []
            for p in patterns:
                tids = json.loads(p["technique_ids_json"]) if p["technique_ids_json"] else []
                tech_str = f"（{', '.join(tids)}）" if tids else ""
                pattern_lines.append(
                    f"- stage={p['stage']}{tech_str}: {p['description']} (confidence={p['confidence']})"
                )
            behavior_patterns = "\n".join(pattern_lines)
        else:
            behavior_patterns = "无"

        # MITRE 映射
        mitre = conn.execute(
            """
            SELECT technique_id, technique_name, tactic, attack_stage
            FROM mitre_mappings
            WHERE target_group = ?
            ORDER BY attack_stage, technique_id
            """,
            (target_group,),
        ).fetchall()

        if mitre:
            mitre_lines = [
                f"- {m['technique_id']} {m['technique_name']} | tactic={m['tactic']} | stage={m['attack_stage']}"
                for m in mitre
            ]
            mitre_mappings = "\n".join(mitre_lines)
        else:
            mitre_mappings = "无"

        conn.close()

        return REPORT_PROMPT_TEMPLATE.format(
            target_group=target_group,
            target_name=target_name,
            target_type=target_type,
            aliases=aliases_str,
            description=description,
            confidence=confidence,
            source_count=source_count,
            first_seen=first_seen,
            last_seen=last_seen,
            entity_count=len(entities),
            entity_list=entity_list,
            relation_count=len(relations),
            relation_list=relation_list,
            evidence_count=evidence_count,
            evidence_samples=evidence_samples,
            behavior_patterns=behavior_patterns,
            mitre_mappings=mitre_mappings,
            profile_prompt=SECTION_PROMPTS["profile"],
            behavior_prompt=SECTION_PROMPTS["behavior_patterns"],
            network_prompt=SECTION_PROMPTS["network"],
            timeline_prompt=SECTION_PROMPTS["timeline"],
            assessment_prompt=SECTION_PROMPTS["threat_assessment"],
        )

    def _parse_sections(self, response_text: str) -> list[dict[str, Any]]:
        """从 LLM 响应中解析 5 个章节。"""
        sections = []
        prev_end = 0

        for section_type, section_title in SECTION_TYPES:
            # 查找 "## section_type" 或 "## 中文标题" 标记
            pattern = rf'^##\s*{re.escape(section_type)}\s*$'
            match = re.search(pattern, response_text, re.MULTILINE)

            if not match:
                # 尝试匹配中文标题
                pattern_zh = rf'^##\s*{re.escape(section_title)}\s*$'
                match = re.search(pattern_zh, response_text, re.MULTILINE)

            if not match:
                # 尝试部分匹配
                pattern_partial = rf'^##\s*.*?{re.escape(section_type[:8])}.*?$'
                match = re.search(pattern_partial, response_text, re.MULTILINE)

            content_start = match.end() if match else prev_end
            content_end = len(response_text)

            # 找下一个章节的起始位置
            remaining = response_text[content_start:]
            next_section_pattern = r'^##\s+'
            next_match = re.search(next_section_pattern, remaining, re.MULTILINE)
            if next_match and next_match.start() > 0:
                content_end = content_start + next_match.start()

            section_markdown = response_text[content_start:content_end].strip()
            # 去掉分隔符
            section_markdown = re.sub(r'^---+', '', section_markdown).strip()
            # 去掉可能的标题重复
            section_markdown = re.sub(r'^#\s+.*$', '', section_markdown, count=1).strip()

            sections.append({
                "section_id": section_type,
                "section_type": section_type,
                "title": section_title,
                "markdown": section_markdown or f"暂无{section_title}数据",
                "evidence_ids": [],
                "analysis_refs": [],
                "graph_refs": {"node_ids": [], "edge_ids": []},
                "sort_order": len(sections),
            })
            prev_end = content_end

        # 如果解析的章节少于 5 个，补全
        while len(sections) < len(SECTION_TYPES):
            st, st_title = SECTION_TYPES[len(sections)]
            sections.append({
                "section_id": st,
                "section_type": st,
                "title": st_title,
                "markdown": f"暂无{st_title}数据",
                "evidence_ids": [],
                "analysis_refs": [],
                "graph_refs": {"node_ids": [], "edge_ids": []},
                "sort_order": len(sections),
            })

        return sections[:5]

    def generate(
        self,
        target_group: str,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """生成智能报告。

        Args:
            target_group: 目标组织名称（如 APT28）
            temperature: 生成多样性，默认 0.7

        Returns:
            {"sections": [...], "markdown": str}
        """
        if temperature is not None:
            self.temperature = temperature

        prompt = self._build_prompt(target_group)

        system_msg = {
            "role": "system",
            "content": (
                "你是一名专业的网络安全威胁情报分析师。"
                "你擅长基于知识图谱数据撰写高质量的威胁情报分析报告。"
                "你的报告必须基于数据，不编造，不夸大。"
                "使用中文撰写，专业客观的语气。"
                "每个章节以 '## 章节类型' 开头。"
            ),
        }
        user_msg = {"role": "user", "content": prompt}

        response_text = self._chat([system_msg, user_msg])

        sections = self._parse_sections(response_text)

        section_markdowns = [s["markdown"] for s in sections]
        combined_markdown = "\n\n---\n\n".join(section_markdowns)
        full_markdown = (
            f"# {target_group} 威胁情报分析报告\n\n"
            f"> 生成时间：{datetime.now(UTC).isoformat()}\n"
            f"> 模型：{self.model}\n\n"
            f"{combined_markdown}"
        )

        return {
            "sections": sections,
            "markdown": full_markdown,
        }


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
