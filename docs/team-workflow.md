# 团队协作与组别职责

> 适用范围：ThreatGraph-OSINT 项目组协作  
> 原则：统一契约、并行开发、每日集成、演示优先

---

## 1. 总体分工

建议按 6 个方向分工。人数不足时可以合并相邻职责。

```text
架构与接口组
数据与样本组
LLM 与行为分析组
后端与数据层组
图谱与前端组
报告测试与答辩组
```

所有组必须遵守：

1. 数据字段以 `docs/data-contract.md` 为准。
2. API 字段以 `docs/api-contract.md` 为准。
3. 任何字段变更必须先通知架构与接口组。
4. 所有模块都要保留证据链，不能只给自然语言结论。
5. 演示链路优先于功能堆叠。

---

## 2. 架构与接口组

职责：

1. 维护架构设计、数据契约、API 契约和目录结构。
2. 审核跨组字段变更。
3. 确认 P0 / P1 范围。
4. 组织每日集成检查。

关键产出：

```text
docs/architecture.md
docs/data-contract.md
docs/api-contract.md
docs/docker-runtime.md
接口变更记录
```

不负责：

```text
不替每个组写完整业务代码
不临时接受未经讨论的字段变更
```

---

## 3. 数据与样本组

职责：

1. 收集 APT28、Lazarus、Kimsuky 三个目标组织的资料。
2. 覆盖三类来源：安全报告、新闻/公告、社媒/论坛整理文本。
3. 整理原始文档，填充来源、标题、语言、发布时间等元数据。
4. 维护小型黄金测试集 `golden.json`。

关键产出：

```text
data/raw/*.json
data/evaluation/golden.json
数据来源索引表
```

golden.json 原则：

```text
不是全量数据集，而是小型人工标注标准答案。
建议每个目标组织 2 篇文本片段，8-12 个实体，5-8 条关系。
总量控制在 6 篇文档片段、30-40 个实体、20-25 条关系。
```

不负责：

```text
不自定义新字段
不直接改 LLM Prompt
不把网页 HTML 原样丢给后端
```

---

## 4. LLM 与行为分析组

职责：

1. 设计实体识别和关系抽取 Prompt。
2. 保证 LLM 输出合法 JSON。
3. 做实体、关系候选结果质量检查。
4. 实现 MITRE ATT&CK 映射、行为模式分析、候选推理。

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

## 5. 后端与数据层组

职责：

1. 搭建 FastAPI 服务。
2. 初始化 SQLite 表结构。
3. 实现文档导入、流水线、图谱查询、报告、评测接口。
4. 导出 `data/graph/graph.json`。
5. P0 实现 SQLite BFS 基础路径追踪。
6. P1 实现 Neo4j 同步和 Cypher 多跳路径查询。

关键产出：

```text
backend/
scripts/run_pipeline.py
scripts/export_graph_json.py
scripts/sync_neo4j.py
data/threatgraph_osint.db
```

不负责：

```text
不决定前端交互样式
不随意修改 API 契约
不让 Neo4j 成为事实源
```

---

## 6. 图谱与前端组

职责：

1. 使用 React + TypeScript + Vite 实现前端。
2. 使用 ECharts-for-React 展示关系图谱。
3. 实现搜索、详情、证据展示、时间线、行为分析、报告展示。
4. 对接 FastAPI，不直接读取数据库或 Neo4j。

关键产出：

```text
frontend/src/api/*.ts
frontend/src/types/*.ts
frontend/src/components/*.tsx
frontend/src/pages/*.tsx
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

## 7. 报告测试与答辩组

职责：

1. 维护评测流程和结果表。
2. 根据 golden.json 计算实体、关系抽取指标。
3. 整理实验报告、PPT、演示脚本和录像。
4. 准备开源项目对比和创新点说明。

关键产出：

```text
data/evaluation/evaluation_result.json
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
docs/*：架构与接口组维护，其他组提交变更前先沟通
data/raw/*：数据与样本组维护
data/evaluation/*：报告测试与答辩组维护
backend/*：后端与数据层组维护
frontend/*：图谱与前端组维护
scripts/*：后端与数据层组维护，架构组参与审核
```

---

## 10. 提交规范

提交信息使用中文说明，推荐格式：

```text
docs: 更新接口契约
feat: 添加图谱查询接口
feat: 添加 APT28 样本数据
fix: 修复实体归一化规则
test: 添加 golden 集评测脚本
```
