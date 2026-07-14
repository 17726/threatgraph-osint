# LLM 实体关系抽取评测指标二审稿

日期：2026-07-15
版本：Review Draft 0.1
状态：方向已获项目负责人认可，计算细节待 QA、LLM 和架构组二次评审
实现状态：未实现，当前评测器仍使用旧口径

本文把 LLM 抽取评测的对象、匹配方法、公式和异常情况集中说明。二审通过前，不修改历史结果，不设置 CI 性能门槛，也不把本文数字当成当前系统已经产出的指标。

## 1. 为什么要重写指标口径

当前 `backend/app/services/extraction_evaluator.py` 有三个明显限制：

1. 实体和关系必须在相同 `chunk_id` 下匹配，无法公平比较不同切块策略。
2. Candidate Audit 中所有 rejected 项都直接增加预测数量并视为 FP，没有先和 Golden 匹配。
3. 当预测和 Golden 同时为空时，当前实现把 Precision、Recall、F1 都写成 `1.0`，容易把“没有支持样本”误写成“表现完美”。

这三点会混淆模型语义能力、格式失败、过滤效果和重复输出。新口径先把数据层次拆开，再计算指标。

## 2. 评测对象分层

```text
Document
  -> Chunk Strategy
  -> Provider Response
  -> Raw Emission
  -> 解析、规范化、去重
  -> Raw Semantic Candidate
  -> Schema / 类型 / 关系矩阵 / 证据校验
  -> Validated Candidate
  -> 归一化和正式导入
  -> Accepted Graph
```

各层职责如下：

| 层 | 内容 | 是否直接计算语义 P/R/F1 |
| --- | --- | --- |
| Provider Response | 模型返回的原始正文，包括非 JSON、截断和错误响应 | 否，只统计请求和解析指标 |
| Raw Emission | Parser 能识别出的每一条候选，包含重复和以后会被拒绝的项 | 否，先用于审计和重复统计 |
| Raw Semantic Candidate | Raw Emission 按文档级语义身份规范化并去重后的候选集合 | 是 |
| Validated Candidate | 通过当前校验政策的唯一候选集合 | 是 |
| Accepted Graph | 归一化后实际进入 SQLite canonical graph 的事实 | 后续可选，不是本轮必需指标 |
| Candidate Audit | 每条候选的 accepted/rejected/merged 状态和原因 | 不单独算 F1，提供诊断指标 |

这里特意把 Raw Emission 和 Raw Semantic Candidate 分开。重复输出属于模型纪律问题，但不应伪装成另一条语义幻觉。语义 P/R/F1 使用去重后的集合，重复问题单独报告 `duplicate_rate`。

## 3. 评测单位

Golden 的原子是一篇 Document。Dataset 只是本次选了哪些 Document/Golden。

评测顺序固定为：

1. 每个预测先还原到 Document 全文坐标；
2. 在单篇 Document 内规范化和去重；
3. 在单篇 Document 内与对应 Golden 一对一匹配；
4. 保存逐文档 TP/FP/FN；
5. 将所有文档的 TP/FP/FN 相加，计算总体 micro 指标。

不能先把不同文档的候选混在一起匹配。同名实体在两篇文章中分别出现，应分别贡献 support。

## 4. 实体匹配

实体匹配建议使用：

```text
同一 Document
+ 实体类型相同
+ normalized name 完全相同，或 name/aliases 有交集
+ 一对一最大匹配
```

规范化至少包括 Unicode NFKC、大小写折叠、首尾空白和连续空白合并。是否增加标点、域名去混淆、CVE 和 ATT&CK 编号规范化，需要由测试判例决定，不能靠模糊相似度临时匹配。

同一个预测只能命中一个 Golden，同一个 Golden 也只能被一个预测命中。别名重复不能制造多个 TP。

## 5. 关系匹配

### 5.1 关系端到端指标

关系端到端匹配要求：

```text
同一 Document
+ 预测主体已匹配 Golden 主体
+ 预测客体已匹配 Golden 客体
+ relation_type 相同
+ 方向相同
+ 一对一匹配
```

这是知识图谱抽取的主要语义指标。只识别出关系名称但端点错误，仍算 FP；对应 Golden 关系算 FN。

### 5.2 条件关系指标

条件关系指标只检查实体端点都已经正确识别的子集，回答：

> 如果主体和客体都找到了，模型是否判断对关系类型和方向？

它用于诊断，不能替代端到端指标。报告中必须同时显示条件关系 support，避免只在少量容易样本上得到很高分。

### 5.3 跨段关系

关系匹配不再要求相同 `chunk_id`。预测需要先还原全文身份。只要主体、客体、关系类型和方向符合 Golden，就可以参与匹配。

证据是否充分单独评分。这样可以区分“事实判断正确但证据范围不同”和“关系本身错误”。

## 6. TP、FP、FN 和 P/R/F1

对实体、关系端到端和条件关系分别计算：

```text
TP = 与 Golden 一对一匹配成功的预测数
FP = 没有匹配 Golden 的唯一预测数
FN = 没有被预测命中的 Golden 数

Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * Precision * Recall / (Precision + Recall)
Support   = TP + FN
```

所有结果必须同时保存 TP、FP、FN、Predicted 和 Support。只给一个 F1 不足以解释结果。

### 6.1 空集规则

建议规则如下：

| 预测 | Golden | TP/FP/FN | Precision | Recall | F1 | 解释 |
| --- | --- | --- | --- | --- | --- | --- |
| 空 | 空 | 0/0/0 | `null` | `null` | `null` | 没有 support，不能写 1.0 |
| 空 | 非空 | 0/0/N | `null` | 0 | 0 | 完全漏抽 |
| 非空 | 空 | 0/N/0 | 0 | `null` | 0 | 全部是额外预测 |
| 非空 | 非空 | 正常计算 | 正常计算 | 正常计算 | 正常计算 | 有效评测 |

UI 和报告应把 `null` 显示为“不适用”，不能显示成 0% 或 100%。

### 6.2 为什么不报告 FPR

FPR 的分母需要 TN：

```text
FPR = FP / (FP + TN)
```

开放式实体关系抽取无法枚举正文中所有“不成立的实体或关系”，因此没有稳定 TN。项目报告 FP 数量、Precision、Recall、F1 和明确分母的拒绝指标，不使用 FPR。

## 7. Rejected、Duplicate 和 Empty

### 7.1 Rejected 不能自动算 FP

每条 rejected 候选必须先做语义匹配：

- rejected 候选与 Golden 匹配：模型抽对了，但校验器拒错了；
- rejected 候选与 Golden 不匹配：模型产生了错误候选，校验器拒对了；
- rejected 候选与另一条候选重复：计入重复，不直接增加语义 FP。

把所有 rejected 直接追加到 predicted 数量，会把正确拒绝、错误拒绝和重复混在一起。

### 7.2 最小例子

Golden 实体：

```text
APT28
X-Agent
```

模型发射：

| 候选 | 审计结果 | 与 Golden 的关系 |
| --- | --- | --- |
| APT28 | accepted | 正确 |
| X-Agent | rejected：offset 校验错误 | 正确，但被错误拒绝 |
| FakeTool | rejected：无证据 | 幻觉，被正确拒绝 |
| APT28 | merged_duplicate | 与第一条重复 |

Raw Emission 共 4 条，规范化去重后的 Raw Semantic Candidate 为 3 条：APT28、X-Agent、FakeTool。

Raw Semantic：

```text
TP = 2
FP = 1
FN = 0
Precision = 2 / 3 = 0.666667
Recall = 2 / 2 = 1.0
F1 = 0.8
```

Validated Candidate 只有 APT28：

```text
TP = 1
FP = 0
FN = 1
Precision = 1.0
Recall = 0.5
F1 = 0.666667
```

审计指标：

```text
raw_emission_count = 4
duplicate_count = 1
duplicate_rate = 1 / 4 = 0.25
rejected_count = 2
correct_rejection_count = 1
false_rejection_count = 1
rejection_precision = 1 / 2 = 0.5
validation_recall_loss = (2 - 1) / 2 = 0.5
```

`validation_recall_loss` 的分母是 Raw Semantic 已经命中的 Golden 数。它表示校验阶段丢掉了多少本来抽对的事实。

### 7.3 Empty 的定义

`Empty` 只描述解析后没有可用候选集合：

- Provider 正常返回空数组；
- Parser 成功，但没有实体和关系；
- 评测作用域经过规范化后为空。

“模型产生候选但全部被拒绝”不是运行过程上的 Empty。它有 Raw Emission 和 Candidate Audit，只是 Validated Candidate 为空。

`Promoted` 也不是计数作用域。它表示实验是否被选择进入 Git，与 rejected 或 empty 没有数学关系。

## 8. 格式和运行指标

语义 F1 不能替代 API 和解析稳定性。每次实验至少记录：

| 指标 | 计算 |
| --- | --- |
| `provider_success_rate` | 成功收到 Provider 响应的 Attempt / 总 Attempt |
| `parse_success_rate` | 能解析成候选结构的响应 / 成功响应 |
| `schema_valid_rate` | 通过草稿或正式 Schema 的解析结果 / 解析成功结果 |
| `completed_document_rate` | 完成预期全部处理的 Document Run / 总 Document Run |
| `partial_document_count` | 至少一个 chunk 失败但保留部分结果的 Document 数 |
| `token_total` | 输入和输出 token 总数 |
| `latency_total` | 本次运行总耗时 |
| `estimated_cost` | 按 Provider 价格和 token 计算的估算成本 |

“返回的是 JSON”只能说明解析或格式成功，不能说明实体关系正确。

### 8.1 Parse Failure 怎么计分

如果一篇有 Golden 的文档发生解析失败：

1. `parse_success=false`；
2. 该文档在端到端语义作用域中视为预测为空；
3. Golden 实体和关系全部贡献 FN；
4. 不凭空增加 FP；
5. 该文档不能从总体 micro 指标中删除。

否则，只统计成功文档会夸大总体表现。

## 9. Candidate Audit 指标

建议至少报告：

| 指标 | 定义 |
| --- | --- |
| `rejected_count` | 被 Validator 拒绝的 Raw Emission 数 |
| `rejection_rate` | rejected / 非重复 Raw Emission |
| `correct_rejection_count` | rejected 且不匹配 Golden 的唯一语义候选数 |
| `false_rejection_count` | rejected 但匹配 Golden 的唯一语义候选数 |
| `rejection_precision` | correct_rejection / (correct_rejection + false_rejection) |
| `validation_recall_loss` | Raw 命中但 Validated 未命中的 Golden / Raw 命中的 Golden |
| `duplicate_count` | 被确定性归并的 Raw Emission 数 |
| `duplicate_rate` | duplicate / Raw Emission |
| `rejection_reasons` | 按 reason code 统计的数量和比例 |

拒绝原因使用稳定代码，不只保存自然语言，例如：

```text
parse_failed
schema_invalid
unknown_entity_type
unknown_relation_type
relation_pair_invalid
endpoint_missing
evidence_missing
evidence_not_grounded
offset_invalid
merged_duplicate
```

## 10. 证据指标

语义事实和证据质量分开报告：

| 指标 | 含义 |
| --- | --- |
| `evidence_grounded_rate` | `document.clean_text[start:end] == evidence_text` 的候选比例 |
| `evidence_exact_match` | 预测证据范围与 Golden 完全相同 |
| `evidence_overlap_match` | 预测和 Golden 证据范围有重叠并达到约定阈值 |
| `evidence_missing_count` | 语义候选没有可回溯证据的数量 |

证据文本截取不同，不应自动把语义正确的实体或关系判为 FP。Accepted Graph 可以继续要求证据门禁，但报告要能看出“语义正确、证据失败”这一类错误。

跨段关系可能需要多个证据 span。Golden v1 只支持一个连续范围，二审需要决定：

- 继续使用单一连续范围；
- 允许 `evidence_spans[]`；
- 关系语义与多段证据分别存储。

## 11. 切块评测指标

同一个切块 Experiment 必须固定：

```text
Document 内容和 content_hash
Golden 版本和内容
模型和 Provider
Prompt、Schema、关系矩阵
模型参数
评测器版本
```

只改变 Chunk Strategy。至少记录：

| 指标 | 作用 |
| --- | --- |
| `chunk_count` | 本策略产生多少块 |
| `overlap_chars` 或 `overlap_tokens` | 重叠规模 |
| `relation_chunk_coverage_upper_bound` | 不调用模型时，至少一个 chunk 能覆盖关系所需证据的比例 |
| `cross_chunk_relation_support` | 关系两端不能被同一无重叠 chunk 覆盖的 Golden 数 |
| `entity_recall` | 实际实体召回 |
| `relation_e2e_recall` | 实际关系端到端召回 |
| `duplicate_rate` | overlap 带来的重复候选比例 |
| `token_total`、`estimated_cost`、`latency_total` | 代价 |

推荐第一轮只比较：

```text
A：全文输入
B：按段落切块，无 overlap
C：按段落切块，有 overlap
```

六篇 Document 使用同一 Dataset。总体结果使用 micro TP/FP/FN，同时列出逐文档差异。样本只有六篇时，只能写探索性结论。

如果某条 Golden 关系在某个策略下没有任何 chunk 能同时覆盖必要证据，这属于切块结构损失。模型没有抽出它时，要同时显示：

- 该关系是 FN；
- 它属于 `uncoverable_by_chunk` 分类；
- 当前策略的结构上界已经丢失这条关系。

这样可以区分“模型没学会”和“算法根本没让模型看到完整上下文”。

## 12. 汇总与报告口径

### 12.1 总体指标

总体以 micro 指标为主：先汇总所有文档 TP/FP/FN，再计算 P/R/F1。逐文档指标必须保留，防止一篇长文档掩盖其他文档。

Macro 平均暂不作为主指标。后续若启用，需要同时公开每篇 support 和空集处理方式。

### 12.2 建议展示顺序

课程报告或前端评测页建议按以下顺序展示：

1. Dataset：文档数、实体 support、关系 support；
2. 运行质量：完成率、解析率、Schema 通过率；
3. Validated Candidate：实体 P/R/F1、关系端到端 P/R/F1；
4. Raw Semantic：实体和关系 P/R/F1；
5. Audit：拒绝、错误拒绝、重复和原因分布；
6. 切块、token、成本和时延；
7. 逐文档 TP/FP/FN 及典型错误。

Validated 关系端到端 F1 可以作为主要描述指标，但现阶段不作为强 CI 门槛。它必须和 support、失败文档及 Raw/Audit 指标一起出现。

### 12.3 结果 JSON 建议形态

下面只表示组织方式，不是已经冻结的 Schema：

```json
{
  "dataset": {
    "document_count": 6,
    "entity_support": 183,
    "relation_support": 150
  },
  "run_quality": {
    "parse_success_rate": 1.0,
    "schema_valid_rate": 0.95
  },
  "scopes": {
    "raw_semantic": {
      "entities": {"tp": 0, "fp": 0, "fn": 0, "precision": null, "recall": null, "f1": null},
      "relations_e2e": {"tp": 0, "fp": 0, "fn": 0, "precision": null, "recall": null, "f1": null}
    },
    "validated_candidate": {
      "entities": {"tp": 0, "fp": 0, "fn": 0, "precision": null, "recall": null, "f1": null},
      "relations_e2e": {"tp": 0, "fp": 0, "fn": 0, "precision": null, "recall": null, "f1": null},
      "relations_conditional": {"tp": 0, "fp": 0, "fn": 0, "precision": null, "recall": null, "f1": null}
    }
  },
  "audit": {
    "rejected_count": 0,
    "correct_rejection_count": 0,
    "false_rejection_count": 0,
    "duplicate_count": 0,
    "rejection_reasons": {}
  }
}
```

## 13. 每次 Evaluation Run 必须记录什么

当前先做记录，不要求模型结果严格重现。每次评测至少关联：

```text
Evaluation Run ID
Extraction Run ID
Document 路径与 content_hash
Golden 路径、golden_version 和内容哈希
Provider、model_name 和模型参数
Prompt 版本和内容哈希
Schema、关系矩阵、Parser、Normalizer、Validation Policy、Evaluator 版本
Chunk Strategy 和参数
代码 Commit SHA
开始/结束时间
token、成本、时延
运行状态：completed / partial / failed
```

失败和 partial 运行不得从实验历史中静默删除。是否提交 Git 由实验价值决定，但本地运行记录要能解释本轮为什么失败。

## 14. 二审需要逐项确认的问题

1. Raw Semantic P/R/F1 是否确认在文档级规范化去重后计算，重复只进入 Duplicate 指标？
2. 当前标注政策明确排除但模型仍输出的对象，是计为语义 FP，还是只记 Policy Violation？推荐：若 Prompt 明确要求排除且对象仍能映射到当前 Schema，则计 FP；Schema 无法表达的对象只进审计。
3. `Precision/Recall/F1=null` 的空集规则是否接受？
4. 条件关系指标的分母是否只包含两个端点均被正确识别的 Golden 关系？
5. 证据匹配是否独立于语义 TP；Accepted Graph 是否继续把 grounded evidence 作为硬门槛？
6. 跨段关系是否升级为 `evidence_spans[]`，还是暂时使用一个连续范围？
7. `rejection_precision` 和 `validation_recall_loss` 的名称、分母是否清楚？
8. Parse Failure 是否按空预测计入总体 FN，而不是从总体指标排除？
9. 第一轮切块实验是否只采用全文、无重叠和有重叠三组？
10. 当前只有六篇 Golden，是否同意所有结论标记为探索性，不启用强性能门槛？

二审通过后，应先用固定真值表补单元测试，再修改评测器。不能先改实现，再用新的实现反推指标定义。
