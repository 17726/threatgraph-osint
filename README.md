# ThreatGraph-OSINT

中文名：开源威胁情报知识图谱研判系统

项目副标题：基于大模型的 APT 组织 OSINT 分析与知识图谱系统

---

## 项目定位

ThreatGraph-OSINT 面向 APT28、Lazarus、Kimsuky 等目标组织，构建覆盖多源情报采集、实体识别、关系抽取、行为分析、知识图谱构建与智能报告生成的端到端 OSINT 分析系统。

本项目对应《网络空间安全综合实验》实验三：开源情报资源中潜在行为和关系的大模型深度分析系统。

---

## 当前架构决策

```text
前端：React + TypeScript + Vite + ECharts-for-React
后端：FastAPI
事实源：SQLite
图谱导出：graph.json
图查询增强：Neo4j，P1 必做
运行环境：Docker Compose
LLM 接口：OpenAI-compatible API
```

核心原则：

1. SQLite 是唯一事实源。
2. graph.json 是导出格式、前端 mock、演示兜底和 Neo4j 同步输入。
3. Neo4j 是 P1 图查询增强，不作为事实源。
4. LLM 原始输出不能直接写入 Neo4j。
5. 前端只调用 FastAPI，不直接读取 SQLite、graph.json 或 Neo4j。

---

## 文档入口

```text
docs/architecture-v2.md       架构设计
docs/data-contract-v2.md      SQLite 与 graph.json 数据契约
docs/docker-runtime-v2.md     Docker Compose 运行契约
docs/api-contract-v2.md       FastAPI 接口契约
docs/references/              课程要求和前期讨论记录
```

---

## 计划目录

```text
backend/      FastAPI 后端
frontend/     React + TypeScript + Vite 前端
data/         SQLite、导出图谱、报告、评测数据
scripts/      流水线、导出、同步脚本
docs/         架构和接口文档
```

---

## 目标分期

P0：基础可演示版本

```text
SQLite + FastAPI + React/ECharts
完成文档导入、实体关系图谱、实体详情、证据展示、SQLite 基础路径追踪、
MITRE 映射、行为模式分析、报告生成、基础评测
```

P1：图谱增强版本

```text
从 SQLite canonical graph 同步到 Neo4j
支持 Neo4j/Cypher 多跳路径查询、多维度组合查询和 Neo4j 状态展示
```

---

## 推荐运行方式

```bash
docker compose up --build
```

默认访问：

```text
前端：http://localhost:5173
后端：http://localhost:8000
API 文档：http://localhost:8000/docs
Neo4j Browser：http://localhost:7474
```

当前仓库处于架构初始化阶段，代码脚手架后续按 `docs/architecture-v2.md` 落地。
