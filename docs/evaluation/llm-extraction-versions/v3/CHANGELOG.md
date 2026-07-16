# extract-v2 → extract-v3

## 优化内容

### 系统提示词 (extract-v3.md)
- 规则 23: 工具/技术/基础设施的 USES 关系必须以 APT_GROUP 或 CAMPAIGN 为主体，MALWARE 不能作为 USES 主体
- 规则 24: AFFILIATED_WITH 不适用于安全厂商报告威胁的场景
- 规则 25: 不要忘记抽取 TIME 类型实体
- 规则 26: evidence_text 必须是原文逐字复制粘贴，不允许改写
- 新增 3 条反例 + evidence_text 改写反例

### 代码 (llm_service.py)
- build_user_prompt 新增禁止 MALWARE 作为 USES 主体、AFFILIATED_WITH 误用、evidence_text 逐字复制、TIME 实体提醒
- DEFAULT_PROMPT_PATH 切换到 extract-v3.md

## 评测结果 (deepseek-v4-flash, 3 篇)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_080 | 0.7500 | 0.7727 |
| kimsuky_060 | 0.8308 | 0.5385 |
| lazarus_091 | 0.6437 | 0.7027 |
