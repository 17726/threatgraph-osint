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
  "target_group": "APT28",
  "use_cache": true,
  "steps": ["clean", "extract", "normalize", "build_graph", "analyze_behavior", "infer", "report"]
}
```

说明：

1. 优先级 P0 可以同步执行，直接返回结果。
2. 后续可升级为后台任务。
3. 所有中间结果写入 SQLite。

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
2. `/graph/path` 在优先级 P0 使用 SQLite relations 表做基础 BFS 路径查询。
3. `/graph/path` 在增强阶段 / 优先级 P1 优先使用 Neo4j Cypher 做正式多跳路径查询。
4. Neo4j 不可用时，路径接口降级到 SQLite；如果 SQLite 也查不到路径，再返回清晰错误。

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
POST /api/v1/neo4j/sync
```

说明：

1. 增强阶段 / 优先级 P1 实现。
2. 同步输入只能来自 SQLite canonical graph 或导出的 `graph.json`。
3. 不允许从 LLM 原始输出同步到 Neo4j。
4. 路径查询接口优先使用 Neo4j；失败时降级到 SQLite BFS。
