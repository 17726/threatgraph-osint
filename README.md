# ThreatGraph-OSINT

中文名：开源威胁情报知识图谱研判系统

项目副标题：基于大模型的 APT 组织 OSINT 分析与知识图谱系统

---

## 项目定位

ThreatGraph-OSINT 面向 APT28、Lazarus、Kimsuky 等目标组织，构建覆盖多源情报采集、实体识别、关系抽取、行为分析、知识图谱构建与智能报告生成的端到端 OSINT 分析系统。

本项目对应《网络空间安全综合实验》实验三：开源情报资源中潜在行为和关系的大模型深度分析系统。

---

## 当前状态

当前仓库处于 P0 脚手架阶段：

```text
已完成：架构方案、数据契约、API 契约、Docker 运行契约、开源项目对比草案、课程要求、
        Docker Compose、FastAPI 后端、SQLite demo seed、React TypeScript 前端
下一步：冻结 JSON 契约，补真实样本文档、LLM 抽取流水线、评测集、Neo4j 同步和报告结构化展示
```

新成员先不要直接改接口字段。所有数据结构和接口变更先同步架构与接口组。

---

## 技术栈

```text
前端：React + TypeScript + Vite + ECharts-for-React
后端：FastAPI
事实源：SQLite
图谱导出：graph.json
图查询增强：Neo4j，增强阶段 / 优先级 P1
运行环境：Docker Compose
LLM 接口：OpenAI-compatible API
```

核心原则：

1. SQLite 是唯一事实源。
2. graph.json 是导出格式、前端 mock、演示兜底和 Neo4j 同步输入。
3. Neo4j 是增强能力，不作为事实源。
4. LLM 原始输出不能直接写入 Neo4j。
5. 前端只调用 FastAPI，不直接读取 SQLite、graph.json 或 Neo4j。

---

## 新成员上手

建议按这个顺序阅读：

```text
1. README.md
2. docs/team-workflow.md
3. docs/stage-roadmap.md
4. docs/architecture.md
5. docs/data-contract.md
6. docs/api-contract.md
7. docs/reference-comparison.md
8. docs/docker-runtime.md
```

如果你只负责某一组，先看：

```text
数据与样本组：docs/data-contract.md + docs/team-workflow.md
LLM 与分析组：docs/data-contract.md + docs/architecture.md
后端组：docs/api-contract.md + docs/data-contract.md
前端组：docs/api-contract.md + docs/team-workflow.md
报告测试组：docs/team-workflow.md + docs/reference-comparison.md + docs/references/course-requirements.md
```

---

## 组别职责简表

详细分工见 [docs/team-workflow.md](docs/team-workflow.md)。

| 组别 | 主要职责 | 关键产出 |
| --- | --- | --- |
| 架构与接口组 | 统一技术路线、数据契约、API 契约、目录结构 | 架构文档、接口文档、评审结论 |
| 数据与样本组 | 收集三类情报源，整理原始文档和黄金测试集 | raw 数据、golden.json、来源索引 |
| LLM 与行为分析组 | 实体关系抽取、MITRE 映射、行为分析、候选推理 | 抽取结果、行为模式、推理结果 |
| 后端与数据层组 | FastAPI、SQLite、pipeline、graph.json 导出、Neo4j 同步 | API 服务、数据库、同步脚本 |
| 图谱与前端组 | React 页面、图谱可视化、搜索、详情、报告展示 | 前端页面、图谱交互、演示界面 |
| 报告测试与答辩组 | 评测、实验报告、PPT、演示脚本和录像 | 评测结果、报告、PPT、答辩材料 |

---

## 阶段与优先级

`P0/P1/P2` 表示优先级，不表示开发先后顺序。阶段路线见 [docs/stage-roadmap.md](docs/stage-roadmap.md)。

Step 0：脚手架和 Mock 闭环

```text
FastAPI + SQLite demo seed + React 前端
前端直接调用后端 API，基于 Mock/seed 数据展示图谱和报告
```

Step 1：真实样本文档闭环

```text
本地文本文件 -> document.json -> extraction_result.json -> SQLite -> graph.json -> 前端图谱 / 基础报告
```

Step 2：集成 MVP

```text
SQLite + FastAPI + React/ECharts
完成本地文档导入、实体关系图谱、实体详情、证据展示、基础路径追踪、报告生成
```

Step 3：课程验收增强

```text
补齐三类来源最小采集、三目标组织、MITRE 映射、行为模式分析、评测结果、Neo4j 图查询增强
```

---

## 计划目录

```text
backend/      FastAPI 后端
frontend/     React + TypeScript + Vite 前端
data/         SQLite、导出图谱、报告、评测数据
scripts/      流水线、导出、同步脚本
docs/         架构、接口、数据、运行与协作文档
```

---

## 推荐运行方式

项目默认使用 Docker Compose，不要求组员本机安装 Python 依赖。

首次启动：

```bash
docker compose up --build
```

后续启动：

```bash
docker compose up
```

默认访问：

```text
前端：http://localhost:5173
后端：http://localhost:8000
API 文档：http://localhost:8000/docs
Neo4j Browser：http://localhost:7474
```

后端测试：

```bash
docker compose build backend
docker compose run --rm backend python -m pytest backend/tests -v
```

前端测试和构建：

```bash
docker compose build frontend
docker compose run --rm frontend npm run test
docker compose run --rm frontend npm run build
```

演示数据脚本：

```bash
docker compose run --rm backend python scripts/seed_demo_data.py
docker compose run --rm backend python scripts/export_graph_json.py
```

生成文件位置：

```text
SQLite：data/threatgraph_osint.db
图谱快照：data/graph/graph.json
```

---

## 发布与隐私约束

1. 不提交原始课程 PDF。
2. 不提交未脱敏的聊天记录、私有链接、教师联系方式、组员手机号、邮箱、API Key。
3. `.env` 不入库，只提交 `.env.example`。
4. 公开材料只保留课程要求：`docs/references/course-requirements.md`。
