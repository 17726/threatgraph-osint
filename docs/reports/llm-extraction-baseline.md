# DeepSeek V4 抽取基线（2026-07-13）

## 验证范围

> **Legacy 历史基线：** 本节记录的 Prompt、运行 ID 和评测文件名来自版本化命名规范落地前的
> 历史运行，仅用于复盘，不作为当前正式工件输出格式。

本次使用真实 DeepSeek API，模型为 `deepseek-v4-flash`，Prompt 为 `extract-v1`。密钥只通过
临时环境变量传入，没有写入仓库、运行工件或 Git 历史。

最小 API 预检成功，响应模型为 `deepseek-v4-flash`，共使用 40 tokens。正式基线使用
`apt28_080` 单文档、单次运行；候选结果通过 extraction schema、关系矩阵、原文证据和字符
位置校验，再与人工 golden 一对一匹配。

## 已校验候选基线

这次历史运行发生在候选审计文件落地之前。下表只统计通过 schema、关系矩阵和证据门禁后
保留下来的候选，不包含模型原始输出中被过滤的无效项，因此可用于检查“可入库候选质量”，
但不得作为原始 DeepSeek 输出的完整端到端指标，也不得与后续包含 `candidate-audit.json` 的
运行直接横向比较。

运行 ID：`extract_apt28_080_extract-v1_20260713T083926515108`

| 对象 | Predicted | Golden | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 实体 | 23 | 32 | 12 | 11 | 20 | 0.521739 | 0.375000 | 0.436364 |
| 关系 | 7 | 24 | 5 | 2 | 19 | 0.714286 | 0.208333 | 0.322581 |

完整错误明细见
`data/evaluation/evaluation_result.apt28_080.deepseek-v4-flash.extract-v1.json`。

在上述口径限制下，这组结果说明当前默认 Prompt 的关系精度尚可，但实体和关系召回率偏低。
下一轮 Prompt 优化应优先补齐工具、技术、进程和基础设施漏抽，同时维持当前证据门禁，不能
用放宽 schema 的方式提高表面召回率。

## Golden 门禁发现

`apt28_080` golden 通过 schema、关系矩阵和证据校验，可以作为当前已校验候选基线。

PR #30 已修复 Kimsuky 和 Lazarus 的关系矩阵冲突。以下 Lazarus 字段问题属于历史基线运行时
状态，后续 Golden 修复已补齐，当前文件已迁移至 data/golden/。基于最新 `main` 复验：

- `kimsuky_060` 已通过 schema、关系矩阵、端点、证据和 chunk 边界校验。
- `lazarus_091` 的关系冲突已解决；历史基线运行时 `lazarus_091_c001` 曾是
  `char_start=0`、`char_end=null`，不满足 chunk 边界成对填写要求。

后续 Golden 已由 QA 组按真实文档长度补齐。评测器会在 API 调用前拒绝无效 golden，避免继续
产生不可比较的分数和 API 成本。

## 限制

本结果是单文档、单次模型运行，不代表整个数据集或模型的稳定平均表现。LLM 输出存在波动，
后续至少应在修复后的三组 golden 上执行多次运行，报告均值、标准差和失败率。当前后端统一
切块接口尚未落地，runner 仍沿用单文档单 chunk 约定；正式切块应由后端生成。
