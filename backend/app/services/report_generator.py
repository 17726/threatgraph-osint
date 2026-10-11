"""智能报告生成服务。

优先使用 LLM 驱动生成，LLM 不可用时降级到规则模板。
"""

from __future__ import annotations

from typing import Any

from backend.app.services.llm_report_service import LLMReportService


def generate_intelligent_report(
    connection: Any,
    target_group: str,
    target_entity_id: str,
    llm_service: LLMReportService | None = None,
) -> dict[str, Any]:
    """生成智能分析报告。

    优先调用 LLM 生成，降级时使用规则模板。
    """
    if llm_service is None:
        llm_service = LLMReportService()

    try:
        result = llm_service.generate(target_group)
        result["_llm_generated"] = True
        return result
    except Exception:
        result = _fallback_generate(connection, target_group, target_entity_id)
        result["_llm_generated"] = False
        return result


def _fallback_generate(
    connection: Any,
    target_group: str,
    target_entity_id: str,
) -> dict[str, Any]:
    """规则模板降级方案。"""
    from datetime import UTC, datetime

    sections = [
        _fallback_profile(connection, target_entity_id),
        _fallback_behavior_patterns(connection, target_group),
        _fallback_network(connection, target_group, target_entity_id),
        _fallback_timeline(connection, target_group, target_entity_id),
        _fallback_threat_assessment(connection, target_group),
        _fallback_attack_chain(connection, target_group, target_entity_id),
    ]

    section_markdowns = [s["markdown"] for s in sections]
    combined_markdown = "\n\n---\n\n".join(section_markdowns)

    return {
        "sections": sections,
        "markdown": f"# {target_group} 威胁情报分析报告\n\n> 生成时间：{datetime.now(UTC).isoformat()}\n> 模式：规则模板降级\n\n{combined_markdown}",
    }


def _fallback_profile(connection: Any, entity_id: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT name, type, aliases_json, description, confidence,
               source_count, first_seen, last_seen, tags_json
        FROM entities WHERE entity_id = ?
        """,
        (entity_id,),
    ).fetchone()
    if row is None:
        return _empty_section("profile", "组织画像")

    import json
    name = row["name"]
    aliases = json.loads(row["aliases_json"])
    alias_str = "、".join(aliases) if aliases else "无已知别名"
    tags = json.loads(row["tags_json"])
    tag_str = "、".join(tags) if tags else "无标签"

    markdown = (
        f"### 基本信息\n\n"
        f"- **名称**：{name}\n"
        f"- **别名**：{alias_str}\n"
        f"- **类型**：{row['type']}\n"
        f"- **描述**：{row['description'] or '暂无描述'}\n"
        f"- **置信度**：{row['confidence']}\n"
        f"- **来源数**：{row['source_count']}\n"
        f"- **首次发现**：{row['first_seen'] or '未知'}\n"
        f"- **最近活跃**：{row['last_seen'] or '未知'}\n"
        f"- **标签**：{tag_str}\n"
    )
    return _section("profile", "组织画像", markdown, sort_order=0)


def _fallback_behavior_patterns(connection: Any, target_group: str) -> dict[str, Any]:
    import json
    patterns = connection.execute(
        "SELECT stage, description, technique_ids_json, confidence "
        "FROM behavior_patterns WHERE target_group = ? ORDER BY stage",
        (target_group,),
    ).fetchall()

    mitre_mappings = connection.execute(
        "SELECT technique_id, technique_name, tactic, attack_stage "
        "FROM mitre_mappings WHERE target_group = ? ORDER BY attack_stage, technique_id",
        (target_group,),
    ).fetchall()

    lines = []
    if patterns:
        lines.append("#### 攻击行为模式\n")
        for row in patterns:
            tids = json.loads(row["technique_ids_json"]) if row["technique_ids_json"] else []
            tech_str = f"（相关技术：{', '.join(tids)}）" if tids else ""
            lines.append(f"- **{row['stage']}**{tech_str}：{row['description']}")

    if mitre_mappings:
        lines.append("\n#### MITRE ATT&CK 映射\n")
        lines.append("| 技术编号 | 技术名称 | 战术阶段 | 攻击阶段 |\n| --- | --- | --- | --- |\n")
        for row in mitre_mappings:
            lines.append(f"| {row['technique_id']} | {row['technique_name']} | {row['tactic']} | {row['attack_stage']} |\n")

    if not patterns and not mitre_mappings:
        lines.append("暂无可用的行为模式数据。")

    return _section("behavior_patterns", "行为模式总结", "".join(lines), sort_order=1)


def _fallback_network(connection: Any, target_group: str, entity_id: str) -> dict[str, Any]:
    relations = connection.execute(
        """
        SELECT r.relation_id, r.relation_type, r.label, r.confidence,
               r.source_entity_id, r.target_entity_id,
               e1.name AS source_name, e1.type AS source_type,
               e2.name AS target_name, e2.type AS target_type
        FROM relations r
        JOIN entities e1 ON r.source_entity_id = e1.entity_id
        JOIN entities e2 ON r.target_entity_id = e2.entity_id
        WHERE r.source_entity_id = ? OR r.target_entity_id = ?
        ORDER BY r.relation_type
        """,
        (entity_id, entity_id),
    ).fetchall()

    if not relations:
        return _section("network", "关联网络分析", "暂无可用的关联网络数据。", sort_order=2)

    node_ids: set[str] = {r["source_entity_id"] for r in relations} | {r["target_entity_id"] for r in relations}
    related_count = len(node_ids) - 1

    lines = [f"该组织在图谱中与 **{related_count}** 个实体存在 **{len(relations)}** 条关系。\n"]
    lines.extend([f"- **{r['relation_type']}**（{r['label']}）：{r['source_name']} → {r['target_name']}，置信度 {r['confidence']}\n" for r in relations])

    return _section("network", "关联网络分析", "".join(lines), sort_order=2,
                     graph_refs={"node_ids": list(node_ids), "edge_ids": [r["relation_id"] for r in relations]})


def _fallback_timeline(connection: Any, target_group: str, entity_id: str) -> dict[str, Any]:
    items = []

    entity = connection.execute("SELECT name, first_seen, last_seen FROM entities WHERE entity_id = ?", (entity_id,)).fetchone()
    if entity and entity["first_seen"]:
        items.append({"time": entity["first_seen"], "event": f"{entity['name']} 首次被观察到", "type": "实体发现"})
    if entity and entity["last_seen"] and entity["last_seen"] != entity["first_seen"]:
        items.append({"time": entity["last_seen"], "event": f"{entity['name']} 最近活跃时间", "type": "实体活跃"})

    evidence_rows = connection.execute(
        "SELECT published_at, source_name FROM evidence WHERE entity_id = ? AND published_at IS NOT NULL ORDER BY published_at",
        (entity_id,),
    ).fetchall()
    for row in evidence_rows:
        items.append({"time": row["published_at"], "event": f"来源 {row['source_name']} 发布相关报告", "type": "来源发布"})

    items.sort(key=lambda x: x["time"])

    if not items:
        return _section("timeline", "时间线", "暂无可用的时间线数据。", sort_order=3)

    lines = ["| 时间 | 事件 | 类型 |\n| --- | --- | --- |\n"]
    lines.extend([f"| {item['time']} | {item['event']} | {item['type']} |\n" for item in items])
    return _section("timeline", "时间线", "".join(lines), sort_order=3)


def _fallback_threat_assessment(connection: Any, target_group: str) -> dict[str, Any]:
    import json
    entity_id = f"apt_group:{target_group.lower()}"

    try:
        assessment = connection.execute(
            "SELECT risk_level, risk_score, rationale, recommendations_json "
            "FROM threat_assessments WHERE target_group = ? ORDER BY created_at DESC LIMIT 1",
            (target_group,),
        ).fetchone()
    except Exception:
        assessment = None

    if assessment:
        recs = json.loads(assessment["recommendations_json"])
        lines = [f"**威胁等级**：{assessment['risk_level']}\n\n",
                 f"**风险分数**：{assessment['risk_score']}/100\n\n",
                 f"**评估依据**：{assessment['rationale']}\n\n"]
        if recs:
            lines.append("#### 预警建议\n\n")
            lines.extend([f"{i}. {rec}\n" for i, rec in enumerate(recs, 1)])
        return _section("threat_assessment", "威胁评估与预警建议", "".join(lines), sort_order=4)

    entity = connection.execute("SELECT name, source_count, confidence FROM entities WHERE entity_id = ?", (entity_id,)).fetchone()
    rel_count = connection.execute(
        "SELECT count(*) AS cnt FROM relations WHERE source_entity_id = ? OR target_entity_id = ?",
        (entity_id, entity_id),
    ).fetchone()[0]
    ev_count = connection.execute("SELECT count(*) AS cnt FROM evidence WHERE entity_id = ?", (entity_id,)).fetchone()[0]

    risk_score = 50
    if entity:
        if entity["confidence"] and entity["confidence"] > 0.8:
            risk_score += 15
        if entity["source_count"] and entity["source_count"] >= 3:
            risk_score += 10
    if rel_count > 5:
        risk_score += 10
    if ev_count > 5:
        risk_score += 5

    # 参考 CVSS 3.1 规范进行等级划分
    risk_level = "MEDIUM"
    if risk_score >= 75:
        risk_level = "CRITICAL"
    elif risk_score >= 60:
        risk_level = "HIGH"
    elif risk_score < 40:
        risk_level = "LOW"

    name = entity["name"] if entity else target_group
    markdown = (
        f"**威胁等级**：{risk_level}\n\n"
        f"**风险分数**：{risk_score}/100\n\n"
        f"**评估依据**：{name} 在知识图谱中包含 {rel_count} 条关系、{ev_count} 条证据。\n\n"
        "#### 预警建议\n\n"
        "1. 持续监控该组织的攻击基础设施和工具集变化\n"
        "2. 建立针对该组织 TTPs 的检测规则和告警策略\n"
        "3. 关注该组织目标行业和地区的安全态势\n"
        "4. 定期更新威胁情报库，保持 IOC 清单的时效性\n"
    )
    return _section("threat_assessment", "威胁评估与预警建议", markdown, sort_order=4)


def _fallback_attack_chain(connection: Any, target_group: str, entity_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT r.relation_id, r.relation_type, r.label, r.confidence,
               r.source_entity_id, r.target_entity_id,
               e1.name AS source_name, e1.type AS source_type,
               e2.name AS target_name, e2.type AS target_type,
               r.first_seen, r.last_seen
        FROM relations r
        JOIN entities e1 ON e1.entity_id = r.source_entity_id
        JOIN entities e2 ON e2.entity_id = r.target_entity_id
        WHERE r.source_entity_id = ? OR r.target_entity_id = ?
        ORDER BY COALESCE(r.first_seen, ''), r.relation_id
        """,
        (entity_id, entity_id),
    ).fetchall()
    if not rows:
        return _section("attack_chain", "攻击链分析", "暂无足够的图谱关系形成完整攻击链。", sort_order=5)

    grouped: dict[tuple[str, str], dict[str, list[str]]] = {}
    node_ids: set[str] = set()
    edge_ids: list[str] = []
    for row in rows:
        time_text = row["first_seen"] or row["last_seen"] or "未知"
        key = (time_text, row["source_name"])
        event = grouped.setdefault(
            key, {"vulnerabilities": [], "tools": [], "techniques": [], "targets": [], "other": [], "evidence": []}
        )
        node_ids.update((row["source_entity_id"], row["target_entity_id"]))
        edge_ids.append(row["relation_id"])
        value = row["target_name"]
        if row["target_type"] == "CVE":
            bucket = "vulnerabilities"
        elif row["target_type"] in {"TOOL", "MALWARE"}:
            bucket = "tools"
        elif row["relation_type"] in {"TARGETS", "TARGETED_BY"}:
            bucket = "targets"
        elif row["relation_type"] in {"USES", "EXPLOITS"}:
            bucket = "techniques"
        else:
            bucket = "other"
        if value not in event[bucket]:
            event[bucket].append(value)
        for evidence_row in connection.execute(
            "SELECT evidence_id FROM evidence WHERE relation_id = ?", (row["relation_id"],)
        ).fetchall():
            if evidence_row["evidence_id"] not in event["evidence"]:
                event["evidence"].append(evidence_row["evidence_id"])

    lines = ["#### 攻击链叙事总览\n\n"]
    for (time_text, source), event in sorted(grouped.items()):
        lines.append(
            f"- **{time_text}**：{source} 利用 **{'、'.join(event['vulnerabilities']) or '未知'}**，"
            f"通过 **{'、'.join(event['tools']) or '未知'}**，使用或关联技术 **{'、'.join(event['techniques']) or '未知'}**，"
            f"目标为 **{'、'.join(event['targets']) or '未知'}**。\n"
        )
    return _section(
        "attack_chain", "攻击链分析", "".join(lines), sort_order=5,
        graph_refs={"node_ids": list(node_ids), "edge_ids": edge_ids},
    )


def _section(section_type: str, title: str, markdown: str, sort_order: int = 0,
             evidence_ids: list[str] | None = None, analysis_refs: list[str] | None = None,
             graph_refs: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "section_id": section_type,
        "section_type": section_type,
        "title": title,
        "markdown": markdown,
        "evidence_ids": evidence_ids or [],
        "analysis_refs": analysis_refs or [],
        "graph_refs": graph_refs or {"node_ids": [], "edge_ids": []},
        "sort_order": sort_order,
    }


def _empty_section(section_type: str, title: str) -> dict[str, Any]:
    return _section(section_type, title, f"暂无{title}数据。", sort_order=0)
