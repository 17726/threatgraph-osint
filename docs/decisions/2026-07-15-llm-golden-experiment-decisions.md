# LLM Golden、实验归档与切块评测阶段决策

日期：2026-07-15
状态：阶段性决策，供架构、LLM、QA 和报告组评审
影响范围：Golden 标注、抽取运行、实验归档、版本记录和后续切块实验

本文只记录已经确认的规则、仓库当前真实状态和仍待评审的问题。它不是代码实现说明，也不表示文中提到的未来目录、Manifest 或评测指标已经落地。

如果本文与 `docs/plans/2026-07-14-llm-extraction-evaluation-architecture-closure.md` 中尚未实施的任务设想冲突，以本文列出的阶段性决策为准。

## 1. 先把几个名称说清楚

前面的讨论中出现过“Dataset / Experiment Manifest 编组”一词。它不是 “dist experiment 演变组”，也不是一种新的 Golden。

本项目统一使用下面这些名称：

| 名称 | 中文解释 | 当前是否有正式实现 |
| --- | --- | --- |
| Document | 一篇清洗后的完整文章，正文保存在 `clean_text` | 有 |
| Golden | 一篇 Document 在当前本体和标注政策下的人工标准答案 | 有 |
| Dataset | 一次评测选用的 Document/Golden 清单 | 没有 Manifest 实现 |
| Provider Attempt | 一次模型 API 请求或重试 | 只有运行过程，没有独立归档对象 |
| Extraction Run | 一篇 Document 使用一套模型、Prompt 和参数完成的一次抽取 | 有 `run_id`，没有 Run 目录 |
| Evaluation Run | 某个 Extraction Run 对某个 Golden 的一次评测 | 有 JSON 结果，身份契约尚不完整 |
| Experiment | 围绕一个实验问题组织的一组 Run、Evaluation Run 和结论 | 只有文档概念 |
| Promoted Experiment | 经人工判断有对照或复盘价值，并通过 PR 进入 Git 的 Experiment | 只有生命周期约定 |
| Baseline | 经审核后被选为后续对照基准的 Experiment 引用 | 只有文档概念 |
| Iteration | 报告中的一次“假设、改动、结果、结论”记录 | 尚未建立统一模板 |

仓库中没有名为 `Track` 或 `Treaty` 的正式数据对象、目录或字段。后续文档不再用这两个词表达实验链路。若讨论的是同一条配置演进线，直接使用 `Experiment` 和 `Iteration`。

Dataset 与 Experiment 的关系可以写成：

```text
Dataset
  = 本次评测选择了哪些 Document 和 Golden

Experiment
  = 研究问题
  + Dataset 引用
  + 对照组和实验组的 Extraction Run
  + Evaluation Run
  + 结果与结论
```

例如“比较全文输入、无重叠切块和重叠切块”是一个 Experiment。六篇 Golden 的路径列表是该实验使用的 Dataset。Dataset 不复制 Golden，也不改变 Golden 版本。

## 2. 仓库当前是什么状态

当前 `main` 仍使用以下目录：

```text
data/documents/<target_group>/<doc_id>.json
data/golden/golden-<language>-<doc_id>-<schema_version>-<golden_version>.json
data/extracted/<抽取结果或候选审计文件>.json
data/evaluation/<评测结果文件>.json
data/threatgraph_osint.db
```

PR #35 已经统一新运行的版本字段、UTC 标签和带随机后缀的 `run_id`。当前正式命名为：

```text
data/extracted/extract-<doc_id>-<model>-<prompt_version>-<schema_version>-<timestamp>-<run_suffix>.json
data/extracted/extract-<doc_id>-<model>-<prompt_version>-<schema_version>-<timestamp>-<run_suffix>-candidate-audit.json
data/evaluation/evaluation_result-<doc_id>-<model>-<prompt_version>-<schema_version>-<golden_version>-<timestamp>.json
data/golden/golden-<language>-<doc_id>-<schema_version>-<golden_version>.json
```

仓库还保留旧文件，例如：

```text
data/extracted/extract_apt28_001_extract-v1_20260712T155115.json
data/evaluation/evaluation_result.apt28_080.deepseek-v4-flash.extract-v1.json
```

这些文件没有被清理或迁进 Experiment 目录。当前 runner 仍把新结果写到 `data/extracted/` 和 `data/evaluation/`，没有以下能力：

- 没有 `data/runs/<run_id>/`；
- 没有 `data/experiments/<experiment_id>/manifest.json`；
- 没有 promote 命令或 `promoted` 状态字段；
- 没有自动把普通运行整理成 Baseline 的流程；
- 没有清理旧 Extraction/Evaluation 文件。

因此，`Promoted Experiment` 目前是提交策略，不是独立运行环境。它的含义只是：某次实验有复盘价值，负责人决定把必要工件提交 Git 并走 PR 评审。

PR #41 只补文件名与 payload 的一致性校验，不负责目录迁移或 Experiment 生命周期。PR #41 未合入前，也不能把其中的行为写成 `main` 已具备的能力。

## 3. PR #27 是什么

PR #27 的原始提交来自张楚贤，核心提交为 `df3c998`，主要内容是：

- 新增 `LLMExtractionService`；
- 接入 OpenAI-compatible API；
- 增加模型返回解析和 Schema 校验；
- 内置关系矩阵校验；
- 增加单篇、批量抽取和可选 SQLite 导入入口；
- 增加不依赖 API Key 的测试脚本。

PR #27 合入前，其分支又合入了 PR #28。最终 merge commit `359e3bc` 因此同时带入了 PR #28 的 Golden 评测、Candidate Audit 和评测报告加固。回顾历史时要区分：

```text
PR #27 原始核心：LLM 抽取服务和 runner
PR #28：在该基础上补 Golden 评测与候选审计
PR #27 最终合入结果：包含两部分
```

长对话记录不作为运行工件，也不建议整段提交到仓库。需要长期保留的决定应整理到本文、PR 描述和 Review 评论中。若聊天中出现了代码无法解释的关键取舍，应提炼为一条可审阅的决策，不复制完整聊天正文。

## 4. Golden 按整篇 Document 标注

### 4.1 已确认的原则

人工标注读取完整 Document，不按算法策略人工切块。标注员在当前本体、关系矩阵和标注政策范围内检查整篇文章，不能因为某段较长、后端以后可能切块，或本轮时间有限，就只标方便的部分。

这条规则解决两个问题：

1. Golden 不随算法切块策略变化。全文、无重叠切块和重叠切块可以使用同一份答案比较。
2. 人工可以识别跨自然段关系。算法切块是否破坏这类关系，正是后续实验要测量的问题，不能在标注阶段先把它删掉。

“完整标注”包含两层含义：

- 范围完整：整篇 `clean_text` 都经过人工审阅；
- 政策内完整：凡是当前实体类型、关系类型和标注政策要求记录的事实，都应进入 Golden。

如果某段没有人工审阅，这份 Golden 就不是正式的全文 Golden，也不能晋升 Baseline。不能一边称其为“标全”，一边把遗漏区域默认排除在评分之外。

### 4.2 “没有标”的内容怎么处理

需要区分三类情况：

| 情况 | 含义 | 处理方式 |
| --- | --- | --- |
| 已审阅且属于标注范围 | 当前本体和政策要求记录的事实 | 必须标注；漏标是 Golden 缺陷 |
| 已审阅但政策明确排除 | 署名作者、页面维护者、无法用当前类型表达的文件工件等 | 在标注政策或 `notes` 中说明 |
| 未审阅 | 标注员没有检查的正文范围 | 不得作为正式全文 Golden |

模型输出政策明确排除的内容时，是算 FP、算校验错误还是只进审计，属于评测政策问题，放在指标二审稿中确认。这个边界不能用“没有出现在 Golden”一句话自动处理。

### 4.3 当前 6 篇 Golden 的真实结构

仓库核验结果如下：

| Golden | 正文长度 | `chunks` 数 | 覆盖范围 | 实体 | 关系 |
| --- | ---: | ---: | --- | ---: | ---: |
| `golden-en-apt28_080-1.0-1.0.json` | 21738 | 1 | `[0, 21738)` | 32 | 24 |
| `golden-en-kimsuky_060-1.0-1.0.json` | 5141 | 1 | `[0, 5141)` | 35 | 28 |
| `golden-en-lazarus_091-1.0-1.0.json` | 15880 | 1 | `[0, 15880)` | 33 | 33 |
| `golden-zh-apt28_001-1.0-1.0.json` | 3324 | 1 | `[0, 3324)` | 21 | 18 |
| `golden-zh-kimsuky_001-1.0-1.0.json` | 4330 | 1 | `[0, 4330)` | 25 | 16 |
| `golden-zh-lazarus_001-1.0-1.0.json` | 9565 | 1 | `[0, 9565)` | 37 | 31 |

六份文件在结构上都是全文覆盖。它们仍包含 `chunks[0]`，因为 Golden v1 Schema 要求按 `chunks` 组织实体和关系。这里的单 chunk 是兼容外壳，不表示人工采用了切块算法。

机器检查只能证明范围覆盖、证据位置和 Schema 合法，不能证明语义上绝无漏标。六份 Golden 是否达到最终 Baseline 质量，仍需要 QA 的二次人工审阅。

### 4.4 跨段关系

关系两端可以出现在不同自然段。标注时不能因为未来算法可能把它们切到不同块，就删除这条关系。

Golden v1 只有一个连续的 `evidence_text` 和一组 `[char_start, char_end)`。如果一条关系需要两处不相邻证据，当前可选办法只有：

1. 选择能独立证明关系的最小连续上下文；
2. 用一个较长的连续范围覆盖两处证据及中间文本；
3. 若前两种都不能准确表达，在 `notes` 中记录，等待多证据 span 契约。

是否把关系证据改成多个 span 是待定 Schema 问题。本次文档 PR 不改 Golden v1。

## 5. 切块只属于算法运行

切块策略属于 Extraction Run 配置，不属于 Golden 身份。后续比较切块策略时应使用同一批 Document 和同一批 Golden：

```text
A：整篇输入
B：无重叠切块
C：重叠切块
```

每组预测都要先把 chunk 局部位置还原为 Document 全文位置，再按文档聚合和去重，最后与全文 Golden 比较。不能拿 Golden 的 v1 `chunk_id` 充当语义匹配主键。

切块实验至少回答两个问题：

1. 结构上有多少 Golden 关系能被任意一个 chunk 同时覆盖两端证据；
2. 在结构上可见的前提下，模型实际抽取出了多少关系。

建议增加一个不依赖模型的上界指标：

```text
relation_chunk_coverage_upper_bound
  = 至少有一个 chunk 能覆盖关系所需证据的 Golden 关系数
    / Golden 关系总数
```

如果第一段和第三段的关系跨度大于 overlap，单纯增加重叠仍可能无法恢复。后续可以比较全文复核、实体聚合后的二次关系抽取或检索式关系配对，但这些属于新的实验变量。

当前评测器仍按相同 `chunk_id` 匹配实体和关系，尚不能严谨执行上述实验。实施切块消融前，必须先把匹配主键改为 Document 身份和全文坐标。

## 6. Experiment 不替代普通运行环境

普通运行和 Experiment 的区别不在于使用不同 runner：

```text
运行 runner
  -> 产生 Extraction Run
  -> 可选产生 Evaluation Run
  -> 本地查看结果
  -> 若能证明改进、退化或重要边界，由负责人选入 Experiment
  -> 通过 PR 归档后成为 Promoted Experiment
  -> 经二次审核可指定为 Baseline
```

普通调试、失败重试和没有结论的运行不上传即可，不需要再设计一种 “ordinary attempt 目录”。Provider Attempt 仍可作为 Run 内部的重试记录，用于排查错误和成本，但它不是 Git 上传分类。

未来可以讨论以下目录，但目前没有冻结：

```text
data/runs/<run_id>/
data/evaluations/<evaluation_run_id>/
data/experiments/<experiment_id>/manifest.json
data/baselines/<baseline_id>.json
```

即使采用这套目录，也不应把所有本地运行自动提交 Git。Manifest 负责引用被选中的工件，不复制同一结果。

## 7. 版本号和每次生成的新文件

### 7.1 哪些版本人工递增

| 字段 | 什么时候改 | 是否自动递增 |
| --- | --- | --- |
| `prompt_version` | Prompt 内容变化 | 人工决定 |
| `schema_version` | JSON 字段、类型或语义契约变化 | 人工决定 |
| `golden_version` | 人工标注或标注政策应用结果变化 | 人工决定 |

版本继续使用两段式数字，例如 `1.0`、`1.1`、`2.0`。Git Commit 不能触发自动递增：一个 Commit 可能只改文档、测试或多个对象，无法推断应该升级哪一种版本。

CI 后续可以做的是校验，而不是代替人决定版本。例如：

- Golden 内容变化但 `golden_version` 没变时失败；
- Prompt 内容变化但 `prompt_version` 没变时失败；
- Schema 内容变化但固定版本没变时失败。

### 7.2 哪些身份自动生成

每次真实抽取自动生成新的 `run_id`，即使 Document、Prompt、模型和参数完全相同，也不能复用上次 Run ID。当前 Run ID 使用可读前缀、UTC 标签和随机后缀，因此每次运行会产生新文件名。

版本号描述“使用了哪一版规则”，Run ID 描述“这是哪一次运行”。两者不能互相替代。

当前写文件仍依赖唯一 Run ID 避免碰撞。若要从机制上保证任何已有文件都不被覆盖，后续保存入口还应使用独占创建或在目标已存在时直接失败。这个不可变写入检查尚未实现。

模型参数、Parser、Normalizer、Validation Policy、Evaluator 和 Chunk Strategy 不属于 Prompt 版本。它们需要独立字段或配置哈希，但具体 Manifest 字段仍待设计。

## 8. 可比性和可复现性暂不设强门槛

现阶段不要求模型重跑产生相同 JSON，也不设置“多数指标必须提升”之类的自动门禁。先记录足够信息：

```text
Document 路径与 content_hash
Golden 路径、版本与内容哈希
模型和 Provider
Prompt 版本与内容哈希
模型参数
Chunk Strategy 和参数
Schema、关系矩阵、Evaluator 版本
Run ID、Evaluation Run ID
代码 Commit SHA
执行时间、token、成本和时延
原始响应是否安全保存
```

这些记录用于解释历史结果，不承诺模型输出完全相同。是否增加重复运行、均值、方差或性能阈值，等样本和评测政策稳定后再决定。

Provider Raw Response 若不含密钥、隐私和私有链接，可以随被选中的实验脱敏归档；默认不上传完整请求会话。Codex/聊天会话不是模型抽取的输入工件，也不应作为实验复现的必要条件。

## 9. 对同步开发的影响

本次是文档 PR，不修改运行行为，对正在进行的前端图谱、Neo4j、智能报告、多维查询、关键路径和动态更新没有代码影响。

后续实现的影响按阶段控制：

| 后续改动 | 主要影响方 | 暂不影响 |
| --- | --- | --- |
| 文档级评测器和指标 | LLM、QA、后端 | 前端图谱、Neo4j 同步 |
| Experiment Manifest | LLM、QA、报告组 | SQLite canonical graph、Neo4j 图事实 |
| 切块消融 runner | LLM、后端 | Golden 人工标注内容 |
| 评测 API/页面 | 后端、前端、QA | canonical graph 写入规则 |
| 图谱犯罪团伙分析 | LLM、后端、Neo4j、报告组 | Golden 版本和评测真值 |

跨组字段变更仍然先改契约，再通知架构与数据规范组评审。

## 10. 状态清单

已经确认：

- 每篇 Golden 对应一篇完整 Document；
- 人工按全文审阅，不做人为算法切块；
- 当前六份 Golden 结构上都是全文单 chunk；
- Chunk Strategy 属于 Run 配置；
- 版本号人工递增，Run ID 每次自动生成；
- 普通运行不上传，只有有实验价值的记录才通过 PR 归档；
- 可复现性现阶段只做记录，不设强门槛；
- SQLite/Neo4j、前端 API 边界不变。

仍待评审：

- 多证据 span 如何表达跨段关系；
- 文档级 Golden v2 的具体 Schema；
- Experiment/Dataset Manifest 的字段和目录；
- Provider Raw Response 的脱敏和归档规则；
- 不可变文件写入和版本未递增校验；
- 评测指标二审稿中的匹配、空集和拒绝计分细节；
- 何时引入重复运行和性能门槛。

本阶段不做：

- 不迁移六篇 Golden；
- 不清理旧 Extraction/Evaluation 文件；
- 不自动导出聊天会话；
- 不因为 Commit 变化自动升级版本；
- 不让 Neo4j 承担实验运行或 Golden 的事实源职责。

## 11. 推荐的后续小 PR

1. 本文档 PR：只确认术语、全文标注和指标二审范围。
2. 指标契约 PR：二审通过后修改评测器和测试，不同时改目录。
3. Experiment Manifest PR：只定义选择、归档和不可变校验。
4. 切块实验 PR：文档级评测可用后，再比较全文、无重叠和重叠策略。

每个 PR 只解决一个可验证问题，减少对其他同学同步开发的干扰。
