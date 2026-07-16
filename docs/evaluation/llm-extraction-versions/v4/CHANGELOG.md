# extract-v3 → extract-v4

## 优化内容

### 系统提示词 (extract-v4.md)
- 规则 26: evidence_text 强化 "ctrl-f 可搜到的连续字符串"，举例 Kimsuky/Kimusky 差异
- 规则 27: PART_OF 合法模式 + APT_GROUP 不可用做 PART_OF head
- 规则 28: ATTRIBUTED_TO tail 只能是 COUNTRY/ORGANIZATION
- 规则 29: 良性连通性检测域名不抽为 INFRASTRUCTURE
- 规则 30: SHA256/MD5 哈希不抽为 MALWARE
- 新增 4 条反例（PART_OF/ATTRIBUTED_TO/连通性域名/SHA256）

### 代码 (llm_service.py)
- build_user_prompt 新增 PART_OF/ATTRIBUTED_TO/良性域名/SHA256 的提醒
- 安全厂商列表新增 Cisco Talos
- DEFAULT_PROMPT_PATH 切换到 extract-v4.md

## 评测结果 (deepseek-v4-flash, 3 篇)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_080 | 0.6957 | 0.5085 |
| kimsuky_060 | 0.7500 | 0.1250 |
| lazarus_091 | 0.6591 | 0.7692 |

## 结论

v4 全面回归。新增的 4 条 prompt 规则导致模型"认知过载"，规则之间相互干扰。此版本被放弃，后续版本回退到 v3 prompt + 代码层修补策略。
