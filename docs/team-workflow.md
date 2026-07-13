# 团队协作与组别职责

> 适用范围：ThreatGraph-OSINT 项目组协作  
> 原则：统一契约、并行开发、每日集成、演示优先

---

## 1. 总体分工

项目按 5 个正式小组协作：

```text
arch：架构与数据规范组
data：数据与样本组
llm：LLM 抽取与分析组
fe：图谱与前端组
qa：报告答辩与测试组
```

后端不是单独小组，而是横向工作流：FastAPI、SQLite、API、pipeline、归一化、导出和 Neo4j 同步等后端工作默认由 `arch` 牵头维护，其他组可以按各自业务边界修改对应后端代码。

所有组必须遵守：

1. 数据字段以 `docs/data-contract.md` 为准。
2. API 字段以 `docs/api-contract.md` 为准。
3. 任何字段变更必须先通知架构与数据规范组。
4. 所有模块都要保留证据链，不能只给自然语言结论。
5. 演示链路优先于功能堆叠。

---

## 2. 架构与数据规范组 `arch`

职责：

1. 维护架构设计、数据契约、API 契约和目录结构。
2. 维护 FastAPI / SQLite / pipeline 等后端骨架和跨组集成边界。
3. 审核跨组字段变更。
4. 确认阶段范围和 P0 / P1 优先级。
5. 组织每日集成检查。

关键产出：

```text
docs/architecture.md
docs/data-contract.md
docs/api-contract.md
docs/docker-runtime.md
接口变更记录
后端骨架和集成入口
```

不负责：

```text
不替每个组写完整业务代码
不临时接受未经讨论的字段变更
不把后端业务逻辑全部集中到架构组一个人身上
```

---

## 3. 数据与样本组 `data`

职责：

1. 收集 APT28、Lazarus、Kimsuky 三个目标组织的资料。
2. 覆盖三类来源：安全报告、新闻/公告、社媒/论坛整理文本。
3. 整理清洗后标准文档，填充来源、标题、语言、发布时间等元数据。
4. 维护小型黄金测试集 `golden.json`。
5. 按数据导入和清洗边界修改对应后端业务代码。
6. 按 `docs/data-contract.md` 的 P0 清洗边界做格式清洗，不提前做事实筛选。

关键产出：

```text
data/documents/<target_group>/*.json
data/raw/*.json
data/golden/golden-<language>-<doc_id>-<schema_version>-<golden_version>.json
docs/schemas/golden.schema.json
数据导入和清洗相关实现
```

P0 主交付是 `data/documents/<target_group>/*.json`。`data/raw/*` 只作为可选采集暂存或复现材料，不阻塞离线闭环。
来源字段语义写在 `docs/data-contract.md` 的 `sources` 表契约中；历史来源索引或转换器输出放入 `data/raw/<collector>/` 复查，不再单独维护 `data/sources/` 目录。

golden.json 原则：

```text
不是全量数据集，而是小型人工标注标准答案。
建议每个目标组织 2 篇文本片段，8-12 个实体，5-8 条关系。
总量控制在 6 篇文档片段、30-40 个实体、20-25 条关系。
格式必须通过 `docs/schemas/golden.schema.json`，关系字段统一使用 head/tail 命名。
```

不负责：

```text
不自定义新字段
不直接改 LLM Prompt
不把网页 HTML 原样丢给后端
不把 MITRE/MISP 这类知识库当作首篇真实正文清洗样本
```

---

## 4. LLM 抽取与分析组 `llm`

职责：

1. 设计实体识别和关系抽取 Prompt。
2. 保证 LLM 输出合法 JSON。
3. 做实体、关系候选结果质量检查。
4. 实现 MITRE ATT&CK 映射、行为模式分析、候选推理。
5. 按抽取、分析和报告生成边界修改对应后端业务代码。

关键产出：

```text
extracted_entities
extracted_relations
mitre_mappings
behavior_patterns
inferred_relations
threat_assessments
Prompt 版本记录
```

字段中文说明：

```text
entity：实体，如 APT28、X-Agent、CVE、Ukraine
relation：关系，如 使用、攻击、利用漏洞、归因于
evidence：证据，说明实体或关系来自哪篇文章哪句话
mitre_mapping：MITRE ATT&CK 映射
behavior_pattern：攻击行为模式
inferred_relation：候选推断关系，不是原文直接事实
rationale：推理理由
confidence：置信度
```

不负责：

```text
不直接写 Neo4j
不把推断结果当作原始事实
不绕过 SQLite 事实源
```

---

## 5. 图谱与前端组 `fe`

职责：

1. 使用 React + TypeScript + Vite 实现前端。
2. 使用 ECharts-for-React 展示关系图谱。
3. 实现搜索、详情、证据展示、时间线、行为分析、报告展示。
4. 对接 FastAPI，不直接读取数据库或 Neo4j。
5. 按图谱查询、API GraphView 消费和展示边界修改对应后端业务代码。

关键产出：

```text
frontend/src/api/*.ts
frontend/src/types/*.ts
frontend/src/components/*.tsx
frontend/src/pages/*.tsx
API GraphView 消费和图谱交互验收记录
```

页面建议：

```text
Dashboard：总览
GraphExplorer：知识图谱
Analysis：行为分析与 MITRE 映射
Reports：报告展示
Evaluation：评测结果
```

不负责：

```text
不处理实体归一化
不直接访问 SQLite、graph.json、Neo4j
不私自改 API 响应结构
```

---

## 6. 报告答辩与测试组 `qa`

职责：

1. 维护评测流程和结果表。
2. 根据 golden.json 计算实体、关系抽取指标。
3. 整理实验报告、PPT、演示脚本和录像。
4. 准备开源项目对比和创新点说明。
5. 按评测、报告和演示验收边界修改对应脚本或后端业务代码。

关键产出：

```text
data/evaluation/evaluation_result-<doc_id>-<model>-<prompt_version>-<schema_version>-<golden_version>-<timestamp>.json
实验报告
最终汇报 PPT
演示脚本
演示录像
开源项目对比表
```

不负责：

```text
不凭空编造评测数据
不修改核心数据契约
不等到最后一天才收集截图
```

---

## 7. 后端横向工作流 `be`

`be` 是任务标签，不是正式小组。它表示 FastAPI、SQLite、API、pipeline、归一化、导出、Neo4j 同步等后端相关工作。

归属原则：

```text
架构与数据规范组：负责后端骨架、目录结构、公共响应、契约和集成边界。
数据与样本组：负责文档导入、采集、清洗和切块相关业务代码。
LLM 抽取与分析组：负责抽取、分析、Prompt 调用和结果校验相关业务代码。
图谱与前端组：负责图谱查询、路径查询、API GraphView 消费和展示相关业务代码。
报告答辩与测试组：负责评测接口、验收脚本、报告数据输出和演示验证相关代码。
```

后端工作必须遵守：

1. 不随意修改 API 契约。
2. 不随意修改数据契约。
3. 不让 Neo4j 成为事实源。
4. 不绕过 SQLite canonical graph。
5. 涉及跨组字段变更时必须先让 `arch` 评审。

---

## 8. 每日集成检查

每天至少检查一次：

```text
1. 当前主分支能否启动
2. API 契约是否变更
3. graph.json 是否能导出
4. 前端是否能加载 mock 或 API 数据
5. golden.json 是否新增或修正
6. 报告和 PPT 是否同步最新截图
```

最低集成目标：

```text
任意一天都能跑通一个目标组织的演示链路：
文档 -> 抽取 -> 图谱 -> 行为分析 -> 报告
```

---

## 9. 文件归属

```text
docs/*：架构与数据规范组维护，其他组提交变更前先沟通
data/documents/*：数据与样本组维护的 P0 标准文档
data/raw/*：数据与样本组维护的可选采集暂存
data/evaluation/*：报告答辩与测试组维护
backend/*：后端横向工作流，arch 牵头，各组按业务边界修改
frontend/*：图谱与前端组维护
scripts/*：后端横向工作流或报告答辩与测试相关脚本，按任务归属维护，arch 参与审核
```

---

## 10. 分支命名建议

完整 Git 流程、分支命名、MR / Pull Request 和 Force Push 规则见 [开发规范与 Git 流程](CONTRIBUTING.md)。

分支名支持两种格式。推荐带组别缩写，方便观察每个组的进度；如果任务很小，也可以不带组别字段。

```text
<type>/<group>/<task-name>
<type>/<task-name>
```

正式组别缩写：

```text
arch：架构与数据规范组
data：数据与样本组
llm：LLM 抽取与分析组
fe：图谱与前端组
qa：报告答辩与测试组
```

示例：

```text
feat/arch/schema-v1
feat/data/apt28-sample
feat/llm/json-retry
feat/fe/graph-detail
feat/qa/golden-eval
feat/graph-search
fix/report-api
```

提交信息使用 Conventional Commits 的轻量格式，类型前缀用英文，冒号后的说明默认中文：

```text
docs: 更新接口契约
feat: 添加图谱查询接口
feat: 添加 APT28 样本数据
fix: 修复实体归一化规则
test: 添加 golden 集评测脚本
```
