# LLM Golden、实验归档与切块评测决策

日期：2026-07-15
状态：LLM 组负责人已确认（决策版本 1.0）；跨组契约和代码改动按后续 PR 评审
影响范围：Golden 标注、抽取运行、实验归档、版本记录和后续切块实验

本文冻结 LLM 组对 Golden 标注范围、实验归档和评测口径的阶段决策，并区分“已确认决策”和“已经实现”。本文不表示未来目录、Manifest 或新评测器已经落地；涉及 QA 标注手册、JSON Schema、后端接口或数据迁移的改动仍需由对应负责人在后续 PR 中评审。

## 0. 决策方法：先确认目标，再选择实现

每个结论必须沿下面的链路检查：

```text
课程硬要求 / 产品目标 / 学习项目目标
  -> 系统必须具备的能力
  -> 当前数据和代码能否提供证据
  -> 至少两个可选方案及代价
  -> 团队确认目标和取舍
  -> 更新契约
  -> 实现和验收
```

如果课程目标、数据规模或跨组契约发生变化，应通过新的决策记录修订本文，不能只改实现后反推口径。

本文使用五种状态：

| 状态 | 含义 | 能否直接约束开发 |
| --- | --- | --- |
| 已验证事实 | 可由当前代码、数据、Git 历史或测试直接证明 | 可以作为分析输入 |
| 现行约束 | 已写入仓库级 `AGENTS.md` 或已合入契约 | 可以，变更需走契约评审 |
| 已确认决策 | LLM 组本阶段采用的目标和取舍 | 可以约束 LLM 组后续实现；跨组改动仍需对应负责人评审 |
| 目标假设 | 团队希望项目达到的效果，但仍可能被质疑 | 不可以，需先达成目标共识 |
| 候选方案 | 为某个目标提出的实现方式 | 不可以，需比较替代方案和证据 |

### 0.1 目标与来源证据

| 目标 | 来源证据 | 能推出什么 | 不能直接推出什么 |
| --- | --- | --- | --- |
| G1：完成“采集→实体识别→关系抽取→行为分析→知识图谱→报告”链路 | `docs/references/course-requirements.md` 第三题实验目标 | 抽取、图谱和报告都必须有可演示闭环 | 不直接规定 Golden 文件结构、目录或指标公式 |
| G2：支持多维查询、关联路径、动态更新和图谱可视化 | 课程要求第三题 4.a～4.d | canonical graph 必须稳定，Neo4j/查询层要能消费已校验事实 | 不要求 Neo4j 成为事实源，也不要求评测结果进入 Neo4j |
| G3：报告包含完整画像、行为模式和证据 | 课程要求第三题第 5 模块；`docs/architecture.md` 的证据链原则 | 实体、关系和分析结论需要可追溯证据 | 不直接要求保存每次模型原始响应或所有本地尝试 |
| G4：把提示词、切块和校验优化沉淀为课程实验过程 | 当前团队的学习项目定位，课程总报告要求说明实验方法和结果 | 有价值的对照实验应能被复盘 | 是否全部入 Git、保留哪些工件仍是团队取舍，不是课程硬条文 |
| G5：产品运行和图查询不因实验方案变化失去一致性 | 仓库 `AGENTS.md` 与 `docs/architecture.md` | SQLite 保持 canonical graph，Neo4j 是可重建投影，前端只走 FastAPI | 不决定 Golden 是全文还是局部，也不决定评测 matcher |

### 0.2 由目标推出的取舍

| 结论 | 依赖的目标 | 当前证据 | 替代方案 | 当前状态 |
| --- | --- | --- | --- | --- |
| 单篇 Document 对应一份 Golden，多篇由 Dataset 编组 | G3、G4 | 现有六份 Golden 均为单文档；逐文档错误更易审阅 | 一个文件包含多篇 Golden | 已确认；Dataset Manifest 另行设计 |
| 人工按全文标注，不按算法 chunk 标注 | G4，以及“比较切块策略”的实验目标 | 全文真值可比较不同切块并保留跨段关系 | 只标指定范围，并显式保存 `covered_spans` | 已确认采用全文方案；切块实验为 P1，不阻塞 P0 |
| 只把有实验价值的运行提交 Git | G4 | 能控制仓库体积并保留关键对照 | 全部运行入 Git；或只保留最终 Baseline | 已确认；普通调试运行留在本地 |
| Raw Semantic 与 Validated 分开计分 | G3、G4 | 当前把全部 rejected 直接计 FP，会混淆模型和校验器责任 | 只报告最终候选 F1 | 已确认；计算规则见指标契约 |
| `run_id` 是运行身份，文件名是可读标签 | G3、G4 | PR #35 已实现随机后缀与 UTC 标签；PR #41 已合入一致性校验 | 时间戳或文件名充当唯一身份 | 已合入 `main` |
| SQLite canonical graph、Neo4j 可重建投影 | G2、G5 | 已写入仓库级约束和架构文档 | Neo4j 直接作为唯一事实源 | 现行约束，除非发起跨组架构变更 |

## 1. 先把几个名称说清楚

前面的讨论中出现过“Dataset / Experiment Manifest 编组”一词。它不是 “dist experiment 演变组”，也不是一种新的 Golden。

本文使用下面这些名称避免讨论歧义；新增数据对象是否进入机器可读契约仍需单独的 Schema PR：

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

当前 `main` 使用以下目录和运行产物边界：

```text
data/documents/<target_group>/<doc_id>.json
data/golden/golden-<language>-<doc_id>-<schema_version>-<golden_version>.json
data/extracted/extract-<...>.json
data/extracted/extract-<...>-candidate-audit.json
data/evaluation/evaluation_result-<...>.json
data/run_logs/run-log-<run_id>.json        # 本机运行摘要，默认不入 Git
data/threatgraph_osint.db
```

PR #35 和 PR #41 已经统一新运行的版本字段、UTC 标签、带随机后缀的 `run_id`，并补充文件名与 payload 的一致性校验。当前正式命名为：

```text
data/extracted/extract-<doc_id>-<model>-<prompt_version>-<schema_version>-<timestamp>-<run_suffix>.json
data/extracted/extract-<doc_id>-<model>-<prompt_version>-<schema_version>-<timestamp>-<run_suffix>-candidate-audit.json
data/evaluation/evaluation_result-<doc_id>-<model>-<prompt_version>-<schema_version>-<golden_version>-<timestamp>.json
data/golden/golden-<language>-<doc_id>-<schema_version>-<golden_version>.json
```

截至 2026-07-16 的 `main`，PR #49、#51、#53、#54、#62、#63、#64 和 #45 还带来以下 LLM 相关现状：

- `scripts/run_llm_extraction.py` 默认写出 `data/run_logs/run-log-<run_id>.json`，记录阶段耗时、API 调用次数、Token 和重试摘要；该目录是本地运行产物，不是 Git 归档的 Experiment Manifest。
- P0 Pipeline 已收敛为手动 `extract_and_build` 复合任务，状态落 SQLite，默认只消费已有审核抽取结果，不把 `use_cache=false` 当作调用外部模型授权。
- `DEFAULT_PROMPT_VERSION` 已升级为 `extract-v7`，默认提示词来自 `docs/prompts/extract-v7.md`；Extraction Schema 和工件命名校验已允许 `extract-v<N>` 形式的 prompt 版本。
- LLM 服务已收敛长输出重试策略、支持 URL/defang 证据匹配回退，并把单轮输出上限提高到最多 80 个实体和 80 个关系。
- 当前评测器已合入 http/defang 归一化和仅限 `MALWARE`/`TOOL` 的文件扩展名匹配；这属于旧评测器的局部匹配改进，不等于本文定义的 Raw Semantic/Validated 双作用域指标已经实现。
- `data/evaluation/` 当前只保留符合新命名的评测结果；旧式 `evaluation_result.*.extract-vN.json` 不再作为当前运行工件保留在该目录。
- `docs/evaluation/llm-extraction-versions/` 已归档 v1 到 v7 的历史提示词、代码快照、抽取结果、候选审计、Golden 副本和评测结果。该目录是历史复盘材料，不是当前运行工件目录或 Experiment Manifest。

因此，`Promoted Experiment` 已被选作 Git 归档策略，但目前还不是独立运行环境。当前仍没有以下能力：

- 没有 `data/runs/<run_id>/`；
- 没有 `data/experiments/<experiment_id>/manifest.json`；
- 没有 promote 命令或 `promoted` 状态字段；
- 没有自动把普通运行整理成 Baseline 的流程。

在 Manifest 落地前，由 PR 描述说明实验问题、引用工件和结论。运行日志可以作为排查和复盘材料，但不能替代 Dataset/Experiment Manifest。

### 2.1 PR #36 的方案来源与演进

PR #36 不能以当前提交形态整体合入：它基于旧父分支，包含多文档 Golden、全局 index/catalog、Candidate Audit 新 Schema、Docker/CI 自动同步等尚未冻结的边界，并且与当前 `main` 冲突。它同时也是后续 PR #41 与本文的关键方案来源，应保留可追溯关系，而不是简单描述为“被替代”。

| PR #36 提议 | PR #41 / 本文的处理 |
| --- | --- |
| 统一工件身份、版本、UTC 标签、文件名与 payload 一致性 | PR #41 继承并加固，增加随机后缀 Run ID 与跨工件绑定校验 |
| Candidate Audit 与 Extraction 绑定及独立契约 | 绑定已由 PR #41 继承；独立 Schema 延后到后续拆分 PR |
| 多文档评测编组 | 从“多文档 Golden 文件”调整为“单文档 Golden + Dataset Manifest” |
| catalog/index 支持发现和复现 | 目标保留；catalog 改为由权威工件派生的视图，Manifest 作为显式编组 |
| 保存运行历史 | 从“全部工件入 Git”调整为“Promoted Experiment 经 PR 归档” |
| CI/Docker 数据一致性 | 目标保留；CI 只校验不直推 main，Docker 使用明确 fixture/挂载 |
| Legacy 工件可发现 | 目标保留；正式输入默认严格，宽 Glob 仅用于 catalog 或迁移盘点 |

后续 Candidate Audit Schema、Dataset/Experiment Manifest、派生 catalog 和 CI 校验拆分 PR 应回链 PR #36。若实际复用 PR #36 的代码，应保留原作者提交，或按实际贡献添加共同作者信息。

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

## 4. 决策：Golden 按整篇 Document 标注

### 4.1 方案 A：完整 Document 标注

本阶段采用完整 Document 标注。人工读取完整 `clean_text`，不按算法策略人工切块；标注员在当前本体、关系矩阵和标注政策范围内检查整篇文章。这样既能支撑当前文档级评测，也为后续全文、无重叠和重叠切块的探索性对比保留同一真值。

这条规则解决两个问题：

1. Golden 不随算法切块策略变化。全文、无重叠切块和重叠切块可以使用同一份答案比较。
2. 人工可以识别跨自然段关系。算法切块是否破坏这类关系，正是后续实验要测量的问题，不能在标注阶段先把它删掉。

“完整标注”包含两层含义：

- 范围完整：整篇 `clean_text` 都经过人工审阅；
- 政策内完整：凡是当前实体类型、关系类型和标注政策要求记录的事实，都应进入 Golden。

在方案 A 下，如果某段没有人工审阅，这份 Golden 就不是正式的全文 Golden，也不能晋升全文 Baseline。不能一边称其为“标全”，一边把遗漏区域默认排除在评分之外。

### 4.2 本阶段未采用：显式范围标注

显式范围标注仍是未来数据量扩大后的备选方案。若采用，必须同时提供机器可读的 `covered_spans` 或等价字段，并把预测和评分严格限制在相同范围。它的优点是人工成本较低，缺点是无法直接评价全文召回、跨段关系和切块造成的结构损失。

Golden v1 没有正式的覆盖范围字段，因此当前不能仅凭 `chunks[]` 猜测“哪些正文未标注但不计分”。选择方案 B 需要先改 Schema、标注工具和评测器，不能只改标注说明。

### 4.3 “没有标”的内容怎么处理

需要区分三类情况：

| 情况 | 含义 | 处理方式 |
| --- | --- | --- |
| 已审阅且属于标注范围 | 当前本体和政策要求记录的事实 | 必须标注；漏标是 Golden 缺陷 |
| 已审阅但政策明确排除 | 署名作者、页面维护者、无法用当前类型表达的文件工件等 | 在标注政策或 `notes` 中说明 |
| 未审阅 | 标注员没有检查的正文范围 | 方案 A 下不得作为全文 Golden；方案 B 下必须落入显式范围之外 |

模型输出政策明确排除、但仍能映射到当前 Schema 的内容时计为语义 FP；Schema 无法表达的对象只进入审计。这个边界不能用“没有出现在 Golden”一句话自动处理。

### 4.4 当前 6 篇 Golden 的真实结构

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

### 4.5 跨段关系

方案 A 下，关系两端可以出现在不同自然段，不能因为未来算法可能把它们切到不同块就删除关系。方案 B 是否覆盖该关系，取决于已声明范围；不能在没有范围字段时临时决定计分与否。

Golden v1 只有一个连续的 `evidence_text` 和一组 `[char_start, char_end)`。如果一条关系需要两处不相邻证据，当前可选办法只有：

1. 选择能独立证明关系的最小连续上下文；
2. 用一个较长的连续范围覆盖两处证据及中间文本；
3. 若前两种都不能准确表达，在 `notes` 中记录，等待多证据 span 契约。

Golden v1 继续使用一个连续证据范围；无法准确表达的多段证据写入 `notes` 并进入后续复核。本次文档 PR 不改 Golden v1，`evidence_spans[]` 留作 Golden v2 的候选能力。

## 5. 决策：切块属于算法运行

切块消融列为 P1 探索实验，不阻塞 P0 课程验收。Chunk Strategy 是 Extraction Run 配置，不进入 Golden 身份；同一实验使用同一批 Document 和同一批全文 Golden：

```text
A：整篇输入
B：无重叠切块
C：重叠切块
```

每组预测都要先把 chunk 局部位置还原为 Document 全文位置，再按文档聚合和去重，最后与全文 Golden 比较。不能拿 Golden 的 v1 `chunk_id` 充当语义匹配主键。

切块实验至少回答两个问题：

1. 结构上有多少 Golden 关系能被任意一个 chunk 同时覆盖两端证据；
2. 在结构上可见的前提下，模型实际抽取出了多少关系。

切块实验必须增加一个不依赖模型的上界指标：

```text
relation_chunk_coverage_upper_bound
  = 至少有一个 chunk 能覆盖关系所需证据的 Golden 关系数
    / Golden 关系总数
```

如果第一段和第三段的关系跨度大于 overlap，单纯增加重叠仍可能无法恢复。后续可以比较全文复核、实体聚合后的二次关系抽取或检索式关系配对，但这些属于新的实验变量。

当前评测器仍按相同 `chunk_id` 匹配实体和关系，尚不能严谨执行上述实验。这是已验证的实现阻塞：开展 P1 切块实验前，需把匹配主键改为 Document 身份和全文坐标，并先用固定真值表验证。

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

后续 Manifest PR 可以评审以下目录；本决策不冻结目录名：

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

Schema 和 Golden 版本继续使用两段式数字，例如 `1.0`、`1.1`、`2.0`。Prompt 版本允许仓库当前使用的 `extract-v<N>` 格式，例如 `extract-v7`。Git Commit 不能触发自动递增：一个 Commit 可能只改文档、测试或多个对象，无法推断应该升级哪一种版本。

CI 后续可以做的是校验，而不是代替人决定版本。例如：

- Golden 内容变化但 `golden_version` 没变时失败；
- Prompt 内容变化但 `prompt_version` 没变时失败；
- Schema 内容变化但固定版本没变时失败。

### 7.2 哪些身份自动生成

每次真实抽取自动生成新的 `run_id`，即使 Document、Prompt、模型和参数完全相同，也不能复用上次 Run ID。当前 Run ID 使用可读前缀、UTC 标签和随机后缀，因此每次运行会产生新文件名。

版本号描述“使用了哪一版规则”，Run ID 描述“这是哪一次运行”。两者不能互相替代。

当前写文件仍依赖唯一 Run ID 避免碰撞。若要从机制上保证任何已有文件都不被覆盖，后续保存入口还应使用独占创建或在目标已存在时直接失败。这个不可变写入检查尚未实现。

模型参数、Parser、Normalizer、Validation Policy、Evaluator 和 Chunk Strategy 不属于 Prompt 版本。它们需要独立字段或配置哈希，但具体 Manifest 字段仍待设计。

## 8. 决策：可比性和可复现性暂不设强门槛

本阶段不要求模型重跑产生相同 JSON，也不设置“多数指标必须提升”之类的自动门禁，而是先记录足够信息：

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

## 10. 状态清单与实施门槛

已验证事实：

- 当前六份 Golden 结构上都是全文单 chunk；
- 当前 runner 仍把工件平铺到 `data/extracted/` 和 `data/evaluation/`；
- 当前没有 Dataset/Experiment Manifest、promote 命令或独立 Experiment 环境；
- 当前默认 Prompt 为 `extract-v7`，Schema/命名校验允许 `extract-v<N>`；
- 当前评测器已有 http/defang 和类型限定的扩展名匹配改进，但仍依赖相同 `chunk_id`，并把 Candidate Audit 中 rejected 项直接加入预测数量；
- PR #35 已实现两段式版本、UTC 标签和随机后缀 Run ID；
- v1 到 v7 的历史抽取评测材料已归档到 `docs/evaluation/llm-extraction-versions/`，不等同于 Manifest；
- 现有代码和 Schema 没有 `Track` 或 `Treaty` 正式对象。

现行项目约束：

- SQLite 是运行时 canonical graph；
- Neo4j 是可从 SQLite 重建的查询投影；
- 前端只通过 FastAPI 获取数据；
- LLM 原始输出不能直接进入 Neo4j 或正式图谱。

已确认的阶段决策：

- 每篇 Document 使用一份全文 Golden，多篇由 Dataset 编组；
- 切块是 Extraction Run 配置，P1 再做全文、无重叠和有重叠三组探索实验；
- 普通调试运行保留在本地，只有有结论的 Promoted Experiment 经 PR 归档；
- 可复现性先记录版本、哈希、参数、Commit、成本和时延，不要求非确定性输出逐字一致；
- Raw Semantic 与 Validated 必须分开报告，Accepted Graph 指标留作后续可选范围；
- Golden v1 继续使用一个连续证据范围，多证据 span 延后到 Golden v2；
- 匹配、空集、Rejected、Duplicate 和 Parse Failure 按指标契约第 14 节执行；
- 六篇 Golden 的结果只用于探索性结论，不设置强性能门槛。

后续独立实现与跨组支持：

- LLM 组先用固定真值表补评测器测试，再实现文档级 matcher、双作用域指标和审计指标；
- QA 组同步全文标注手册，并对六份 Golden 做语义完整性复核；本 PR 不代改数据；
- 架构或后端负责人评审涉及 Golden Schema、评测结果 Schema 和持久化入口的变更；
- Dataset/Experiment Manifest、不可变写入、Provider Raw Response 脱敏归档均为后续独立 PR；
- P1 切块实验必须等待文档级评测器可用，不调用付费 API 预跑未冻结实验。

不被后续实现阻塞的工作：

- PR #41 已合入的工件命名与 payload 一致性校验；
- SQLite canonical graph 到 Neo4j 的可重建同步；
- 基于现有 API 契约的前端图谱、查询和报告页面；
- 不改变本文指标语义的 LLM 调用、解析稳定性、Prompt 迭代和错误观测。

本阶段不做：

- 不迁移六篇 Golden；
- 不清理旧 Extraction/Evaluation 文件；
- 不自动导出聊天会话；
- 不因为 Commit 变化自动升级版本；
- 不让 Neo4j 承担实验运行或 Golden 的事实源职责。

## 11. 推荐的后续小 PR

1. 评测器 PR：先提交固定真值表测试，再实现文档级 matcher、Raw/Validated 和审计指标，不同时改目录。
2. QA 契约 PR：同步全文标注手册并记录六份 Golden 的人工复核结果，不由 LLM 组直接改写 Golden 数据。
3. Experiment Manifest PR：定义 Dataset、Promoted Experiment、Baseline 引用和不可变校验。
4. 切块实验 PR：文档级评测可用后，再比较全文、无重叠和有重叠策略。

每个 PR 只解决一个可验证问题，减少对其他同学同步开发的干扰。
