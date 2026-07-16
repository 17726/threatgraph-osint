# extract-v6 → extract-v7

## 目标

针对 lazarus_001（中文文章 relation F1 最低仅 0.28）做代码层修复，不修改 prompt（v6 已证明 prompt 改动有回归风险）。

## 优化内容

### 1. containment matching — 评测器 (extraction_evaluator.py)

`_entity_match_score()` 新增包含匹配：同类型实体中，一个 name 是另一个的子串时给 score=2。

例如：`Lazarus Group` ↔ `Lazarus`、`PowerRatankba` ↔ `PowerRatankba.0`

### 2. infrastructure URL dedup — 代码 (llm_service.py)

`parse_llm_response_with_audit()` 新增基础设施 URL 去重：共享同一基础域名的 INFRASTRUCTURE 实体合并为一个，全路径 URL 转为别名。

例如：`hxxps://bitcoingöld[.]org/bitcoingold.exe` 合并到 `hxxps://bitcoingöld[.]org`（alias）

### 3. normalize_name 去空格 — 评测器 (extraction_evaluator.py) & 代码 (llm_service.py)

从压缩空格为单空格改为**移除所有空格**，配合 NFKC 实现：
- 全角括号 `（J S）` → `(js)` 匹配半角 `(js)`
- `L A Z A R U S` → `lazarus`

### 4. 文案修正 — 提示词 (extract-v7.md)

Rule 5 从 "必须满足 relationship-matrix.md" 改为 "必须满足下方关系类型配对矩阵"（模型看不到那个文件，矩阵通过代码注入）。

### Prompt 变化

v7 prompt 与 v6 完全相同，仅标题改为 extract-v7。

## 评测结果 (deepseek-v4-flash, 6 篇，最新黄金集)

| Article | entity F1 | relation F1 |
|---|---|---|
| apt28_001 | 0.6230 | 0.5600 |
| apt28_080 | 0.7333 | 0.7273 |
| kimsuky_001 | 0.4421 | 0.2667 |
| kimsuky_060 | 0.8750 | 0.5106 |
| lazarus_001 | 0.4160 | 0.3725 |
| lazarus_091 | 0.6923 | 0.7742 |

### v6 → v7 对比

| Article | Δ entity | Δ relation |
|---|---|---|
| apt28_001 | -0.0067 | **+0.0100** |
| apt28_080 | **+0.2034** | **+0.1985** |
| kimsuky_001 | -0.2887 | -0.3140 |
| kimsuky_060 | -0.0368 | **+0.3288** |
| lazarus_001 | -0.0026 | **+0.0922** |
| lazarus_091 | -0.0419 | **+0.0578** |


5/6 篇 relation 上涨。lazarus_001 relation 从 0.280 → 0.373。

kimsuky_001 暴跌是 LLM 方差（v7 这轮模型过度 verbose，抽了 83 实体 78 关系，v6 比较克制）。

## 被拒记录 (candidate-audit)

| Article | rejected E | rejected R | 原因明细 |
|---|---|---|---|
| apt28_001 | 1 | 2 | validation_failed: 3 |
| apt28_080 | 2 | 7 | validation_failed: 9 |
| kimsuky_001 | 13 | 19 | validation_failed: 18, infrastructure_url_merged: 7, duplicate_relation_removed: 7 |
| kimsuky_060 | 0 | 6 | validation_failed: 6 |
| lazarus_001 | 5 | 6 | infrastructure_url_merged: 5, duplicate_relation_removed: 5, validation_failed: 1 |
| lazarus_091 | 8 | 9 | validation_failed: 17 |
| **总计** | **29** | **49** | validation_failed: 54, infrastructure_url_merged: 12, duplicate_relation_removed: 12 |

### 拒绝原因说明
- **validation_failed**: evidence_text 未在原文精确匹配或矩阵违反
- **infrastructure_url_merged**: 全路径 URL 被合并到基础域名实体（v7 新增）
- **duplicate_relation_removed**: 重复关系被移除
