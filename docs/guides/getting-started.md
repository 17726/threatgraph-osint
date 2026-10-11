# 快速上手

本指南包含环境准备、审核样例导入、模型接入和开发验证。项目介绍见 [README](../../README.md)。

## 本地运行

需要 **Git** 和支持 Compose 的 **Docker**（Windows / macOS 可使用 Docker Desktop）。容器方式不要求本机安装 Python 或 Node.js。

### 1. 获取代码

```bash
git clone https://github.com/17726/threatgraph-osint.git
cd threatgraph-osint
cp .env.example .env
```

Windows PowerShell 将最后一行换成：

```powershell
Copy-Item .env.example .env
```

先体验本地样例时，保持 `LLM_API_KEY` 为空即可。

### 2. 启动基础服务

```bash
docker compose up --build -d backend frontend
```

| 入口            | 地址                                  |
| --------------- | ------------------------------------- |
| 前端            | <http://localhost:5173>               |
| 交互式 API 文档 | <http://localhost:8000/docs>          |
| 健康检查        | <http://localhost:8000/api/v1/health> |

首次启动只初始化数据库，**不会自动填充样例数据**。基础浏览与离线导入不依赖 crawler、Neo4j 或模型 API。

### 3. 导入审核样例

在仓库根目录执行以下单行命令（Bash / PowerShell 通用），使用仓库中已有的文档和人工审核抽取结果：

```bash
docker compose run --rm backend python scripts/import_extraction_result.py --document data/examples/document.apt28.thn.beardshell.example.json --extraction-result data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json --export-graph --json
```

该步骤不调用模型 API。导入后打开前端，选择 **APT28** 并点击“刷新”，即可探索样例图谱、点击节点或关系查看证据。此样例只填充 APT28；Lazarus、Kimsuky 需要各自的文档与抽取结果。

数据保存在宿主机 `data/threatgraph_osint.db`，导出快照位于 `data/graph/graph.json`。前端通过 FastAPI 读取数据库中的图谱。

### 4. 停止服务

```bash
docker compose down
```

本地 `data/` 中的 SQLite 数据会保留。后续使用 `docker compose up -d backend frontend` 再次启动。

## 接入模型与采集

在本地 `.env` 中配置模型服务。仓库示例默认填写 DeepSeek 的地址与模型名，也可以替换为你的 OpenAI-compatible 服务配置：

```dotenv
LLM_API_KEY=<你的 API Key>
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
```

模型名称和可用性以所用服务为准。以下预检、真实抽取和在线采集会调用外部模型 API，并产生相应费用。

先验证连接：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py --preflight-only --json
```

对仓库中的一篇文档执行真实抽取、导入和图谱导出：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py --document data/documents/apt28/apt28_080.json --import --export-graph --json
```

要从界面采集新情报，启动 crawler 并应用环境配置：

```bash
docker compose up --build -d backend frontend crawler
```

然后在前端点击“采集情报”。采集固定使用 `live` 抽取；未配置模型时按钮禁用，API 返回 `503 ERR_LLM_NOT_CONFIGURED`。crawler 只通过内部网络与后端通信，不暴露宿主机端口。

单篇文档过滤失败时，其余文档可以继续处理，任务会标记为 `partial_success`。模型参数、候选审计与评测口径见 [LLM 抽取与评测指南](../guides/llm-extraction-and-evaluation.md)；任务日志、运行产物和可选 Neo4j 配置见 [运行与排障](../guides/running-and-troubleshooting.md)。

## 开发与验证

```text
backend/       FastAPI、图谱查询、抽取与分析服务、测试
frontend/      图谱交互、行为分析、报告和任务进度界面
crawler/       独立采集服务及其测试
scripts/       数据转换、抽取、导入、导出与评测
config/        审核工件清单与样例配置
data/          标准文档、Golden、抽取工件及本地运行数据
docs/          架构、契约、指南与研究记录
```

后端与采集测试：

```bash
docker compose build backend crawler
docker compose run --rm backend python -m pytest backend/tests -v
docker compose run --rm crawler python -m pytest crawler/tests -v
```

前端测试、构建与格式检查：

```bash
docker compose build frontend
docker compose run --rm frontend npm run test
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run format:check
```
