# To-Do List

> `P0/P1/P2` 表示优先级，`Step/S0/S1` 表示执行顺序。完整说明见 [docs/stage-roadmap.md](docs/stage-roadmap.md)。

## 优先级说明

```text
P0：课程验收必须完成的核心链路
P1：不阻塞核心链路，但能明显提升答辩质量的增强
P2：可选做的工作，时间不足时可以只写入后续展望
```

P0 按课程要求包含三类来源采集与预处理、三个目标组织、LLM NER/RE、归一化与证据、行为/MITRE、图谱查询与可视化、五章节结构化报告。评测在 P0 只保留固定开发集的最小结果；完整评测平台、Neo4j、切块消融和自动 catalog 不阻塞 P0。

## 组别与任务标签说明

五个正式小组：

```text
arch：架构与数据规范组，负责 schema/API 契约、字段归属、Mock 样例、后端骨架和集成对齐。
data：数据与样本组，负责真实资料、文本清洗、样本文档、golden.json 和来源记录。
llm：LLM 抽取与分析组，负责 Prompt、合法 JSON 输出、候选抽取、重试和分析结果。
fe：图谱与前端组，负责图谱展示、交互、实体详情、报告页面和接入真实接口。
qa：报告答辩与测试组，负责质量门禁、验收记录、报告/PPT、演示脚本和视频。
```

补充任务标签：

```text
be：后端横向工作流，表示 FastAPI、SQLite、API、归一化、导出等后端开发工作；不是单独小组，默认由 arch 牵头，其他组按业务边界认领。
qa：质量门禁、验收测试、报告和答辩相关工作。
```

## 当前进展总览

- [x] **Step 0：搭建 S0 项目脚手架** `P0`
- [ ] **Step 1：真实样本文档闭环** `P0`
- [ ] **Step 2：P0 MVP 闭环** `P0`
- [ ] **Step 3：课程验收闭环** `P0`
- [ ] **Step 4：增强能力** `P1`
- [ ] **Step 5：可选扩展** `P2`

## 验收状态口径

```text
未开始：尚无可执行产物
代码已实现：有实现和回归测试，但未完成课程固定样本验收
已有数据：已有真实 Document/Extraction/Golden，但未证明端到端可复现
已集成验证：已用固定样本和独立 SQLite 留下可重复的验收证据
已准备答辩材料：已有演示命令、失败降级、截图/录像时点和限制说明
```

| 课程核心项 | 当前状态 | 下一个验收证据 |
| --- | --- | --- |
| 三类来源与中英文 Document | 已有数据 | 覆盖检查命令和三类采集/转换记录 |
| Document 导入、切块和 Pipeline | 已集成验证后半链路 | 三类来源上游接入同一任务 |
| LLM 候选抽取 | 已集成验证 `reviewed` | 保留 `live` 作为显式可选现场演示 |
| 归一化、SQLite 图谱、证据与路径 API | 已集成验证后端三样本 | 三组织前端切换和浏览器验收 |
| 行为模式与 MITRE | 代码已实现基础规则 | 真实 MITRE 映射和 `evidence_ids` |
| 三组织五章节报告 | 代码已实现 | 强制规则模式与三组织集成验收 |
| 开发集最小评测 | 已有数据 | 统一标记为 development / exploratory，移除前端 Mock 指标 |
| 课程答辩材料 | 未开始 | 验收矩阵、20 分钟演示脚本和降级路径 |

## Step 0：搭建 S0 项目脚手架 `P0`

目标：证明前端、后端和 SQLite 能通过 Mock/seed 数据连起来。该阶段已经完成，只作为后续工作的基础。

1. [x] **S0.1 工程容器与启动方式**（be / fe / qa）
   - [x] 提供 Docker Compose 基础运行方式。
   - [x] 后端容器能启动 FastAPI 服务。
   - [x] 前端容器能启动 Vite 开发服务。
   - [x] 数据目录能挂载到本地，便于保留 SQLite 文件。

2. [x] **S0.2 后端基础服务**（be）
   - [x] 建立 FastAPI 应用入口。
   - [x] 提供健康检查接口。
   - [x] 初始化 SQLite demo seed 数据。
   - [x] 提供图谱、实体、报告相关基础 API。

3. [x] **S0.3 前端基础页面**（fe）
   - [x] 建立 React + TypeScript + Vite 脚手架。
   - [x] 接入后端 API，而不是只读前端本地常量。
   - [x] 展示基础图谱视图。
   - [x] 展示实体详情和基础报告内容。

4. [x] **S0.4 Mock 数据闭环**（be / fe / qa）
   - [x] seed 数据能覆盖节点、关系和报告。
   - [x] 前端能基于 seed 数据渲染主要页面。
   - [x] 后端测试能通过。
   - [x] 前端构建能通过。

5. [x] **S0.5 新成员上手说明**（arch / qa）
   - [x] README 保留项目介绍和运行入口。
   - [x] 阶段路线单独放入 `docs/stage-roadmap.md`。
   - [x] 当前任务单独放入根目录 `TODO.md`。

## Step 1：真实样本文档闭环 `P0`

目标：先不依赖爬虫平台，用本地文本或 `data/documents/<target_group>/*.json` 跑通真实样本文档到候选抽取、正式图谱和前端展示的闭环。

1. [x] **S1.1 冻结三份并行开发契约**（arch / be / fe / llm）
   - [x] 确定 `document.json` 的必填字段、可选字段、`schema_version` 和样例文件。
   - [x] 确定 `extraction_result.json` 的候选实体、候选关系、候选状态、校验结果、证据文本和 `confidence` 字段。
   - [x] 确定 `graph.json` 的 `nodes`、`edges`、`evidence`、`analysis`、`exported_from` 和 `source_of_truth` 字段。
   - [x] 明确字段归属：哪些字段属于文档层、候选层、正式图谱层和分析层。
    - [x] 明确实体类型、关系类型和最小合法关系矩阵。
    - [x] 同步已确认的本体决策：删除 `TARGET`，增加 `INFRASTRUCTURE`、`LOCATION`、`FINANCIAL_ACCOUNT` 及犯罪网络关系。
   - [x] 给每份 JSON 放入至少 1 个可直接复用的样例。

2. [x] **S1.2 准备第一份真实样本文档**（data / qa）
   - [x] 已覆盖 APT28、Kimsuky、Lazarus 真实样本。
   - [x] 已保留厂商报告、安全新闻和社媒/论坛公开数据。
   - [x] MITRE ATT&CK、MISP Galaxy 等知识库仅作为 reference / golden 参考。
   - [x] Document 保留清洗正文、来源 URL、发布时间、语言、目标组织和清洗 provenance。
   - [x] 证据片段在抽取工件中可回溯到 Document 正文。
   - [x] 真实清洗结果已放入 `data/documents/<target_group>/*.json`。

3. [x] **S1.3 接入文档导入和切块**（be / data）
   - [x] `POST /api/v1/documents/import` 可写入 `documents`。
   - [x] 后端将导入文档切分为 `chunks`。
   - [x] 保留 `doc_id`、`chunk_id`、`source_url`、`language` 和 `target_group`。
   - [x] 重复 `doc_id` 或 `content_hash` 返回可识别的已存在结果。

4. [x] **S1.4 生成候选抽取结果**（llm / be）
   - [x] 先用 mock LLM 输出或手写 `extraction_result.json` 跑通流程。
   - [x] 提供 DeepSeek V4 / OpenAI-compatible 真实 API 抽取、预检和失败重试入口。
   - [x] 候选实体写入 `extracted_entities`，不直接写入正式 `entities`。
   - [x] 候选关系写入 `extracted_relations`，不直接写入正式 `relations`。
   - [x] 每个候选实体和候选关系都要带 `chunk_id`、`evidence_text` 和 `confidence`。
   - [x] 记录抽取运行信息到 `extraction_runs`。

5. [x] **S1.5 归一化为正式图谱**（be / arch）
   - [x] 实现基础实体归一化：同名、别名、大小写和常见 APT 别称合并。
   - [x] 后端生成正式 `entity_id`，LLM 不生成最终 ID。
   - [x] 后端生成正式 `relation_id`，LLM 不直接写正式关系。
   - [x] 将可信候选结果写入 `entities`、`relations` 和 `evidence`。
   - [x] 基于实体类型和关系类型做最小合法性校验。

6. [ ] **S1.6 导出并验证 `graph.json`**（be / fe / qa）
   - [x] 从 SQLite 正式图谱表导出 `data/graph/graph.json`。
   - [x] 确认 `nodes` 的 `evidence_ids` 能追溯到 `evidence`。
   - [x] 确认 `edges` 的 `evidence_ids` 能追溯到 `evidence`。
   - [ ] 前端能使用真实样本的 `graph.json` 或 API 响应正常渲染。
    - [ ] 记录当前流程的手动步骤和失败边界。
    - [x] 迁移现有黄金集和示例中的 `TARGET` 实体为语义实体类型。
    - [x] 增加成员、控制、转账关系的结构验收 fixture。

## Step 2：P0 MVP 闭环 `P0`

目标：形成团队可复现、可继续开发的最小产品。Step 2 完成后才算 MVP，Step 0 只能算 Demo 或脚手架闭环。

1. [ ] **S2.1 端到端流水线入口**（be / qa）
   - [ ] 提供一个统一入口运行 `clean -> extract -> normalize -> build_graph -> report`。
   - [x] 标准 Document 之后的 Pipeline 已支持指定 `target_group` 或 `doc_id`。
   - [x] 候选、归一化、图谱、证据和任务状态写入 SQLite；评审工件保留为 Git JSON。
   - [ ] 同一份样本文档在其他成员机器上能复现。

2. [x] **S2.2 稳定运行时 canonical graph**（be / arch）
   - [x] Git JSON 负责人工输入和经评审实验档案，SQLite 负责运行时 canonical graph、证据、导入状态和同步水位。
   - [x] `graph.json` 是导出快照、离线样例和演示兜底，前端默认消费 `/api/v1/graph` 的轻量 GraphView。
   - [x] Neo4j 是由 SQLite 重建的可重建查询投影，不是事实源。
   - [x] 禁止 `LLM 原始输出 -> Neo4j -> 前端` 这类绕过正式图谱的链路。

3. [x] **S2.3 完成核心 API**（be / fe）
   - [x] 图谱接口能返回节点、关系和证据。
   - [x] 实体详情接口能返回别名、描述、置信度、来源数量和证据。
   - [x] 报告接口能返回指定目标组织的基础报告。
   - [x] 路径查询已有 SQLite BFS 降级实现。
   - [x] 错误响应保持统一结构。

4. [ ] **S2.4 完成核心前端体验**（fe / qa）
   - [x] 图谱页面能按目标组织展示节点和关系。
   - [x] 点击节点后能看到实体详情和证据。
   - [x] 点击关系后能看到关系类型、置信度和证据。
   - [x] 报告页面能展示基础报告和结构化章节。
   - [ ] 页面能区分“证据事实”和“系统推断”。

5. [ ] **S2.5 完成 P0 质量门禁**（qa / 全员）
   - [x] 后端基线测试通过。
   - [x] 前端测试和生产构建通过。
   - [x] README 提供 Docker、离线导入和真实 LLM 入口。
   - [ ] 至少 1 个目标组织端到端可复现。
   - [x] `docs/demo-flow.md` 已记录实现边界和降级语义。

## Step 3：课程验收闭环 `P0`

目标：覆盖课程要求中的核心验收项，让项目可以进入实验报告和课堂演示。

1. [ ] **S3.1 覆盖三个目标组织**（data / llm / be）
   - [ ] 完成 APT28 样本文档、候选抽取、正式图谱和报告。
   - [ ] 完成 Lazarus 样本文档、候选抽取、正式图谱和报告。
   - [ ] 完成 Kimsuky 样本文档、候选抽取、正式图谱和报告。
   - [ ] 三个目标组织的数据字段和图谱输出保持同一契约。

2. [ ] **S3.2 覆盖三类来源**（data / be）
   - [ ] 至少覆盖安全报告、安全博客、CERT 或厂商报告中的一类安全来源。
   - [ ] 至少覆盖新闻、政府公告或公开通报中的一类公开公告来源。
   - [ ] 至少覆盖社媒、论坛或人工整理文本中的一类公开讨论来源。
   - [ ] 每类来源都能说明采集或导入方式、清洗方式和可信度边界。

3. [ ] **S3.3 完成 MITRE ATT&CK 和行为模式分析**（llm / be / qa）
   - [ ] 将关键技术映射到 MITRE ATT&CK technique。
   - [ ] 将行为按攻击阶段组织，例如初始访问、执行、持久化、横向移动和数据窃取。
   - [ ] 每个 MITRE 映射都保留 `evidence_ids`。
   - [ ] 报告中能解释行为模式如何从图谱和证据得到。

4. [x] **S3.4 完成基础评测**（qa / llm）
   - [x] 使用通过 schema、关系矩阵和证据校验的 APT28 英文 golden 作为首份可信基线。
   - [x] 实现实体抽取正确、多抽和漏抽统计。
   - [x] 实现关系抽取正确、多抽和漏抽统计。
   - [x] 实现实体和关系 precision、recall、F1 评测脚本。
   - [x] 在 `docs/reports/llm-extraction-baseline.md` 记录数据规模、真实指标和局限。

5. [ ] **S3.5 完成三组织结构化报告**（llm / be / fe / qa）
   - [ ] 每个组织都生成目标画像、行为模式、关联网络、时间线和威胁评估五类章节。
   - [ ] 规则降级模式不依赖 API Key，且不先尝试外部 LLM。
   - [ ] 章节中的事实引用可回溯到 `evidence_ids` 或图谱节点/关系。
   - [ ] 前端能按章节展示三个组织的真实报告。

6. [ ] **S3.6 完成课程报告和演示材料**（qa / 全员）
   - [ ] 完成实验报告结构：背景、需求、架构、实现、结果、评测、总结。
   - [ ] 准备演示脚本：导入文档、运行流程、查看图谱、查看证据、生成报告。
   - [ ] 准备关键截图：前端首页、图谱、实体详情、证据、报告、评测结果。
   - [ ] 标明哪些能力已实现，哪些属于 P1/P2 展望。

## Step 4：增强能力 `P1`

目标：在 P0 已稳定的基础上提升系统表现力和答辩加分点。

1. [ ] **S4.1 Neo4j 同步和路径查询**（be / fe）
   - [x] 从 SQLite canonical graph 全量构建 Neo4j 查询投影，并支持基于同步水位的幂等增量更新。
   - [x] 实现 Neo4j 状态检查接口。
   - [ ] 实现按组织、时间、地区和攻击类型的多维查询及多跳关键路径接口。
   - [x] Neo4j 多跳关键路径查询已接入统一路径接口；多维组合查询仍待实现。
   - [x] Neo4j 不可用时降级到 SQLite 查询。
   - [x] 支持清空 Neo4j 后从 SQLite 重建，证明 Neo4j 不持有唯一事实。
   - [x] 前端展示路径查询结果。

2. [ ] **S4.2 报告导出与表现增强**（be / fe / qa）
   - [ ] 在 P0 五章节报告之上增加 Word/PDF 导出。
   - [ ] 增加更丰富的图表、风险趋势和横向组织对比。
   - [ ] 报告版本化与历史对比不阻塞课程演示。

3. [ ] **S4.3 采集调度与增量更新**（data / be）
   - [ ] 在 P0 三类来源最小采集入口之上增加定时调度。
   - [ ] 增加 checkpoint、重试、增量去重和新情报自动入图。
   - [ ] 调度失败时记录错误，不影响已有正式图谱。

4. [ ] **S4.4 质量增强和可维护性**（arch / qa）
   - [ ] 增加 JSON schema 或 Pydantic 校验。
   - [ ] 增加实体类型和关系类型合法性矩阵。
   - [ ] 增加更多后端测试和前端构建检查。
   - [ ] 整理常见问题和调试说明。

## Step 5：可选扩展 `P2`

目标：时间充足时探索更完整的情报平台能力；时间不足时写入后续展望即可。

1. [ ] **S5.1 兼容外部情报格式**（arch / be）
   - [ ] 设计 STIX 2.1 子集导入导出。
   - [ ] 设计 MISP 事件或属性级兼容输出。
   - [ ] 设计 OpenCTI 风格对象映射说明。
   - [ ] 说明外部格式与本项目 SQLite canonical graph 的边界。

2. [ ] **S5.2 GraphRAG 风格问答或摘要**（llm / be / fe）
   - [ ] 从正式图谱中选择目标组织相关子图。
   - [ ] 基于证据和子图生成摘要。
   - [ ] 支持简单自然语言问答。
   - [ ] 明确回答必须引用证据，不允许只凭模型发挥。

3. [ ] **S5.3 插件式 enrichment**（be / data）
   - [ ] 设计 enrichment analyzer 接口。
   - [ ] 支持 IOC、CVE、域名或哈希的扩展信息补全。
   - [ ] 记录 enrichment 来源、时间和证据。
   - [ ] enrichment 结果默认进入候选层，确认后再入正式图谱。

4. [ ] **S5.4 更严格的 schema/rule 推理**（arch / be）
   - [ ] 增加更细的实体类型约束。
   - [ ] 增加更细的关系合法性规则。
   - [ ] 增加推断关系的 accepted/rejected 审核流程。
   - [ ] 报告中明确区分直接证据、规则推理和 LLM 推断。

## 最近下一步

1. [x] **锁定三组织已审核 Extraction**（arch / llm / qa）
   - [x] 显式配置 APT28、Kimsuky、Lazarus 的 Document/Extraction 对。
   - [x] 排除 Candidate Audit，多个合法工件时明确报错。
   - [x] 在独立 SQLite 中验证三个 `reviewed` Pipeline 均产生非零实体、关系和证据。

2. [ ] **固化三类来源采集与预处理验收**（data / qa）
   - [ ] 输出三组织、三来源类型、中英文数量和 Schema/哈希错误。
   - [ ] 记录安全来源、新闻来源和社媒/论坛来源的采集或批量转换命令。

3. [ ] **补齐 MITRE、分析 API 和三组织报告**（llm / be / fe / qa）
   - [ ] MITRE 映射只从受审技术表生成并保留证据。
   - [ ] 移除跨组织分析返回和硬编码威胁评分。
   - [ ] 三个组织都生成五章节规则报告。

4. [ ] **保留最小评测并准备答辩**（qa / 全员）
   - [ ] 评测只展示固定开发集指标和局限，不建设完整平台。
   - [ ] 准备课程验收矩阵、20 分钟脚本和离线降级路径。
