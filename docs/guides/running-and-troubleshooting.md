# 运行与排障

基础启动和无需 API Key 的审核样例见 [上手指南](getting-started.md)。本文补充任务追踪、运行产物和可选 Neo4j 查询层的操作。

## 服务与数据

| 服务     | 访问方式                             | 职责                                   |
| -------- | ------------------------------------ | -------------------------------------- |
| frontend | `http://localhost:5173`              | 图谱、分析、报告和任务进度             |
| backend  | `http://localhost:8000`              | 文档导入、抽取编排、SQLite 查询与分析  |
| crawler  | Compose 内部 `http://crawler:8100`   | 来源采集、清洗、过滤，不映射宿主机端口 |
| neo4j    | `http://localhost:7474`；Bolt `7687` | 可选的图查询投影                       |

基础启动：

```bash
docker compose up --build -d backend frontend
```

启用采集（先在 `.env` 中配置 `LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`）：

```bash
docker compose up --build -d backend frontend crawler
```

`docker compose up --build -d` 会启动包括 Neo4j 在内的全部服务。环境变量更新后需要重新执行 `up` 使相关容器应用配置。

SQLite 保存在宿主机 `data/threatgraph_osint.db`。`docker compose down` 不删除该文件；`docker compose down -v` 会额外删除 Compose 管理的 Neo4j 数据卷和日志卷，仍不会删除宿主机 `data/` 中的文件。

## 任务进度与日志

采集链路为：前端 → backend 创建采集任务 → crawler 采集与过滤 → backend 导入标准文档 → `live` Pipeline 抽取、校验和建图。

前端弹窗显示采集任务 ID、子 Pipeline 任务 ID、当前来源/文档、阶段进度和最近事件。Pipeline 状态接口为 `GET /api/v1/pipeline/status/{job_id}`，采集状态接口为 `GET /api/v1/crawl/runs/{crawl_run_id}`。

查看服务与日志：

```bash
docker compose ps
docker compose logs --tail=100 backend crawler
docker compose logs -f backend crawler
```

PowerShell 下按事件或前端显示的任务 ID 过滤：

```powershell
docker compose logs backend crawler | Select-String 'pipeline_event|crawl_event'
docker compose logs backend crawler | Select-String '<前端显示的 crawl_ 或 job_ 任务 ID>'
```

单篇文档出现 LLM 网络或解析错误时，会记入 `filter_summary.failed_documents`，其余成功过滤的文档继续处理，任务状态为 `partial_success`。脚本崩溃、配置缺失或目录损坏等批次级错误仍会中止任务。采集状态保存在 backend 内存，服务重启后不能依赖旧任务 ID 查询历史。

## 本地运行产物

| 路径                                       | 内容                                               |
| ------------------------------------------ | -------------------------------------------------- |
| `data/threatgraph_osint.db`                | SQLite 运行时事实源                                |
| `data/graph/graph.json`                    | 显式导出的图谱快照                                 |
| `data/run_logs/run-log-<run_id>.json`      | CLI 抽取阶段耗时、API 调用次数和 Token 用量        |
| `data/run_logs/pipeline-run-<job_id>.json` | 前端/API 发起的 live Pipeline 摘要                 |
| `data/run_artifacts/<run_id>*.json`        | live Pipeline 的 Extraction 与 Candidate Audit     |
| `data/crawl_runs/<crawl_run_id>/`          | 实际产生的采集、清洗、过滤、待导入文档、进度与摘要 |

上述任务日志、live Pipeline 工件和采集归档属于被 Git 忽略的本地产物。CLI 的候选结果路径和评测产物另见 [抽取指南](llm-extraction-and-evaluation.md)。CLI 可用 `--run-log-dir <目录>` 指定运行摘要目录；等待 LLM 时默认每 30 秒输出心跳，`--heartbeat-seconds 0` 可关闭。

live Pipeline 失败或进程中断时保留运行摘要，已生成的候选工件不会因后续 SQLite 导入失败而删除。重启时以 SQLite 任务终态对账摘要；损坏的本机档案不会阻止服务恢复。

`reviewed` 模式不会自动消费 `data/run_artifacts/`。工件经过评审并迁入 `data/extracted/`，登记到 `config/reviewed-extractions.json` 或已有样例清单后，才可作为审核输入使用。

## 可选 Neo4j 查询层

基础图谱使用 SQLite 即可。要启用 Neo4j，先在 `.env` 配置其账号密码，再启动：

```bash
docker compose up -d backend neo4j
```

等待 Neo4j 启动完成后，通过 [Swagger UI](http://localhost:8000/docs) 依次调用：

1. `POST /api/v1/neo4j/rebuild`：首次从 SQLite 全量重建项目投影。
2. `GET /api/v1/neo4j/status`：检查初始化和同步水位。
3. `POST /api/v1/neo4j/sync`：需要时手动触发幂等增量同步。

默认 Pipeline 成功写入 SQLite 后会尝试增量同步；Neo4j 不可用或尚未初始化时，SQLite 任务仍保持成功，结果中的 `neo4j_sync` 说明投影状态。CLI 离线导入后也可以手动重建或同步投影。

`GET /api/v1/graph/path` 在投影就绪且水位追平时优先使用 Neo4j；连接失败、查询失败、未初始化或有待同步变更时回退 SQLite，并返回 `fallback_reason`。

全量重建替换带项目 ownership 的图数据。若同库其他图为项目节点增加了外部关系，重建会失败并回滚，不会静默删除外部关系。

## 常见问题

| 现象                   | 检查方式                                                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 页面正常但图谱为空     | 首次启动不填充数据；先导入样例，再选择 APT28 并刷新                                                                            |
| “采集情报”按钮禁用     | 检查三项 LLM 配置是否非空，重新运行 Compose `up` 并刷新页面；配置存在不代表密钥有效，可另做预检                                |
| 采集后只有部分文档入图 | 检查任务 `partial_success`、失败文档摘要及 `data/crawl_runs/` 中的归档                                                         |
| 路径查询回退 SQLite    | 查看 `fallback_reason` 和 Neo4j 状态，必要时重建或增量同步                                                                     |
| 无法连接 Docker API    | 确认 Docker 引擎已启动，Docker Desktop 使用 Linux 容器                                                                         |
| crawler 需要代理       | 按 `.env.example` 配置 `CRAWLER_PROXY_HOST` / `CRAWLER_PROXY_PORT`；Docker Desktop 访问宿主机代理可使用 `host.docker.internal` |

完整字段与错误码见 [API 契约](../api-contract.md)。
