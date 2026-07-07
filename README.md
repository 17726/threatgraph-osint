# ThreatGraph-OSINT

中文名：开源威胁情报知识图谱研判系统

项目副标题：基于大模型的 APT 组织 OSINT 分析与知识图谱系统

---

## 项目定位

ThreatGraph-OSINT 面向 APT28、Lazarus、Kimsuky 等目标组织，构建覆盖多源情报采集、实体识别、关系抽取、行为分析、知识图谱构建与智能报告生成的端到端 OSINT 分析系统。

本项目对应《网络空间安全综合实验》实验三：开源情报资源中潜在行为和关系的大模型深度分析系统。

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

先看根目录 [TODO.md](TODO.md) 了解当前进展和下一步任务，然后按这个顺序阅读项目文档：

```text
1. README.md
2. TODO.md
3. AGENTS.md
4. docs/development-guidelines.md
5. docs/team-workflow.md
6. docs/stage-roadmap.md
7. docs/architecture.md
8. docs/data-contract.md
9. docs/api-contract.md
10. docs/reference-comparison.md
11. docs/docker-runtime.md
```

如果你只负责某一组，先看：

```text
数据与样本组：docs/data-contract.md + docs/team-workflow.md
LLM 与分析组：docs/data-contract.md + docs/architecture.md
后端横向工作流：docs/api-contract.md + docs/data-contract.md + docs/team-workflow.md
图谱与前端组：docs/api-contract.md + docs/team-workflow.md
报告答辩与测试组：docs/team-workflow.md + docs/reference-comparison.md + docs/references/course-requirements.md
```

---

## 组别职责简表

详细分工见 [docs/team-workflow.md](docs/team-workflow.md)。

| 组别             | 缩写   | 主要职责                                               | 关键产出                        |
| ---------------- | ------ | ------------------------------------------------------ | ------------------------------- |
| 架构与数据规范组 | `arch` | 统一技术路线、数据契约、API 契约、目录结构、后端骨架   | 架构文档、接口文档、评审结论    |
| 数据与样本组     | `data` | 收集三类情报源，整理原始文档和黄金测试集               | raw 数据、golden.json、来源索引 |
| LLM 与分析组     | `llm`  | 实体关系抽取、MITRE 映射、行为分析、候选推理           | 抽取结果、行为模式、推理结果    |
| 图谱与前端组     | `fe`   | React 页面、图谱可视化、搜索、详情、报告展示           | 前端页面、图谱交互、演示界面    |
| 报告答辩与测试组 | `qa`   | 评测、实验报告、PPT、演示脚本和录像                    | 评测结果、报告、PPT、答辩材料   |

后端不是单独小组，而是横向工作流：FastAPI、SQLite、pipeline、graph.json 导出、Neo4j 同步等工作由架构与数据规范组牵头维护；数据、LLM、图谱前端、报告测试等组可以按各自业务边界修改对应后端代码，但必须遵守 API 契约和数据契约。

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