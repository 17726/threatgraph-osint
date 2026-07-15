# extract-v4 → extract-v5

## 策略调整

v4 新增 4 条规则导致全面回归。决定**回退到 v3 prompt，只在代码层修补**。

核心思路：让 prompt 做语义理解，让代码做规则校验和过滤。

## 优化内容

### 代码修改

1. **validate_extraction_result.py** — ALLOWED_RELATIONS 矩阵扩展
   - PART_OF: heads 新增 APT_GROUP，pairs 新增 (APT_GROUP→APT_GROUP) 和 (APT_GROUP→ORGANIZATION)
   - ATTRIBUTED_TO: tails 新增 APT_GROUP（允许 CAMPAIGN/MALWARE ATTRIBUTED_TO APT_GROUP）

2. **llm_service.py** — build_user_prompt 回退
   - 移除 v4 新增的 PART_OF/ATTRIBUTED_TO/良性域名/SHA256 提醒行
   - 安全厂商列表移除 Cisco Talos（回退到 v3 版本）
   - 从 11 条缩减回 7 条

3. **llm_service.py** — parse_llm_response_with_audit 代码级过滤器
   - SHA256/MD5/SHA1 哈希检测: 自动拒绝 MALWARE 类型的哈希值实体
   - 良性连通性域名过滤: 自动拒绝 20 个已知公共服务域名
   - 过滤器在 dedup 之前执行

### Prompt (extract-v5.md)
- 系统提示词回退到 v3 版本
- 仅在用户提示词里标注 prompt_version: extract-v5

## 评测结果 (deepseek-v4-flash, 6 篇)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_001 | 0.4783 | 0.4615 |
| apt28_080 | — | — |
| kimsuky_001 | 0.6061 | 0.4082 |
| kimsuky_060 | — | — |
| lazarus_001 | 0.3433 | 0.1140 |
| lazarus_091 | — | — |

## 结论

回退 prompt 到 v3 + 代码层修复后，6 篇评测开始覆盖中文文章。但 kimsuky_001 (relation=0.408) 和 lazarus_001 (relation=0.114) 中文文章 F1 极低，需要进一步处理黄金集中英文字符差异和 URL 规范化问题。
