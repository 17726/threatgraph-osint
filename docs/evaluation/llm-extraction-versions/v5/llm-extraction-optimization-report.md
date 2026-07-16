# LLM 抽取优化报告

每次优化对应一个新的 prompt version，输出文件名自动携带版本号。

---

## extract-v1 → extract-v2 (2026-07-14)

**基线评测问题 (apt28_080, deepseek-v4-flash):**
- entity F1=0.415, relation F1=0.267
- DISCOVERED_BY 假阳性 5 条
- CONTROLS 假阳性 3 条
- TOOL recall=0.11, TECHNIQUE recall=0.20（漏扫文档后半部分）

**优化内容：**
1. `docs/prompts/extract-v2.md` — 新增规则 17-22 + few-shot 示例 + 常见错误
2. `llm_service.py` build_user_prompt — 新增 4 条"重要提醒"
3. 默认版本切换: extract-v1 → extract-v2

---

## extract-v2 → extract-v3 (2026-07-14)

**v2 评测结果 (apt28_080):**
- entity F1=0.643 (+55%), relation F1=0.481 (+80%)
- DISCOVERED_BY/CONTROLS 假阳性归零
- TOOL recall 0.11→0.89
- 新问题: MALWARE USES TOOL/TECHNIQUE/INFRASTRUCTURE（矩阵不允许）
- 新问题: evidence_text 被模型改写
- 新问题: AFFILIATED_WITH 误触（安全厂商）
- TIME recall=0, ORGANIZATION recall=0.167

**优化内容：**
1. `docs/prompts/extract-v3.md` — 新增规则 23-26 + 3 条反例
2. `llm_service.py` build_user_prompt — 扩充到 7 条
3. 默认版本切换: extract-v2 → extract-v3

---

## extract-v3 → extract-v4 (2026-07-14) — 已废弃回退

**v3 三篇评测结果:**
- apt28_080: entity F1=0.764, relation F1=0.732 (precision 双 0.9+)
- kimsuky_060: entity F1=0.794, relation F1=0.314 (11/23 条关系被拒)
- lazarus_091: entity F1=0.583, relation F1=0.649 (35 个 FP 实体)

**跨文章共性问题:**
- evidence_text 被模型改写/拼错是最大被拒原因
- PART_OF 矩阵违反: APT_GROUP PART_OF APT_GROUP/ORGANIZATION
- ATTRIBUTED_TO 矩阵违反: CAMPAIGN/MALWARE ATTRIBUTED_TO APT_GROUP
- lazarus: 良性连通性检测域名被抽成 INFRASTRUCTURE（10 FP）
- lazarus: SHA256 哈希值被抽成 MALWARE 实体（4 FP）
- 级联失败: 实体 evidence_text 被拒 → 所有引用该实体的关系也被拒

**优化内容：**
1. `docs/prompts/extract-v4.md` — 新增规则 26-30 + 4 条反例
2. `llm_service.py` build_user_prompt — 扩充到 11 条
3. 默认版本切换: extract-v3 → extract-v4

**回归原因：** 规则过多，模型"过度纠正"。apt28 F1 0.764→0.696，kimsuky relation F1 0.314→0.125。**全部回退，改用代码层修复。**

---

## extract-v5 (2026-07-15) — 保持 v3 prompt，代码层修复

**v4 回归后策略调整：** v4 新增 4 条规则导致模型"过度纠正"和规则间干扰。决定回退到 v3 prompt + 在代码层修复。

### 代码修改

**1. `scripts/validate_extraction_result.py` — ALLOWED_RELATIONS 矩阵扩展**
- PART_OF: heads 新增 APT_GROUP，pairs 新增 (APT_GROUP→APT_GROUP) 和 (APT_GROUP→ORGANIZATION)
- ATTRIBUTED_TO: tails 新增 APT_GROUP（允许 CAMPAIGN/MALWARE ATTRIBUTED_TO APT_GROUP）

**2. `backend/app/services/llm_service.py` — build_user_prompt 回退**
- 移除 v4 新增的 4 条提醒行，从 11 条缩减回 7 条

**3. `backend/app/services/llm_service.py` — parse_llm_response_with_audit 代码级过滤器**
- SHA256/MD5/SHA1 哈希检测: `^[A-Fa-f0-9]{32,64}$` 匹配的 MALWARE 实体自动拒绝
- 良性连通性域名过滤: INFRASTRUCTURE 实体名匹配已知公共服务域名自动拒绝

**4. `backend/app/services/llm_service.py` — _find_text_span 模糊匹配 + evidence_text 自动纠正**
- 三层策略：精确匹配 → whitespace 容错匹配（IGNORECASE）→ None
- 匹配成功后自动纠正 evidence_text 为原文实际片段
- 解决 "Kimusky, also known..." vs "Kimusky\n, also known..." 的换行符差异导致的级联断裂

**核心思路：** 让 prompt 做语义理解，让代码做规则校验和过滤。

### 最终效果

| 文章 | entity F1 | relation F1 |
|---|---|---|
| apt28_080 | 0.750 | 0.773 |
| kimsuky_060 | 0.831 | 0.538 |
| lazarus_091 | 0.644 | 0.703 |
