# 优先级与阶段路线

> 适用范围：ThreatGraph-OSINT 多人协作开发
> 目的：区分功能优先级和每日推进阶段，避免把 P0/P1/P2 误用为开发顺序。
> 日期：2026-07-07

## 1. 命名结论

优先级使用 `P0/P1/P2`，只表示重要性。

```text
P0：项目必须完成的最基本要求
P1：基本属于加分项，但能明显提升答辩质量
P2：可选做的工作，时间不足时可以只写入后续展望
```

阶段使用 `Step 0/Step 1/Step 2...`，可以在表格里简写为 `S0/S1/S2`。

不建议使用 `T1/T2`，因为 `T` 容易和 Task、Test、Time 混淆。`Step` 更适合表达“每天逐步集成”的开发节奏。

当前完成状态和最近任务以根目录 [TODO.md](../TODO.md) 为准。本文件只解释阶段定义和验收标准。

## 2. 当前 Step 状态

### Step 0：脚手架和 Mock 闭环

状态：已完成。

已经具备：

1. Docker Compose 基础运行方式。
2. FastAPI 后端脚手架。
3. SQLite 初始化和 demo seed 数据。
4. React TypeScript 前端脚手架。
5. 前端直接调用后端 API。
6. 基于 Mock/seed 数据完成前后端打通。

Step 0 的意义是证明“前后端和数据层能连起来”，但它还不是最终 MVP。

原因：

1. 数据仍然是 Mock/seed，不是课程样本资料。
2. LLM 抽取链路还没有接入。
3. 证据链、归一化、评测和报告结构还需要继续补。

## 3. 后续 Step 划分

### Step 1：真实样本文档闭环

目标：把 Mock 数据替换为可追溯的真实样本文档。

输入：

```text
本地文本文件或 document.json
```

输出：

```text
extraction_result.json
SQLite documents/chunks/extracted_*
SQLite entities/relations/evidence
data/graph/graph.json
基础报告 markdown
```

验收标准：

1. 至少 1 个目标组织使用真实样本文档。
2. 能从文档中抽取候选实体和候选关系，可以先用 mock LLM 输出。
3. 候选结果进入 `extracted_entities`、`extracted_relations`。
4. 归一化后进入 `entities`、`relations`、`evidence`。
5. 前端图谱、实体详情、证据展示仍然能工作。
6. 能导出 `graph.json`。

不要求：

1. 不要求爬虫平台。
2. 不要求三类来源都接入。
3. 不要求 Neo4j。
4. 不要求完整报告结构化。

### Step 2：P0 MVP 闭环

目标：形成团队可复现、可继续开发的最小产品。

必须具备：

1. 至少 1 个目标组织端到端跑通。
2. SQLite 作为唯一事实源。
3. `document.json`、`extraction_result.json`、`graph.json` 契约稳定。
4. LLM 候选层和正式图谱层分离。
5. 实体类型、关系类型、证据字段完成基础校验。
6. FastAPI 提供图谱、实体详情、报告接口。
7. 前端通过 API 展示图谱、实体详情、证据和报告。
8. 其他组员能按 README 复现。

Step 2 完成后，才可以称为 MVP。Step 0 只能称为 Demo 或脚手架闭环。

### Step 3：课程验收闭环

目标：覆盖课程要求中的核心验收项。

建议完成：

1. 覆盖 APT28、Lazarus、Kimsuky 三个目标组织。
2. 覆盖至少三类来源：安全报告/安全博客/CERT、新闻/政府公告、社媒/论坛整理文本。
3. 实现三类来源的最小采集入口，可以是本地样本、单页抓取、RSS/feed。
4. 完成基础 MITRE ATT&CK 映射。
5. 完成行为模式分析。
6. 完成结构化威胁报告。
7. 展示基础评测结果。

### Step 4：P1/P2 增强

目标：提高系统表现力和创新性。

可选内容：

1. Neo4j 同步和多跳路径查询。
2. 结构化报告 sections。
3. 增量采集、采集重试和 checkpoint。
4. STIX 2.1 子集导入导出。
5. MISP/OpenCTI 兼容输出。
6. GraphRAG 风格的子图摘要或自然语言问答。
7. 插件式采集器和 enrichment analyzer。

## 4. 优先级归属

### P0：项目最基本要求

P0 不等于 Step 0。P0 是最终必须完成的最小能力集合。

P0 包含：

1. 本地文档或 `document.json` 导入。
2. 文档、切块、候选抽取、正式图谱、证据链的 SQLite 存储。
3. LLM 候选层和正式图谱层分离。
4. 实体类型、关系类型和证据字段基础校验。
5. `graph.json` 导出。
6. FastAPI 图谱和报告接口。
7. React 图谱、详情、证据和报告展示。
8. 至少 1 个目标组织端到端可复现。

### P1：加分项

P1 包含：

1. 三个目标组织完整覆盖。
2. 三类来源最小采集入口。
3. MITRE ATT&CK 映射。
4. 行为模式分析。
5. 基础评测。
6. Neo4j 同步和多跳路径查询。
7. 结构化报告章节。

### P2：可选做

P2 包含：

1. 完整采集调度。
2. 增量更新和自动触发流水线。
3. STIX / MISP / OpenCTI 兼容导入导出。
4. GraphRAG 风格问答。
5. 插件式 enrichment。
6. 更严格的 schema/rule 推理。

## 5. 并行开发契约

并行开发不是等所有系统都搭好，而是先冻结契约。

最低并行契约：

```text
data -> document.json -> llm / be
llm -> extraction_result.json -> be
be -> graph.json -> fe / qa
qa -> report.md 或 report.json -> fe / 答辩材料
```

建议每个契约都至少提供一个固定样例。样例一旦被 fe、be、llm 共同使用，字段变更必须先同步架构与数据规范组。

## 6. Demo 和 MVP 区别

Demo 用来证明“能跑”。

```text
可以只跑一个样本
可以有手动步骤
可以使用 mock
可以只在个人机器上稳定
重点是演示概念
```

MVP 用来证明“团队可以交付和继续开发”。

```text
代码、样本和运行说明进入仓库
其他组员能复现
输入输出契约稳定
核心链路不依赖口头解释
至少覆盖一个目标组织的端到端流程
有清楚的失败边界和降级策略
```

因此，Step 0 是 Demo/脚手架闭环。Step 2 达到验收标准后，才算 MVP。

## 7. 对当前架构的调整判断

当前架构不需要推翻。

应当在开工前定清楚的点：

1. `document.json`、`extraction_result.json`、`graph.json` 契约。
2. `documents`、`extracted_*`、`entities/relations/evidence` 的归属。
3. LLM 输出只进入候选层，不能直接进入正式图谱。
4. 实体类型、关系类型和关系合法性校验。
5. 证据链字段必须贯穿图谱、API 和报告。

不应过早引入的点：

1. 完整 STIX 2.1。
2. OpenCTI/MISP 式重平台能力。
3. TypeDB 作为主数据库。
4. GraphRAG 完整社区发现和问答框架。
5. 大规模爬虫和外部 API 插件生态。

结论：保留 SQLite + graph.json + FastAPI + React + Neo4j 增强的主架构。初期重点不是换数据库，而是把数据边界、候选层、正式层和证据链定清楚。
