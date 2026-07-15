# ThreatGraph-OSINT

<div align="center">

**开源威胁情报知识图谱研判系统**

基于大模型的 APT 组织 OSINT 分析、关系发现与证据链研判平台

简体中文 | [English](README.en.md)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=111827)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker Compose](https://img.shields.io/badge/Docker_Compose-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)

[快速开始](#快速开始) · [系统能力](#系统能力) · [架构与数据流](#架构与数据流) · [项目文档](#项目文档) · [开发验证](#开发验证)

</div>

ThreatGraph-OSINT 面向 APT28、Lazarus、Kimsuky 等目标组织，将公开情报文档转换为可检索、可视化、可追溯的威胁情报知识图谱，辅助分析人员查看实体关系、证据来源、行为模式和评测结果。

本项目对应《网络空间安全综合实验》实验三：**开源情报资源中潜在行为和关系的大模型深度分析系统**。

> [!IMPORTANT]
> 当前仓库处于 P0 / Step 1 迭代阶段。前端图谱、行为分析、评测页面和离线抽取验证已具备基础实现；真实样本文档的完整闭环、自动采集和 Neo4j 增强能力仍按路线逐步完善。

## 系统能力

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| 目标组织切换 | 已实现 | 支持按 APT28、Lazarus、Kimsuky 查询 SQLite 正式图谱；空库返回空图 |
| 知识图谱可视化 | 已实现 | 展示实体、关系、时间过滤和路径追踪 |
| 实体与关系详情 | 已实现 | 支持查看类型、置信度、验证状态和证据 |
| 行为分析 | 已实现基础页面 | 展示攻击阶段、技术映射和分析结果 |
| 评测结果 | 已实现 Mock 页面 | 展示实体、关系抽取指标原型和错误样例，当前指标为前端 Mock 数据 |
| FastAPI API | 已实现 P0 接口 | 提供健康检查、图谱和报告接口 |
| SQLite 运行时主库 | 已确定 | 保存 canonical graph、证据、导入状态和同步水位 |
| 文档与候选抽取契约 | 已冻结 | 提供 JSON Schema、样例和关系合法性矩阵 |
| 自动采集 | 规划中 | 后续接入 HTTP 页面、RSS/Atom 等来源 |
| Neo4j 图查询投影 | P1 增强 | 承担多维查询、关键路径、图算法和增量同步演示 |

### 核心原则

- **事实按职责分层**：Git JSON 保存人工输入及经评审实验档案；SQLite 是运行时 canonical graph、证据和导入状态的权威来源。
- **候选层与正式图谱层分离**：LLM 输出先进入候选表，经过校验和归一化后才能进入正式实体与关系。
- **证据链贯穿分析流程**：实体、关系、行为分析和报告结论都应能追溯到 `evidence_ids`。
- **graph.json 是导出快照**：用于离线样例、演示兜底和 Neo4j 同步输入，不替代 SQLite。
- **Neo4j 是可重建查询投影**：只接收 SQLite canonical graph 的已验证实体和关系；同步失败不能反向污染 SQLite。
- **前端只调用 FastAPI**：React 不直接读取 SQLite、`graph.json` 或 Neo4j。

## 界面预览

![ThreatGraph-OSINT 前端界面](docs/assets/pr3-frontend.png)

前端当前包含三个主要视图：

- **知识图谱**：查看目标组织的实体网络、关系、时间范围和证据详情。
- **行为分析**：查看攻击阶段、MITRE ATT&CK 映射和行为模式。
- **评测结果**：查看评测页面原型、Mock 指标和错误样例。

## 架构与数据流

```text
公开情报 / 本地清洗文档
          │
          ▼
     文档导入与切块
          │
          ▼
   LLM 候选实体与关系
          │
          ▼
 校验、归一化与证据绑定
          │
          ▼
 SQLite 运行时 canonical graph
          │
     ┌────┴────┐
     ▼         ▼
 graph.json  FastAPI
     │         │
     ▼         ▼
   Neo4j     React + ECharts
  P1 增强       图谱研判界面
```

### 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite、ECharts、Lucide React |
| 后端 | FastAPI、Python 3.13 |
| 数据层 | SQLite |
| 图谱增强 | Neo4j 5 Community，P1 阶段使用 |
| 运行方式 | Docker Compose |
| LLM 接口 | OpenAI-compatible API |

## 快速开始

### 环境要求

- Docker Desktop，包含 Docker Compose
- Git

项目默认通过 Docker Compose 运行，不要求本机安装 Python 或前端依赖。

### 1. 配置环境变量

复制示例配置文件：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

启动时只创建 SQLite 表，不自动写入演示数据。真实抽取默认使用 DeepSeek V4 Flash；只在本地 `.env`
填写 `LLM_API_KEY`，不要把密钥放进命令行、代码或提交记录。

### 2. 启动服务

首次启动或依赖发生变化时：

```bash
docker compose up --build
```

后续启动：

```bash
docker compose up
```

服务地址：

| 服务 | 地址 |
| --- | --- |
| 前端 | <http://localhost:5173> |
| 后端 API | <http://localhost:8000> |
| Swagger API 文档 | <http://localhost:8000/docs> |
| 健康检查 | <http://localhost:8000/api/v1/health> |
| Neo4j Browser | <http://localhost:7474> |

### 3. 导入真实抽取结果

启动后数据库默认为空。要调用 LLM 抽取、导入 SQLite 并导出图谱快照，执行：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --document data/documents/apt28/your-document.json \
  --import --export-graph --json
```

也可以将已有的 `document.json` 和 `extraction_result.json` 导入：

```bash
docker compose run --rm backend python scripts/import_extraction_result.py \
  --document data/documents/apt28/your-document.json \
  --extraction-result data/extracted/your-extraction-result.json \
  --export-graph
```

运行后生成或更新：

```text
SQLite 数据库：data/threatgraph_osint.db
图谱快照：data/graph/graph.json
运行摘要：data/run_logs/run-log-<run_id>.json
```

运行摘要记录文档加载、LLM、Golden 评测、SQLite 导入、图谱导出和总耗时，
并聚合本次 LLM API 调用次数与 Token 使用量。`data/run_logs/` 是本机运行产物，
默认不提交到 Git；如需临时输出到其他目录，可增加
`--run-log-dir <目录>`。

LLM 请求等待期间默认每 30 秒输出一次心跳，并在重试时显示尝试序号和失败原因。
可使用 `--heartbeat-seconds <秒数>` 调整间隔，设为 `0` 可关闭心跳。

### 4. 停止服务

```bash
docker compose down
```

如果需要同时清理 Neo4j 的 Docker 数据卷：

```bash
docker compose down -v
```

## API 入口

当前 P0 后端提供以下基础接口：

```text
GET /api/v1/health
GET /api/v1/graph?target=APT28&depth=2
GET /api/v1/reports/{target_group}
```

成功响应统一使用以下结构：

```json
{
  "success": true,
  "data": {},
  "timestamp": "2026-07-12T00:00:00+08:00"
}
```

完整接口字段、错误码和后续接口规划见 [`docs/api-contract.md`](docs/api-contract.md)。

## 数据契约

项目使用 schema-first 方式冻结跨组数据边界：

```text
data/documents/<target_group>/*.json
        │
        ▼
document.schema.json
        │
        ▼
extraction-result.schema.json
        │
        ▼
校验、归一化、证据绑定
        │
        ▼
graph.schema.json -> data/graph/graph.json
```

主要契约文件：

- [`document.schema.json`](docs/schemas/document.schema.json)：清洗后的标准文档。
- [`extraction-result.schema.json`](docs/schemas/extraction-result.schema.json)：LLM 候选实体和关系。
- [`golden.schema.json`](docs/schemas/golden.schema.json)：人工标准答案和评测数据。
- [`graph.schema.json`](docs/schemas/graph.schema.json)：SQLite 导出的完整图谱快照。
- [`relationship-matrix.md`](docs/schemas/relationship-matrix.md)：实体类型与关系类型合法性矩阵。

可复用样例位于 [`data/examples/`](data/examples/)。真实清洗文档默认放在 `data/documents/<target_group>/`。

## 项目结构

```text
.
├── backend/              FastAPI 后端与服务逻辑
├── frontend/             React + TypeScript + Vite 前端
├── data/
│   ├── examples/         契约样例
│   ├── documents/        标准化真实文档
│   ├── extracted/        抽取结果
│   ├── graph/            graph.json 导出快照
│   └── threatgraph_osint.db
├── scripts/              数据导入、转换和导出脚本
├── docs/                 架构、契约、运行和协作文档
├── TODO.md               当前任务与进展
└── docker-compose.yml    本地开发编排配置
```

## 开发验证

### 后端测试

```bash
docker compose build backend
docker compose run --rm backend python -m pytest backend/tests -v
```

### 前端测试与构建

```bash
docker compose build frontend
docker compose run --rm frontend npm run test
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run format:check
```

### 离线抽取结果校验

```bash
docker compose run --rm backend python scripts/validate_extraction_result.py \
  data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json \
  --document data/examples/document.apt28.thn.beardshell.example.json
```

### DeepSeek V4 真实抽取与评测

先在本地 `.env` 配置 `LLM_API_KEY`，然后执行最小连通性检查：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --preflight-only --json
```

对人工 golden 文档执行真实抽取并计算实体、关系 Precision、Recall、F1：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --document data/documents/apt28/apt28_080.json \
  --golden data/golden/golden-en-apt28_080-1.0-1.0.json \
  --json
```

抽取结果仍只进入候选层；被过滤的候选会单独写入同一 `run_id` 的 Candidate Audit。当前
评测器会把其中 rejected 项计入预测数量和 false positive，这是待拆分为 raw/validated 多作用域
指标的历史口径，不能直接解释为模型本身的最终 F1。需要生成正式图谱时显式追加
`--import --export-graph`。
完整操作和评测口径见
[`docs/guides/llm-extraction-and-evaluation.md`](docs/guides/llm-extraction-and-evaluation.md)。

## 项目文档

| 文档 | 用途 |
| --- | --- |
| [`TODO.md`](TODO.md) | 当前进展、优先级和下一步任务 |
| [`docs/stage-roadmap.md`](docs/stage-roadmap.md) | Step 0～Step 4 阶段路线和验收标准 |
| [`docs/architecture.md`](docs/architecture.md) | 系统架构、数据流和分层边界 |
| [`docs/api-contract.md`](docs/api-contract.md) | FastAPI 接口契约 |
| [`docs/data-contract.md`](docs/data-contract.md) | SQLite 数据层契约 |
| [`docs/demo-flow.md`](docs/demo-flow.md) | 课程全链路演示路径、当前实现边界与数据门槛 |
| [`docs/schemas/README.md`](docs/schemas/README.md) | JSON Schema 与样例说明 |
| [`docs/docker-runtime.md`](docs/docker-runtime.md) | Docker Compose 运行契约 |
| [`docs/team-workflow.md`](docs/team-workflow.md) | 小组职责与协作流程 |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | 开发规范与 Git 流程 |
| [`docs/reports/llm-extraction-baseline.md`](docs/reports/llm-extraction-baseline.md) | DeepSeek V4 真实调用、APT28 指标和 golden 门禁结论 |

新成员建议按以下顺序阅读：

1. 本 README，了解项目定位和运行方式。
2. [`TODO.md`](TODO.md)，了解当前任务和完成边界。
3. [`docs/stage-roadmap.md`](docs/stage-roadmap.md)，了解项目阶段。
4. [`docs/architecture.md`](docs/architecture.md)，了解系统数据流。
5. 与负责小组对应的契约和协作文档。

按组别选择入口：

| 组别 | 优先阅读 |
| --- | --- |
| 架构与数据规范组 `arch` | [`docs/architecture.md`](docs/architecture.md)、[`docs/api-contract.md`](docs/api-contract.md)、[`docs/data-contract.md`](docs/data-contract.md) |
| 数据与样本组 `data` | [`docs/data-contract.md`](docs/data-contract.md)、[`docs/schemas/README.md`](docs/schemas/README.md)、[`docs/team-workflow.md`](docs/team-workflow.md) |
| LLM 抽取与分析组 `llm` | [`docs/guides/llm-extraction-and-evaluation.md`](docs/guides/llm-extraction-and-evaluation.md)、[`docs/data-contract.md`](docs/data-contract.md)、[`docs/schemas/README.md`](docs/schemas/README.md) |
| 图谱与前端组 `fe` | [`docs/api-contract.md`](docs/api-contract.md)、[`docs/team-workflow.md`](docs/team-workflow.md) |
| 报告答辩与测试组 `qa` | [`docs/team-workflow.md`](docs/team-workflow.md)、[`docs/reference-comparison.md`](docs/reference-comparison.md)、[`docs/references/course-requirements.md`](docs/references/course-requirements.md) |

## 当前路线

```text
Step 0  脚手架与 Mock 闭环       已完成
Step 1  真实样本文档闭环          进行中
Step 2  P0 MVP 闭环               待完成
Step 3  课程验收闭环              待完成
Step 4  Neo4j、采集与报告增强     规划中
```

当前首要目标是使用至少一份可追溯真实文档，跑通“导入 → 切块 → 候选抽取 → 归一化 → 正式图谱 → 前端展示”的闭环。

## 数据与隐私约束

- 不提交原始课程 PDF。
- 不提交未脱敏的聊天记录、私有链接、教师联系方式或个人联系方式。
- 不提交 API Key、真实密码或 `.env` 文件；仓库只保留 [`.env.example`](.env.example)。
- 公开材料只保留必要的课程要求和脱敏文档。
