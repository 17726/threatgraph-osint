# ThreatGraph-OSINT 后端多维查询与自动流水线设计

> 日期：2026-07-15
> 状态：已确认，进入实施计划

## 1. 目标与边界

本次实现补齐以下能力：

- 后端多维图谱查询，避免前端对全量图谱做客户端过滤。
- Neo4j 查询投影、全量重建、幂等增量同步和多跳路径查询。
- 统一流水线入口，自动执行抽取、归一化、建图、行为分析、推理、报告和 Neo4j 同步。
- 文档导入后自动触发流水线。
- SQLite 任务状态、进程内后台任务和轻量定时调度。
- SQLite 增量更新与 Neo4j 增量同步。

SQLite 仍是运行时 canonical 事实源。Neo4j 只保存由 SQLite 已验证实体、关系和证据构建的可重建查询投影，不能反向写入 SQLite，也不能接收 LLM 原始输出。

`data/documents/<target_group>/*.json` 按已清洗标准文档处理，使用 `clean_text`、`content_hash`、来源元数据和目标组织字段。对常见 `text`、`raw_text`、`content` 字段提供轻量适配；缺少必要字段时拒绝导入并返回契约错误，不静默猜测来源。

## 2. 服务边界

新增按职责拆分的服务：

- `document_adapter.py`：标准文档校验和有限字段适配。
- `graph_query_service.py`：SQLite 多维查询、过滤、BFS 和证据裁剪。
- `neo4j_service.py`：连接状态、索引约束、全量重建、增量同步和 Cypher 查询。
- `pipeline_service.py`：流水线步骤编排、任务状态和文档级幂等执行。
- `scheduler_service.py`：FastAPI 进程内定时扫描和自动触发。

`DemoStore` 保留演示数据初始化及兼容基础能力；API 路由逐步委托给新服务，避免继续扩大单体类职责。

## 3. 多维查询

扩展 `GET /api/v1/graph` 参数：

- `target`：目标组织、实体名称、别名或实体 ID。
- `entity_types`、`relation_types`、`tags`、`source_types`、`languages`：逗号分隔的多值过滤。
- `first_seen_from`、`last_seen_to`：时间范围过滤。
- `min_confidence`：最低置信度。
- `depth`：目标节点展开跳数。
- `limit`：结果节点上限。

SQLite 路径使用参数化 SQL，并在目标节点和过滤条件下执行 BFS；只返回关联证据。响应保留当前 `nodes`、`edges`、`evidence` 结构，增加 `engine`、`filters` 和结果统计字段。无过滤参数时保持现有兼容行为。

`GET /api/v1/graph/path` 增加 `max_depth`、可选 `relation_types` 和 `min_confidence`。Neo4j 可用时优先使用 Cypher；不可用时降级到 SQLite BFS，并明确返回实际 `engine`。

## 4. Neo4j 投影与增量同步

新增同步状态表，记录 SQLite canonical graph 的变更水位、最后成功同步时间、同步状态和错误信息。所有正式实体、关系、证据写入或更新后产生可比较的更新时间/版本水位。

同步策略：

1. 支持从 SQLite 全量清空并重建 Neo4j，验证 Neo4j 可丢失后可恢复。
2. 增量同步按 SQLite 变更水位读取新增或更新实体、关系、证据，使用 `MERGE` 幂等写入。
3. 同步成功后推进水位；失败时保留旧水位和错误状态，不污染 SQLite。
4. Neo4j 连接失败不阻塞 SQLite 流水线，任务状态记录为降级或同步失败。
5. Neo4j 建立实体唯一约束/索引，关系使用正式 `relation_id` 作为稳定身份。

## 5. 统一流水线与自动触发

实现：

```text
POST /api/v1/pipeline/run
GET  /api/v1/pipeline/status/{job_id}
```

默认步骤：

```text
extract -> normalize -> build_graph -> analyze_behavior -> infer -> report -> neo4j_sync
```

请求可以传 `doc_id`、`target_group`、`use_cache` 和 `steps`；指定步骤时按依赖顺序执行。已有离线抽取、归一化、分析和报告服务通过适配器接入，不重复实现业务规则。

任务记录保存 job ID、目标范围、当前步骤、状态、开始/结束时间、错误信息和各步骤摘要。API 启动 FastAPI 后台任务后立即返回 job ID；状态接口返回可重试的失败步骤。

文档导入成功后，在同一应用进程中提交该文档的默认流水线任务。导入事务先提交，任务再启动；重复导入不重复创建相同文档任务。

## 6. 定时调度

使用进程内轻量调度器，不引入 Redis、Celery 或独立 worker。应用启动时读取环境变量配置调度间隔，后台周期性扫描：

- 已导入但尚未成功处理的文档。
- Neo4j 水位落后的增量同步任务。
- 失败且允许重试的任务。

应用关闭时停止调度循环。单进程内使用任务锁避免同一文档或同步水位重复运行；多副本部署不作为本次目标。

## 7. 错误与降级

- 文档契约错误：导入失败，返回统一校验错误。
- 抽取/分析/报告失败：SQLite 保留任务和已有中间结果，状态接口返回失败步骤和错误信息。
- Neo4j 不可用：图谱普通查询使用 SQLite，路径查询降级 SQLite，流水线标记同步失败但不回滚 canonical graph。
- 查询无结果：返回空节点、空边和空证据，不返回前端难以处理的异常。

## 8. 验证要求

新增后端测试覆盖：

- 多维类型、标签、时间、置信度和深度过滤。
- 别名/名称/ID 目标匹配和 SQLite 路径降级。
- Neo4j mock 下的全量重建、幂等增量同步和失败保留水位。
- 流水线步骤顺序、任务状态、重复任务和导入后自动触发。
- 非标准文档适配及契约错误。

完成后运行：

```text
python -m pytest backend/tests -v
npm --prefix frontend run build
```

无法运行 Docker/Neo4j 集成验证时，使用 mock 驱动测试并在结果中明确说明。
