# DeepSeek V4 抽取基线（2026-07-13）

## 验证范围

本次使用真实 DeepSeek API，模型为 `deepseek-v4-flash`，Prompt 为 `extract-v1`。密钥只通过
临时环境变量传入，没有写入仓库、运行工件或 Git 历史。

最小 API 预检成功，响应模型为 `deepseek-v4-flash`，共使用 40 tokens。正式基线使用
`apt28_080` 单文档、单次运行；候选结果通过 extraction schema、关系矩阵、原文证据和字符
位置校验，再与人工 golden 一对一匹配。

## 可信基线

运行 ID：`extract_apt28_080_extract-v1_20260713T083926515108`

| 对象 | Predicted | Golden | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 实体 | 23 | 32 | 12 | 11 | 20 | 0.521739 | 0.375000 | 0.436364 |
| 关系 | 7 | 24 | 5 | 2 | 19 | 0.714286 | 0.208333 | 0.322581 |

完整错误明细见
`data/evaluation/evaluation_result.apt28_080.deepseek-v4-flash.extract-v1.json`。

这组结果说明当前默认 Prompt 的关系精度尚可，但实体和关系召回率偏低。下一轮 Prompt 优化
应优先补齐工具、技术、进程和基础设施漏抽，同时维持当前证据门禁，不能用放宽 schema 的
方式提高表面召回率。

## Golden 门禁发现

`apt28_080` golden 通过 schema、关系矩阵和证据校验，可以作为当前可信基线。

另外两份英文 golden 暂不能用于可信关系指标：

- `kimsuky_060` 有 5 条关系违反当前关系矩阵，包括 `APT_GROUP PART_OF APT_GROUP`、
  `CAMPAIGN ATTRIBUTED_TO APT_GROUP`、`MALWARE USES TOOL`，以及两条方向反转的
  `ORGANIZATION DISCOVERED_BY ...`。
- `lazarus_091` 有 1 条 `CAMPAIGN ATTRIBUTED_TO APT_GROUP` 不在当前允许配对中。

这些冲突需要 QA 与架构组共同决定：修正 golden 关系方向/类型，或正式扩展关系矩阵。评测器
现在会在 API 调用前拒绝无效 golden，避免继续产生不可比较的分数和 API 成本。

## 限制

本结果是单文档、单次模型运行，不代表整个数据集或模型的稳定平均表现。LLM 输出存在波动，
后续至少应在修复后的三组 golden 上执行多次运行，报告均值、标准差和失败率。当前后端统一
切块接口尚未落地，runner 仍沿用单文档单 chunk 约定；正式切块应由后端生成。
