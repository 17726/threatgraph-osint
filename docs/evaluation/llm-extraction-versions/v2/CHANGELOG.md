# extract-v1 → extract-v2

## 优化内容

### 系统提示词 (extract-v2.md)
- 规则 17: DISCOVERED_BY 仅表示漏洞首次被发现的具体事实，安全厂商日常监测不是
- 规则 18: CONTROLS 仅表示威胁组织实际控制资产，公司拥有产品不是
- 规则 19: INSTANCE_OF 仅表示同类型实例，恶意软件变种用 aliases
- 规则 22: 强调全文扫描 .exe/.dll/.sys 等可执行文件、命令、技术、基础设施
- 新增 few-shot 正面示例（9 实体 + 6 关系）+ 常见错误示例

### 代码 (llm_service.py)
- build_user_prompt 末尾加了 4 条重要提醒，禁止 DISCOVERED_BY/CONTROLS 误用
- DEFAULT_PROMPT_PATH 切换到 extract-v2.md

## 评测结果 (deepseek-v4-flash)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_080 | 0.6429 | 0.4815 |
