# 后端多维查询与自动流水线实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不使用 Docker 的前提下，补齐 SQLite 后端多维查询、Neo4j 查询投影与增量同步、统一流水线、导入后自动触发和进程内定时调度。

**Architecture:** SQLite 继续作为唯一事实源。查询服务负责 SQLite 多维过滤和 BFS 降级；Neo4j 服务只同步已验证 canonical graph，并在可用时承担多跳查询。流水线服务通过 FastAPI `BackgroundTasks`/进程内任务执行器编排现有抽取、归一化、分析、报告逻辑，调度器扫描未完成文档和同步水位。

**Tech Stack:** Python 3.13、FastAPI、SQLite、Neo4j Python Driver、pytest、React/Vite。

---

## 文件结构与职责

**新增：**

- `backend/app/services/document_adapter.py`：标准文档校验、`text`/`raw_text`/`content` 到 `clean_text` 的有限适配。
- `backend/app/services/graph_query_service.py`：SQLite 图查询、多维过滤、邻接 BFS、证据裁剪。
- `backend/app/services/neo4j_service.py`：Neo4j 连接、状态、全量重建、幂等增量同步、路径查询。
- `backend/app/services/pipeline_service.py`：任务表、任务状态、步骤编排、自动触发。
- `backend/app/services/scheduler_service.py`：进程内周期扫描器。
- `backend/tests/test_graph_query_service.py`：多维过滤与 SQLite 路径测试。
- `backend/tests/test_document_adapter.py`：标准文档与非标准字段适配测试。
- `backend/tests/test_neo4j_service.py`：mock driver 全量/增量同步测试。
- `backend/tests/test_pipeline_service.py`：步骤顺序、幂等任务、失败状态测试。

**修改：**

- `backend/app/services/demo_store.py`：补充查询所需 schema/变更水位，并委托或复用新服务；保留现有 demo seed 兼容行为。
- `backend/app/main.py`：注册多维查询、路径参数、pipeline 接口、生命周期调度器和导入后自动触发。
- `backend/app/db/schema.py`：增加 pipeline jobs、同步水位和 canonical 变更记录表的初始化迁移。
- `docker-compose.yml`：不作为本次运行方式依赖；仅保留已有配置，Neo4j 环境变量从本地进程环境读取。
- `.env.example`：补充 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`、调度间隔和自动触发开关（如已有则只校正说明）。

---

### Task 1: 建立标准文档适配边界

**Files:**
- Create: `backend/app/services/document_adapter.py`
- Test: `backend/tests/test_document_adapter.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 编写失败测试**

覆盖三种行为：已有 `clean_text` 原样保留并校验 hash；`text`/`content` 可转换为 `clean_text`；缺少 `doc_id`、`target_group`、`title`、`language` 或正文时抛出契约错误。

```python
def test_adapt_standard_document_keeps_clean_text():
    document = make_document(clean_text="APT28 使用 X-Agent")
    assert adapt_document(document)["clean_text"] == "APT28 使用 X-Agent"


def test_adapt_legacy_text_field():
    document = make_document(clean_text=None) | {"text": "APT28 使用 X-Agent"}
    adapted = adapt_document(document)
    assert adapted["clean_text"] == "APT28 使用 X-Agent"
    assert adapted["content_hash"].startswith("sha256:")


def test_reject_document_without_required_fields():
    with pytest.raises(DocumentContractError):
        adapt_document({"doc_id": "doc-1", "clean_text": "正文"})
```

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m pytest backend/tests/test_document_adapter.py -v`

预期：因模块或函数尚未存在而失败。

- [ ] **Step 3: 实现最小适配器**

使用现有 `require_valid_document` 和 `document_content_hash`；只允许明确的正文别名，不推断来源信息。适配后补齐 `schema_version`、`target_groups`、`content_hash`、`tags`、`metadata` 的默认值，并返回标准字典。

- [ ] **Step 4: 接入导入接口**

在 `main.py` 的 `/documents/import` 路由调用 `adapt_document`，契约错误转换为统一 400 错误；成功后才调用 store 导入。

- [ ] **Step 5: 运行测试**

运行：`python -m pytest backend/tests/test_document_adapter.py backend/tests/test_document_contract.py -v`

预期：全部通过。

---

### Task 2: 实现 SQLite 多维图查询

**Files:**
- Create: `backend/app/services/graph_query_service.py`
- Test: `backend/tests/test_graph_query_service.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 编写失败测试**

测试类型、标签、置信度、时间、关系类型、别名目标和深度过滤；断言返回节点、边、证据以及 `engine == "sqlite"`。

```python
def test_graph_query_filters_type_tag_confidence_and_depth(store):
    result = GraphQueryService(store.db_path).get_graph(
        target="Fancy Bear",
        entity_types=["MALWARE"],
        tags=["security_report"],
        min_confidence=0.85,
        depth=1,
    )
    assert result["engine"] == "sqlite"
    assert {node["type"] for node in result["nodes"]} <= {"MALWARE"}
    assert all(node["confidence"] >= 0.85 for node in result["nodes"])


def test_path_filters_relation_type_and_depth(store):
    result = GraphQueryService(store.db_path).get_path(
        "apt_group:apt28", "malware:x-agent", max_depth=2,
        relation_types=["USES"],
    )
    assert result["engine"] == "sqlite"
    assert result["paths"][0]["edges"][0]["type"] == "USES"
```

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m pytest backend/tests/test_graph_query_service.py -v`

预期：服务尚未存在而失败。

- [ ] **Step 3: 实现参数化 SQLite 查询**

将查询参数统一为 `GraphFilters` 数据结构。实体过滤使用 `type`、`confidence`、时间字段和 `tags_json`；目标匹配 `entity_id`、`name`、`aliases_json`，并对目标节点做 BFS。关系过滤使用类型、置信度、时间和端点集合。所有 SQL 值使用绑定参数，不能拼接用户输入。

- [ ] **Step 4: 保持旧响应兼容**

无过滤条件时返回现有 `schema_version/nodes/edges/evidence`，新增 `engine`、`filters`、`stats` 不破坏前端字段。证据只保留属于可见节点或关系的记录。

- [ ] **Step 5: 接入 API 参数**

扩展 `GET /api/v1/graph`：`entity_types`、`relation_types`、`tags`、`source_types`、`languages`、`first_seen_from`、`last_seen_to`、`min_confidence`、`depth`、`limit`。扩展 path 的 `max_depth`、`relation_types`、`min_confidence`。

- [ ] **Step 6: 运行测试**

运行：`python -m pytest backend/tests/test_graph_query_service.py backend/tests/test_api.py -v`

预期：新增测试和已有 API 测试全部通过。

---

### Task 3: 实现 Neo4j 查询投影与同步

**Files:**
- Create: `backend/app/services/neo4j_service.py`
- Test: `backend/tests/test_neo4j_service.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/services/demo_store.py`

- [ ] **Step 1: 编写 mock driver 失败测试**

mock `neo4j.GraphDatabase.driver`，验证连接检查、约束创建、全量同步、重复增量同步不会重复写入，以及 driver 异常不推进水位。

```python
def test_incremental_sync_is_idempotent_and_advances_watermark(db, fake_driver):
    service = Neo4jService(db, driver_factory=lambda: fake_driver)
    first = service.sync_incremental()
    second = service.sync_incremental()
    assert first["status"] == "succeeded"
    assert second["changed"] == 0
    assert read_watermark(db) == first["watermark"]
```

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m pytest backend/tests/test_neo4j_service.py -v`

预期：同步服务或状态表尚未存在而失败。

- [ ] **Step 3: 增加 SQLite 状态和变更记录**

在 schema 初始化中增加 `graph_changes(change_id, entity_id, relation_id, evidence_id, changed_at, operation)`、`sync_state(name, watermark, status, last_success_at, error_message)`。canonical 实体、关系、证据写入路径记录变更。

- [ ] **Step 4: 实现 Neo4j 服务**

通过环境变量连接 Neo4j；启动时创建实体/关系唯一约束。全量重建先删除投影节点和关系，再按 SQLite 顺序写实体、关系、证据。增量同步按 `changed_at > watermark` 查询，使用稳定 ID `MERGE`，所有同步成功后一次性更新 SQLite 水位。

- [ ] **Step 5: 实现 Neo4j 路径查询和 SQLite 降级**

Cypher 只允许使用固定关系类型片段或参数化过滤；限制 `max_depth` 和结果数量。连接失败时由调用层回退 `GraphQueryService.get_path`。

- [ ] **Step 6: 运行测试**

运行：`python -m pytest backend/tests/test_neo4j_service.py backend/tests/test_db_schema.py -v`

预期：mock 同步测试和 schema 测试通过。

---

### Task 4: 建立统一流水线任务服务

**Files:**
- Create: `backend/app/services/pipeline_service.py`
- Test: `backend/tests/test_pipeline_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/demo_store.py`

- [ ] **Step 1: 编写失败测试**

使用可注入的步骤函数测试顺序、成功状态、重复 job 和失败步骤保存。

```python
def test_pipeline_runs_steps_in_order(db):
    calls = []
    service = PipelineService(db, steps={name: lambda: calls.append(name) for name in DEFAULT_STEPS})
    job = service.run_sync(target_group="APT28")
    assert calls == DEFAULT_STEPS
    assert service.status(job["job_id"])["status"] == "succeeded"


def test_pipeline_failure_keeps_failed_step(db):
    service = PipelineService(db, steps={"extract": lambda: (_ for _ in ()).throw(ValueError("bad"))})
    job = service.run_sync(doc_id="apt28_032", steps=["extract"])
    assert service.status(job["job_id"])["failed_step"] == "extract"
```

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m pytest backend/tests/test_pipeline_service.py -v`

预期：任务服务尚未存在而失败。

- [ ] **Step 3: 增加任务表和状态模型**

建立 `pipeline_jobs` 与 `pipeline_job_steps` 表，记录 job、范围、步骤、状态、当前步骤、时间、摘要、错误和重试次数。使用 SQLite 事务创建 job；同一目标范围存在 running/pending job 时返回已有 job。

- [ ] **Step 4: 接入现有业务实现**

默认顺序固定为：`extract`、`normalize`、`build_graph`、`analyze_behavior`、`infer`、`report`、`neo4j_sync`。步骤适配现有离线抽取、归一化、规则分析、推理和报告生成逻辑；没有可执行的抽取输入时记录清晰失败，不伪造抽取结果。

- [ ] **Step 5: 增加 API**

实现 `POST /api/v1/pipeline/run`，支持 `doc_id`、`target_group`、`use_cache`、`steps`，创建后台任务并立即返回 job ID；实现 `GET /api/v1/pipeline/status/{job_id}`。

- [ ] **Step 6: 运行测试**

运行：`python -m pytest backend/tests/test_pipeline_service.py backend/tests/test_api.py -v`

预期：任务服务和 API 测试通过。

---

### Task 5: 导入后自动触发和进程内定时调度

**Files:**
- Create: `backend/app/services/scheduler_service.py`
- Test: `backend/tests/test_scheduler_service.py`
- Modify: `backend/app/main.py`
- Modify: `.env.example`

- [ ] **Step 1: 编写失败测试**

```python
def test_scheduler_submits_pending_document_once(db):
    pipeline = FakePipeline()
    scheduler = SchedulerService(db, pipeline, interval_seconds=1)
    scheduler.scan_once()
    scheduler.scan_once()
    assert pipeline.submitted_doc_ids == ["apt28_032"]
```

- [ ] **Step 2: 运行测试确认失败**

运行：`python -m pytest backend/tests/test_scheduler_service.py -v`

预期：调度服务尚未存在而失败。

- [ ] **Step 3: 实现扫描器**

从 SQLite 扫描未成功处理文档和未完成 Neo4j 水位，使用进程内 `asyncio.Lock`/任务集合去重；通过 `THREATGRAPH_SCHEDULER_ENABLED` 和 `THREATGRAPH_SCHEDULER_INTERVAL_SECONDS` 控制。默认关闭调度，避免开发重载时重复执行；用户开启后由应用 startup 创建后台循环，shutdown 取消任务。

- [ ] **Step 4: 接入导入自动触发**

`import_document` 事务成功后调用 pipeline submit；跳过重复文档时不新建任务。自动触发默认遵循 `THREATGRAPH_AUTO_PIPELINE_ENABLED`，开发环境可显式开启。

- [ ] **Step 5: 运行测试**

运行：`python -m pytest backend/tests/test_scheduler_service.py backend/tests/test_api.py -v`

预期：调度、导入触发和 API 测试通过。

---

### Task 6: 更新本地运行说明与回归验证

**Files:**
- Modify: `README.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/stage-roadmap.md`

- [ ] **Step 1: 更新契约**

补充 graph 多维查询参数、pipeline 请求/状态响应、Neo4j engine 降级语义和本地 uvicorn/npm 启动方式；明确 Docker 不属于本次验证路径。

- [ ] **Step 2: 运行后端测试**

运行：`python -m pytest backend/tests -v`

预期：全部通过。

- [ ] **Step 3: 构建前端**

运行：`npm --prefix frontend run build`

预期：构建成功。

- [ ] **Step 4: 启动本地后端并检查接口**

在项目根目录运行：`uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload`

检查：`GET http://localhost:8000/api/v1/health`、带过滤参数的 `/api/v1/graph`、`POST /api/v1/pipeline/run` 和对应 status 接口。

- [ ] **Step 5: 启动本地前端**

在 `frontend` 目录运行：`npm run dev`

确认前端继续通过 FastAPI 获取图谱，过滤条件由后端传递，不依赖前端全量过滤。

- [ ] **Step 6: 记录 Neo4j 验证边界**

若本机未运行 Neo4j，保留 mock driver 测试结果，并在最终说明中明确：SQLite 多维查询、路径降级和流水线已验证；Neo4j 真实连接需在本地 Neo4j 服务启动后再执行集成验证。

---

## 自审结论

- 设计文档中的多维查询、Neo4j 全量/增量同步、统一流水线、导入后触发、定时调度和降级路径均有对应任务。
- 计划遵守 SQLite 唯一事实源，不引入 Redis、Celery 或 Docker 运行依赖。
- 本地验证命令采用用户指定的 `uvicorn` 和 `npm run dev`；测试使用 Python pytest 和前端 build。
- 新增服务之间通过明确的数据库和方法接口协作，步骤函数可注入，便于 mock 测试。
