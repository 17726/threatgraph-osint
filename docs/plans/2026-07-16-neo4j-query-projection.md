# Neo4j 查询投影、增量同步与路径查询实施计划

## 目标

在不改变 SQLite 唯一事实源地位的前提下，实现可清空重建的 Neo4j 查询投影、基于 SQLite
变更水位的幂等增量同步、同步状态接口和 Neo4j 优先/SQLite 降级的多跳路径查询，满足课程要求中
“多维查询、关联路径追踪、动态更新、可视化”的图谱能力。

## #47 评审结论

可以迁移的设计：

- `Neo4jService` 只读取 `entities`、`relations`、`evidence`。
- SQLite trigger 记录 canonical graph 变更，成功后才推进 Neo4j 水位。
- 使用 canonical ID 做 `MERGE`，Neo4j 失败不回滚 SQLite。
- `/graph/path` 优先使用 Cypher，失败后回退现有 SQLite BFS。

原样合入前必须修复：

- `MATCH (n) DETACH DELETE n` 会删除同库中不属于本项目的节点；只允许删除带项目投影标签的节点。
- 全量重建在释放 SQLite 读快照后才读取最大 change ID，可能跳过并发写入；实体、关系、证据和
  snapshot watermark 必须来自同一个 SQLite 读事务。
- 全量写入缺少显式 Neo4j 事务、唯一约束和关系索引，失败时可能留下半成品投影。
- 初始水位不能证明既有 SQLite 数据已全量同步；首次增量前必须要求完成 rebuild。
- `sync_state` 需要记录 `status`、`last_attempt_at`、`last_success_at`、`last_full_sync_at` 和稳定错误，
  不能只保存一个整数。
- Neo4j 属性需要显式提供 `canonical_updated_at` 和 `sync_version`，不能把 SQLite 列无选择地透传。
- 路径深度必须有后端固定上限，Cypher 不能拼接用户提供的关系类型；Neo4j 异常由调用层明确降级。
- 同步错误响应不能暴露 URI、认证信息或宿主机路径。

## 提交与身份

1. 第一笔迁移提交只放 #47 的 Neo4j 服务、同步 schema、依赖和原测试，Author 保留
   `yzq38 <1825904177@qq.com>`，维护者作为 Committer。
2. 后续测试、修复、API、文档和集成验证由维护者作为 Author/Committer。
3. 不使用 `Co-authored-by` 混淆独立迁移与维护者修复。

## Task 1：迁移 #47 Neo4j 子集

- 新增 `backend/app/services/neo4j_service.py`。
- 新增 `backend/tests/test_neo4j_service.py`。
- 在 `backend/app/db/schema.py` 增加原同步表和 trigger。
- 在 `DemoStore` 初始化后创建同步 schema。
- 增加 Neo4j Python Driver 依赖。

迁移后先记录基线失败，不以 #47 的 mock 测试通过作为可合入结论。

## Task 2：用失败测试冻结投影边界

新增测试覆盖：

- rebuild 只删除带项目 ownership 的关系和 `ThreatGraphProjection` 节点；项目节点存在外部关系时
  非 `DETACH` 删除必须失败并回滚。
- 同一 SQLite 快照读取 canonical 数据和 watermark。
- 创建实体唯一约束、证据唯一约束、关系 ID 索引。
- Neo4j 写入在一个显式 transaction 中完成，失败不推进水位。
- 首次 incremental 在未 full rebuild 时返回 `requires_rebuild`。
- 同步状态持久化成功、失败、尝试时间和错误码，错误不泄露敏感连接信息。
- 删除/更新/重复增量均按 canonical ID 幂等，关系端点缺失不推进水位。
- 投影属性包含 `canonical_updated_at`、`sync_version`、`evidence_ids`。
- 同一服务实例的 rebuild/incremental 串行执行，旧快照不能覆盖新投影或回退水位。
- 证据变更同时刷新新旧 entity/relation owner 的聚合 `evidence_ids`。

## Task 3：修复全量重建与增量同步

- 扩展 `sync_state`，兼容旧表增量迁移。
- SQLite triggers 记录 `entities`、`relations`、`evidence` 的 upsert/delete；证据变更额外记录新旧
  owner 的刷新事件。
- rebuild 在一个 SQLite 快照中读取数据和上界，在 Neo4j write transaction 中删除本项目投影并重建。
- 增量按 `(watermark, upper_bound]` 读取 outbox，写入成功后原子推进 SQLite 水位。
- 更新状态时不影响 canonical 表；失败保留原水位。
- driver 未配置、连接失败和写入失败返回稳定状态，不阻塞 SQLite API。

## Task 4：接入状态、同步与路径 API

实现：

```text
GET  /api/v1/neo4j/status
POST /api/v1/neo4j/rebuild
POST /api/v1/neo4j/sync
GET  /api/v1/graph/path
```

- status 同时返回连接状态、SQLite 水位、待同步变更数和最后同步状态。
- rebuild 明确执行全量重建；sync 只执行增量同步。
- path 只遍历本项目节点和关系；连接失败、查询失败、同步失败、水位落后或无可用投影时回退
  SQLite BFS，并返回实际 `engine`。
- 前端继续只调用 FastAPI，不直接访问 Neo4j。
- Pipeline canonical 提交成功后可做 best-effort 增量同步；Neo4j 失败只写入结果摘要，不把 SQLite
  Pipeline 反向改为失败。

## Task 5：真实容器验收与文档

- 更新 README、TODO、API/数据契约和架构“尚未落地”状态。
- 使用独立 SQLite 导入固定 reviewed 工件。
- 启动 Neo4j 容器，执行 rebuild，记录节点/关系/证据数量和水位。
- 再导入一份工件，执行 incremental，验证只推进新增水位且重复执行 changes=0。
- 清空本项目 Neo4j 投影后再次 rebuild，证明 Neo4j 不持有唯一事实。
- 用同一 source/target 验证 Neo4j path 与 SQLite fallback 响应结构兼容。

## 验证命令

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
docker compose run --rm --no-deps frontend npm run test
docker compose run --rm --no-deps frontend npm run build
docker compose config --quiet
git diff --check
```

真实 Neo4j 验收需要先启动：

```powershell
docker compose up -d neo4j
```
