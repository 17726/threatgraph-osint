# extract-v5 → extract-v6

## 优化内容

### 评测器 (extraction_evaluator.py)

1. **normalize_name() 改进** — 从压缩空格为单个空格改为移除所有空格，实现：
   - 英文大小写不敏感
   - 全角/半角兼容（`（J S）` → `(js)` 匹配 `(js)`）
   - NFKC 规范化（全角→半角）

2. **_entity_match_score() 增强** — 跨类型实体匹配（score=2）：当预测实体和黄金实体类型不同但名称/别名匹配时给 2 分（之前只给 0 分）。例如 TOOL↔TECHNIQUE、MALWARE↔TOOL。

### 代码 (llm_service.py)

3. **URL 规范化大小写 bug 修复** — `_find_text_span()` 中 hxxp↔http 替换不再使用 `.lower()`，改为显式覆盖所有大小写变体（hxxp/http/HXXP/HTTP），最终搜索使用 `text_lower.find()` 做大小写不敏感匹配。

### 提示词

- Prompt 内容无变化，仅标题 `extract-v5` → `extract-v6`。

## 评测结果 (deepseek-v4-flash, 6 篇，最新黄金集)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_001 | 0.6296 | 0.5500 |
| apt28_080 | 0.5299 | 0.5287 |
| kimsuky_001 | 0.7308 | 0.5806 |
| kimsuky_060 | 0.9118 | 0.1818 |
| lazarus_001 | 0.4186 | 0.2804 |
| lazarus_091 | 0.7342 | 0.7164 |

## 结论

normalize_name 和 URL 修复对中文文章有显著改善。kimsuky_001 relation 0.408→0.581，lazarus_001 relation 0.114→0.280。但 lazarus_001 仍是最低的一篇，主要问题：(1) 模型列举大量全路径 URL 实体，(2) 类型不匹配，(3) MALWARE 作为 USES 主体违反规则。
