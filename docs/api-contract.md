# API 契约

> 适用范围：ThreatGraph-OSINT 项目  
> 后端：FastAPI  
> 前端：React + TypeScript + Vite  
> 数据源：SQLite，Neo4j 只做增强阶段 / 优先级 P1 的图查询增强

---

## 1. 通用响应

成功响应：

```json
{
  "success": true,
  "data": {},
  "timestamp": "2026-07-06T22:30:00+08:00"
}
```

失败响应：

```json
{
  "success": false,
  "error": {
    "code": "ERR_VALIDATION",
    "message": "请求参数不合法",
    "details": {}
  },
  "timestamp": "2026-07-06T22:30:00+08:00"
}
```

---

## 2. 系统接口

```text
GET /api/v1/health
```

返回：

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "components": {
      "sqlite": "ok",
      "neo4j": "disconnected",
      "llm": "configured"
    }
  }
}
```

---

## 3. 采集接口

```text
GET  /api/v1/sources
POST /api/v1/sources
POST /api/v1/collection-runs
GET  /api/v1/collection-runs/{collection_run_id}
```

第一阶段可以先跳过网络采集，通过本地文本或 `data/documents/<target_group>/*.json` 导入文档。课程验收增强阶段再实现三类来源的最小自动采集闭环，并写入 SQLite。复杂定时调度、增量 checkpoint、复杂去重和新情报自动入图属于后续增强。

三容器自动采集使用以下接口：

```text
POST /api/v1/crawl/runs
GET  /api/v1/crawl/runs/{crawl_run_id}
```

开发阶段浏览器可以直接访问宿主机暴露的 backend API，但 crawler 只在 Docker Compose 内部网络提供服务，浏览器不能直接访问 crawler。backend 生成 `crawl_run_id`，查询当前目标组织最大文档编号后计算 `start_number`，再通过 HTTP 调用内部 crawler。任务状态当前只保存在 backend 进程内存中；同一时间已有 `pending` 或 `running` 任务时返回 HTTP 409。

任务状态包括 `pending`、`running`、`succeeded` 和 `failed`。至少成功导入一篇文档时任务为 `succeeded`，单篇失败会继续处理并计入 `items_failed`；没有成功导入文档时任务为 `failed`。

采集固定使用 live Pipeline，因此启动采集前必须配置非空的 `LLM_MODEL`、`LLM_BASE_URL` 和 `LLM_API_KEY`。三项配置任一缺失时，health 的 `components.llm` 为 `not_configured`，`POST /api/v1/crawl/runs` 返回 HTTP 503、错误码 `ERR_LLM_NOT_CONFIGURED` 和消息 `无有效 LLM 配置`；backend 不创建任务，也不调用 crawler。frontend 仍显示“采集情报”按钮，但将其置为 disabled。

采集任务的每篇 promote 文档在调用 `/documents/import` 后，都会继续复用已有的 live Pipeline 接口：先调用 `/pipeline/run` 并固定传入 `extraction_mode=live`，再轮询 `/pipeline/status/{job_id}`。即使文档因 `doc_id` 或 `content_hash` 已存在而返回 `skipped`，也会使用 backend 返回的既有 `doc_id` 继续执行 live Pipeline。crawler 不实现第二套抽取、校验或建图逻辑。

采集状态响应还包含 `source_results`。该字段以文档的 `source_name` 为键，记录每个来源的 `items_promoted`、`items_imported`、`items_skipped`、`items_failed` 和 `items_pipeline_succeeded`。当请求选择多个来源时，只有所有选中来源都达到 `limit` 篇成功完成 live Pipeline，任务才返回 `status=succeeded`；未达标时返回 `failed`，并在 `error_message` 中列出缺失来源。

`POST /sources` 请求：

```json
{
  "source_id": "src_securelist_apt28",
  "name": "Securelist APT Reports",
  "source_type": "vendor_report",
  "collector_type": "http_page",
  "url": "https://securelist.com/masha-and-these-bears/84311/",
  "target_groups": ["APT28"],
  "enabled": true,
  "config": {
    "language": "en",
    "default_target_group": "APT28"
  }
}
```

`POST /collection-runs` 请求：

```json
{
  "source_id": "src_securelist_apt28",
  "target_groups": ["APT28"],
  "limit": 5,
  "write_documents": true
}
```

返回：

```json
{
  "success": true,
  "data": {
    "collection_run_id": "colrun_20260707_001",
    "status": "succeeded",
    "items_found": 1,
    "items_imported": 1,
    "document_ids": ["apt28_049"]
  }
}
```

优先级 P0 支持的输入 / 采集器类型：

```text
local_json：读取 data/documents 下符合 document.schema.json 的本地 JSON 样本
local_text：读取本地手动清洗文本
http_page：抓取单篇安全报告、新闻或公告页面，课程验收增强阶段使用，采集结果需先转换为 document.json
rss_feed：读取 RSS/Atom feed 并抽取条目，课程验收增强阶段使用
```

增强阶段扩展：

```text
scheduled_run：定时任务
checkpoint：增量位置
dedup_policy：去重策略
auto_pipeline：新情报采集后自动触发清洗、抽取、建图
```

---

## 4. 文档接口

```text
GET /api/v1/documents
GET /api/v1/documents/{doc_id}
POST /api/v1/documents/import
```

`POST /documents/import` 请求：

```json
{
  "doc_id": "apt28_049",
  "schema_version": "1.0",
  "target_group": "APT28",
  "target_groups": ["APT28"],
  "source_url": "https://thehackernews.com/2025/06/apt28-uses-signal-chat-to-deploy.html",
  "source_type": "news",
  "source_name": "The Hacker News",
  "title": "APT28 Uses Signal Chat to Deploy BEARDSHELL Malware and COVENANT in Ukraine",
  "language": "en",
  "clean_text": "...",
  "content_hash": "sha256:...",
  "published_at": "2025-06-24",
  "retrieved_at": "2026-07-08T08:01:18Z",
  "source_reliability": "B",
  "tlp": "TLP:CLEAR",
  "tags": ["APT28", "CERT-UA", "Malware", "Phishing", "Ukraine", "news"],
  "metadata": {}
}
```

说明：

1. 请求体必须使用 `application/json`，并完整满足 `docs/schemas/document.schema.json`；旧的 `raw_text`、`text` 或 `content` 字段不会被自动当作 `clean_text`。
2. `schema_version` 必填，用于避免数据、LLM、后端和前端字段漂移。
3. `target_group` 是主目标组织，`target_groups` 可保存多个相关组织。
4. `content_hash` 用于重复导入判断，固定为 `sha256(clean_text 按 UTF-8 编码后的字节)`；值与正文不一致时返回 HTTP 400 和 `ERR_VALIDATION`。
5. `doc_id` 或 `content_hash` 已存在时不会重复写入，响应中的 `status` 为 `skipped`，`doc_id` 为首次导入记录的标识。
6. `source_reliability` 优先使用 `A/B/C/D/unknown`，P0 可先人工填写。
7. `published_at` 不确定时允许为 `null`，但 `retrieved_at` 必须保留。
8. 导入成功后由后端基于 `clean_text` 生成 `chunks`，data 组不在 `document.json` 中手写 chunks。

---

## 5. 流水线接口

```text
POST /api/v1/pipeline/run
GET  /api/v1/pipeline/status/{job_id}
```

请求：

```json
{
  "doc_id": "apt28_049",
  "extraction_mode": "reviewed"
}
```

说明：

1. 前端先调用文档导入接口，再由用户显式调用本接口；文档导入不会自动产生 LLM 费用。
2. 接口创建后台任务并返回 HTTP 202。调用方使用返回的 `job_id` 轮询状态接口，直到 `succeeded` 或 `failed`。
3. `extraction_mode=reviewed` 只消费仓库中已有的已审核抽取结果，真实操作名为 `import_extraction_and_build`；缺少已审核结果时明确失败，不隐式调用 LLM。
4. `extraction_mode=live` 显式调用后端配置的 `LLMExtractionService`，真实操作名为 `extract_and_build`；模型输出先通过 extraction_result 契约校验，再由现有 `OfflineExtractionPipeline` 归一化并写入 SQLite。
5. `use_cache` 已废弃且会返回 HTTP 400。抽取模式必须使用含义明确的 `reviewed` 或 `live`，不能用布尔值同时表达“缓存偏好”和“外部调用授权”。
6. `doc_id` 和 `target_group` 必须且只能提供一个。为避免一次误触发大量模型调用，`live` 只允许 `doc_id`；`reviewed` 可按目标组织运行，并按 `doc_id` 排序处理 SQLite 中的匹配文档。
7. 同一作用域和抽取模式的 `pending` / `running` 请求复用活动任务，且只向后台执行器提交一次；执行前仍通过条件更新原子认领。
8. `pipeline_jobs` 和 `pipeline_job_steps` 持久化任务、结果、错误和时间信息。服务启动时把遗留的 `running` 标记为中断失败，并以 SQLite 终态对账已有 live 运行档案；档案缺失、损坏或不可写不阻塞 SQLite 恢复。服务正常关闭时等待在途任务结束。
9. `live` 模式在调用 SQLite 导入前，将 Extraction 与同 `run_id` 的 Candidate Audit 持久化到本机 `data/run_artifacts/`，并将 `running / succeeded / failed`、工件路径、SHA-256、LLM 调用观测和导入摘要写入 `data/run_logs/pipeline-run-<job_id>.json`。这些目录默认被 Git 忽略，不新增 `data/pipeline_*` 运行时目录。
10. 流水线只有一个真实复合步骤，不为已经包含在离线流水线中的归一化、建图、分析和报告伪造独立成功状态。
11. `live` 状态响应的 `run_archive` 用于定位本机运行档案；任务尚未开始时为 `null`。档案损坏时返回 `status=unavailable`，不能阻止 SQLite 中断恢复。档案只记录候选输出和运行观测，不改变 SQLite 作为 canonical 事实源的地位。
12. `reviewed` 只读取 `config/course-demo.json` 或 `config/reviewed-extractions.json` 显式登记的工件，不扫描运行目录，也不会把刚生成的 live 结果自动视为已审核结果。

提交成功响应示例：

```json
{
  "success": true,
  "data": {
    "job_id": "job_0123456789abcdef",
    "doc_id": "apt28_049",
    "target_group": null,
    "extraction_mode": "reviewed",
    "operation": "import_extraction_and_build",
    "status": "running"
  }
}
```

状态值：

```text
pending -> running -> succeeded
                   -> failed
```

`live` 状态响应会额外返回：

```json
{
  "run_archive": {
    "run_log": "data/run_logs/pipeline-run-job_0123456789abcdef.json",
    "status": "succeeded",
    "run_id": "extract-apt28_049-deepseek-v4-flash-1.0-1.0-20260716010000000000-a1b2c3d4",
    "artifacts": {
      "result_path": "data/run_artifacts/extract-apt28_049-deepseek-v4-flash-1.0-1.0-20260716010000000000-a1b2c3d4.json",
      "result_sha256": "...",
      "candidate_audit_path": "data/run_artifacts/extract-apt28_049-deepseek-v4-flash-1.0-1.0-20260716010000000000-a1b2c3d4-candidate-audit.json",
      "candidate_audit_sha256": "..."
    }
  }
}
```

---

## 6. 实体接口

```text
GET /api/v1/entities/search?q=APT28
GET /api/v1/entities/{entity_id}
```

实体详情返回：

```json
{
  "success": true,
  "data": {
    "id": "apt_group:apt28",
    "name": "APT28",
    "type": "APT_GROUP",
    "aliases": ["Fancy Bear", "Sofacy"],
    "description": "...",
    "confidence": 0.96,
    "source_count": 3,
    "first_seen": "2014-01-01",
    "last_seen": "2026-07-01",
    "tags": ["apt", "mitre"],
    "evidence": []
  }
}
```

---

## 7. 图谱接口

```text
GET /api/v1/graph?target=APT28&depth=2
GET /api/v1/graph/neighbors?entity_id=technique:t1566
GET /api/v1/graph/timeline?target=APT28
GET /api/v1/graph/path?source=apt_group:apt28&target=malware:x-agent
```

边界说明：

1. `/api/v1/graph` 返回前端当前使用的轻量图谱视图，字段以本节响应为准。
2. `docs/schemas/graph.schema.json` 约束的是导出的 `data/graph/graph.json` 快照，不要求 API 响应携带 `version`、`generated_at`、`exported_from`、`source_of_truth` 和 `analysis`。
3. 行为分析、MITRE 映射和推理结果默认走第 8 节的 `/analysis/*` 接口；后续如需在图谱接口聚合分析结果，应新增显式参数或新接口。
4. 如果后续要让 API 直接返回完整快照，必须同步更新本文件、前端类型和后端测试。
5. `target` 仅按忽略大小写后的完整实体 ID、完整名称或完整别名匹配；默认 `depth=2`，`depth=0` 只返回中心实体。
6. 列表筛选参数支持重复参数或逗号分隔值，包括 `entity_types`、`entity_ids`、`relation_types`、`tags`、`source_types` 和 `languages`。
7. `first_seen_from` 与 `last_seen_to` 使用区间相交语义：实体或关系的活动区间只要与查询区间相交就保留；边界日期未知时不因时间筛选被排除。
8. 任意筛选和 `limit` 都保证图闭包，返回边的两个端点一定同时存在于 `nodes`；有 `target` 时 `limit` 优先保留中心实体，再按跳数选取邻居。
9. `/graph/neighbors` 专用于实体一跳查询，返回中心实体、直接邻居、连接边及相关证据，不复用组织筛选语义。

图谱响应：

```json
{
  "success": true,
  "data": {
    "schema_version": "1.0",
    "nodes": [
      {
        "id": "apt_group:apt28",
        "name": "APT28",
        "type": "APT_GROUP",
        "aliases": ["Fancy Bear"],
        "description": "...",
        "confidence": 0.96,
        "source_count": 3,
        "first_seen": "2014-01-01",
        "last_seen": "2026-07-01",
        "tags": ["apt", "mitre"],
        "evidence_ids": ["ev_001"]
      }
    ],
    "edges": [
      {
        "id": "rel:apt_group:apt28:USES:malware:x-agent",
        "source": "apt_group:apt28",
        "target": "malware:x-agent",
        "type": "USES",
        "label": "使用",
        "confidence": 0.91,
        "source_count": 2,
        "evidence_count": 1,
        "first_seen": "2015-01-01",
        "last_seen": "2024-12-31",
        "validation_status": "valid",
        "evidence_ids": ["ev_002"]
      }
    ],
    "evidence": [
      {
        "id": "ev_001",
        "doc_id": "apt28_mitre_001",
        "chunk_id": "apt28_mitre_001_c001",
        "entity_id": "apt_group:apt28",
        "relation_id": null,
        "text": "APT28 is a threat group...",
        "evidence_type": "direct_quote",
        "quote_start": 0,
        "quote_end": 27,
        "source_url": "https://attack.mitre.org/groups/G0007/",
        "source_type": "knowledge_base",
        "source_name": "MITRE ATT&CK",
        "published_at": null,
        "retrieved_at": "2026-07-07T00:00:00+08:00",
        "source_reliability": "A",
        "language": "en"
      }
    ]
  }
}
```

说明：

1. `/graph` 默认从 SQLite 查询。
2. `/graph/path` 的 `max_depth` 范围为 1 到 8；关系类型和最小置信度筛选同时作用于 Neo4j 与 SQLite 实现。
3. `/graph/path` 优先使用 Neo4j Cypher 做多跳路径查询。Neo4j 正常返回空路径时不重复查询 SQLite。
4. Neo4j 未配置、投影尚未全量构建或查询失败时，路径接口降级到 SQLite BFS，并增加稳定的 `fallback_reason`。

路径查询返回：

```json
{
  "success": true,
  "data": {
    "source": "apt_group:apt28",
    "target": "malware:x-agent",
    "engine": "neo4j",
    "paths": [
      {
        "nodes": [
          { "id": "apt_group:apt28", "name": "APT28", "type": "APT_GROUP" },
          { "id": "malware:x-agent", "name": "X-Agent", "type": "MALWARE" }
        ],
        "edges": [
          {
            "id": "rel:apt_group:apt28:USES:malware:x-agent",
            "source": "apt_group:apt28",
            "target": "malware:x-agent",
            "type": "USES",
            "label": "使用"
          }
        ],
        "length": 1,
        "evidence_ids": ["ev_002"]
      }
    ]
  }
}
```

---

## 8. 行为分析与推理接口

```text
POST /api/v1/analysis/{target_group}/run
GET  /api/v1/analysis/{target_group}/behavior
GET  /api/v1/analysis/{target_group}/mitre
GET  /api/v1/analysis/{target_group}/inferences
GET  /api/v1/analysis/{target_group}/threat-assessment
```

说明：

1. `behavior` 是行为模式，展示攻击阶段、攻击方式、目标偏好。
2. `mitre` 是 MITRE ATT&CK 映射，展示技术编号、战术和攻击阶段。
3. `inferences` 是智能推理候选关系，不能当作原始事实。
4. `threat-assessment` 是威胁等级和预警建议。

字段含义：

```text
attack_stage：攻击阶段
mitre_mapping：MITRE ATT&CK 映射
behavior_pattern：行为模式
inferred_relation：推断关系
rationale：推理理由
confidence：置信度
evidence_ids：支撑证据
```

行为模式返回：

```json
{
  "success": true,
  "data": {
    "target_group": "APT28",
    "patterns": [
      {
        "pattern_id": "pattern_apt28_initial_access",
        "stage": "初始访问",
        "description": "APT28 常通过鱼叉式钓鱼获得初始访问。",
        "technique_ids": ["T1566"],
        "relation_ids": ["rel:apt_group:apt28:USES:technique:t1566"],
        "evidence_ids": ["ev_001"],
        "confidence": 0.88
      }
    ]
  }
}
```

MITRE 映射返回：

```json
{
  "success": true,
  "data": {
    "target_group": "APT28",
    "mappings": [
      {
        "mapping_id": "mitre_apt28_t1566",
        "technique_id": "T1566",
        "technique_name": "Phishing",
        "tactic": "Initial Access",
        "attack_stage": "初始访问",
        "confidence": 0.9,
        "source": "rule",
        "evidence_ids": ["ev_001"]
      }
    ]
  }
}
```

推理结果返回：

```json
{
  "success": true,
  "data": {
    "target_group": "APT28",
    "inferences": [
      {
        "inferred_relation_id": "infer_apt28_initial_access",
        "source": "apt_group:apt28",
        "target": "technique:t1566",
        "type": "HAS_BEHAVIOR",
        "rationale": "APT28 使用鱼叉式钓鱼技术，该技术属于初始访问阶段。",
        "confidence": 0.86,
        "status": "candidate",
        "evidence_ids": ["ev_001"]
      }
    ]
  }
}
```

威胁评估返回：

```json
{
  "success": true,
  "data": {
    "target_group": "APT28",
    "risk_level": "HIGH",
    "risk_score": 82,
    "rationale": "APT28 活跃时间长，攻击目标集中于政府和军事领域，并持续使用初始访问与凭证窃取技术。",
    "recommendations": [
      "加强鱼叉式钓鱼邮件检测",
      "对相关 ATT&CK 技术建立告警规则",
      "持续关注 APT28 相关 IOC 和新工具"
    ],
    "evidence_ids": ["ev_001", "ev_002"]
  }
}
```

---

## 9. 报告接口

```text
GET  /api/v1/reports/{target_group}
POST /api/v1/reports/{target_group}/generate
```

返回：

```json
{
  "success": true,
  "data": {
    "target_group": "APT28",
    "title": "APT28 威胁情报分析报告",
    "markdown": "...",
    "generated_at": "2026-07-06T22:30:00+08:00"
  }
}
```

增强阶段结构化报告草案：

```json
{
  "success": true,
  "data": {
    "target_group": "APT28",
    "title": "APT28 威胁情报分析报告",
    "markdown": "...",
    "sections": [
      {
        "section_id": "profile",
        "title": "目标画像",
        "section_type": "profile",
        "markdown": "...",
        "evidence_ids": ["ev_001"],
        "analysis_refs": [],
        "graph_refs": {
          "node_ids": ["apt_group:apt28"],
          "edge_ids": []
        }
      },
      {
        "section_id": "behavior_patterns",
        "title": "行为模式",
        "section_type": "behavior_patterns",
        "markdown": "...",
        "evidence_ids": ["ev_001", "ev_002"],
        "analysis_refs": ["behavior_pattern:pattern_apt28_initial_access"],
        "graph_refs": {
          "node_ids": ["apt_group:apt28", "technique:t1566"],
          "edge_ids": ["rel:apt_group:apt28:HAS_BEHAVIOR:behavior:apt28_initial_access"]
        }
      }
    ],
    "generated_at": "2026-07-06T22:30:00+08:00"
  }
}
```

增强阶段章节类型：

```text
profile：目标组织画像
behavior_patterns：行为模式总结
network：关联网络
timeline：时间线
threat_assessment：威胁等级评估
recommendations：预警建议
```

---

## 10. 评测接口

```text
GET  /api/v1/evaluation/summary
POST /api/v1/evaluation/run
```

返回：

```json
{
  "success": true,
  "data": {
    "entity_precision": 0.88,
    "entity_recall": 0.82,
    "entity_f1": 0.85,
    "relation_precision": 0.78
  }
}
```

---

## 11. Neo4j 接口

```text
GET  /api/v1/neo4j/status
POST /api/v1/neo4j/rebuild
POST /api/v1/neo4j/sync
```

说明：

1. `status` 返回连接状态、同步状态、水位、最新变更、待同步数量、首次重建要求及最近时间和稳定错误码。
2. `rebuild` 在同一个 SQLite 读快照中取得 canonical graph 与水位，在一个 Neo4j 写事务中替换本项目投影；先删除带项目 ownership 的关系，再以非 `DETACH` 方式删除 `ThreatGraphProjection` 节点。存在外部关系时整笔事务失败回滚。
3. `sync` 读取 `(watermark, latest_change]` 的变更批次，使用稳定 ID 幂等 upsert/delete；只有 Neo4j 事务成功后才推进 SQLite 水位。首次增量同步前必须先全量重建，返回 HTTP 409。
4. 同步输入只能来自 SQLite canonical graph，不允许从 LLM 原始输出同步到 Neo4j。
5. Pipeline 成功写入 SQLite 后会尽力触发一次增量同步；投影失败不改变 Pipeline 的 SQLite 成功状态。
6. 重建或同步连接失败返回 HTTP 503 和稳定原因码，不返回驱动异常、连接串或凭据。
7. 路径查询接口只遍历本项目节点和带 ownership 的关系；未配置、未重建、同步失败、水位落后或查询失败时降级到 SQLite BFS。

状态响应示例：

```json
{
  "success": true,
  "data": {
    "available": true,
    "connection": "connected",
    "status": "succeeded",
    "watermark": 42,
    "latest_change": 42,
    "pending_changes": 0,
    "requires_rebuild": false,
    "last_attempt_at": "2026-07-16T08:00:00+00:00",
    "last_success_at": "2026-07-16T08:00:00+00:00",
    "last_full_sync_at": "2026-07-16T08:00:00+00:00",
    "error": null
  }
}
```
