# ThreatGraph-OSINT 架构设计

> 适用范围：ThreatGraph-OSINT 项目  
> 课程方向：实验三「开源情报资源中潜在行为和关系的大模型深度分析系统」  
> 技术路线：React + TypeScript + Vite + ECharts-for-React + FastAPI + SQLite + graph.json 导出 + Neo4j(增强阶段 / 优先级 P1)
> 版本：当前版
> 日期：2026-07-06

---

## 1. 架构结论

本项目采用 SQLite 作为唯一事实源：

```text
SQLite：唯一事实源，保存文档、切块、抽取结果、实体、关系、证据、报告、评测结果
graph.json：由 SQLite 导出的图谱格式，用于前端 mock、演示兜底、Neo4j 同步输入
Neo4j：增强阶段 / 优先级 P1 的图查询增强层，用于多跳路径查询和 Cypher 展示，但不作为事实源
```

当前架构：

```text
SQLite 事实源 + graph.json 导出 + Neo4j 增强同步 + FastAPI API + React/TypeScript/ECharts 前端
```

核心原则：

1. LLM 原始输出不是事实源。
2. SQLite 是唯一事实源。
3. graph.json 是导出格式和前端 mock，不是事实源。
4. Neo4j 是增强能力，但不是事实源。
5. 前端只依赖 FastAPI 接口，不感知底层是 SQLite、graph.json 还是 Neo4j。
6. 现场演示必须可缓存、可复现，不能强依赖实时爬虫或实时 LLM。

### 1.1 参考项目后的架构调整

参考 OpenCTI、MISP、SpiderFoot、GraphRAG 和 TypeDB CTI 后，当前架构只吸收轻量且必要的设计，不引入重型平台：

1. **证据链前置**：实体、关系、行为分析和报告结论都必须能追溯到 `evidence_ids`。证据记录要保留来源、发布时间、抓取时间、证据类型和原文位置。
2. **文档容器化**：`documents` 不只是 `raw_text`，还要保存 `source_name`、`source_type`、`published_at`、`retrieved_at`、`source_reliability`、`tags_json` 和 `content_hash`。
3. **采集层隔离**：`sources -> collection_runs -> collected_items -> documents` 分层。采集失败、重复、解析失败只影响采集层，不能直接污染正式图谱。
4. **候选层隔离**：LLM 输出只能进入 `extracted_entities`、`extracted_relations`，并带 `candidate_status`、`validation_status`、`validation_errors_json`。后端归一化后才写入 `entities`、`relations`、`evidence`。
5. **schema-first**：`document.json`、`extraction_result.json`、`graph.json` 都必须带 `schema_version`。实体类型、关系类型和合法关系矩阵由架构维护，不能由 LLM 临时发明。
6. **图数据库增强而非真源**：Neo4j 继续作为 P1 增强层，只从 SQLite canonical graph 或 `graph.json` 同步。

这几项属于开工前需要确定的架构边界。暂不吸收的内容包括完整 STIX 2.1、OpenCTI/MISP 式平台权限模型、TypeDB 主库、GraphRAG 完整社区发现和大规模自动采集调度。

阶段和优先级分开管理：

```text
阶段：表示开发先后顺序，见 docs/stage-roadmap.md
P0/P1/P2：表示优先级，不表示必须按顺序串行开发
```

---

## 2. 系统目标

系统面向 APT 组织开源情报分析，完成课程要求中的完整链路：

```text
多源数据采集
  -> 文本清洗与标准化
  -> LLM 实体识别
  -> LLM 关系抽取
  -> 知识图谱构建
  -> 行为模式分析与 MITRE ATT&CK 映射
  -> 智能推理与候选关联发现
  -> 图谱查询与可视化
  -> 智能报告生成
  -> 测试评估
```

MVP 范围固定为 3 个目标组织：

```text
APT28
Lazarus
Kimsuky
```

数据源至少覆盖三类：

```text
安全报告 / 安全博客 / CERT 公告
新闻媒体 / 政府公告
社交媒体 / 论坛 / Telegram 频道整理文本
```

---

## 3. 总体架构

```text
┌──────────────────────────────────────────────┐
│          React + TypeScript + Vite 前端        │
│  搜索 / 图谱 / 详情 / 时间线 / 报告 / 评测       │
│  ECharts-for-React 负责关系图可视化             │
└──────────────────────┬───────────────────────┘
                       │ HTTP JSON
┌──────────────────────▼───────────────────────┐
│                 FastAPI 后端                  │
│  sources / collection / documents / pipeline   │
│  graph / entities                              │
│  analysis / reports / evaluation / neo4j-sync  │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│               业务服务与流水线                  │
│  采集 / 清洗 / 抽取 / 归一化 / 建图 / 行为分析 / 推理 / 报告 │
└───────────────┬──────────────────┬───────────┘
                │                  │
┌───────────────▼──────────────┐   │
│          SQLite 事实源         │   │
│ documents / chunks / entities │   │
│ relations / evidence / analysis│  │
│ reports / evaluation           │  │
└───────────────┬──────────────┘   │
                │ 导出 graph.json   │
┌───────────────▼──────────────┐   │
│          graph.json           │   │
│ 前端 mock / 演示兜底 / 同步输入 │   │
└───────────────┬──────────────┘   │
                │ 增强同步           │
┌───────────────▼──────────────┐   │
│             Neo4j             │◀──┘
│ 多跳路径查询 / 图谱增强 / Cypher │
└──────────────────────────────┘
```

---

## 4. 推荐数据流

权威数据流：

```text
sources 配置 / data/raw/*.json
  -> collection runs
  -> SQLite collected_items
  -> SQLite documents/chunks
  -> LLM 抽取结果写入 SQLite extraction tables
  -> 归一化实体和关系写入 SQLite canonical graph tables
  -> 行为分析和推理结果写入 SQLite analysis tables
  -> 导出 data/graph/graph.json
  -> FastAPI
  -> React + TypeScript + ECharts
```

增强数据流：

```text
SQLite canonical graph 或 data/graph/graph.json
  -> Neo4j sync
  -> Neo4j
  -> FastAPI path/query API
  -> React + TypeScript + ECharts
```

禁止的数据流：

```text
LLM 原始输出 -> 直接写 Neo4j -> 前端展示
```

原因：

1. LLM 输出可能包含重复实体、漂移 ID、非法 JSON、错误关系。
2. 未归一化数据直接入图会污染图数据库。
3. 后续评测、证据追溯、报告复现会困难。
4. Neo4j 应从已校验的 canonical graph 同步，不能承担清洗和纠错职责。

### 4.1 输入与采集边界

课程要求覆盖“至少三类来源自动采集”和“新情报自动融入图谱”，但第一阶段不应被爬虫平台阻塞。本项目采用阶段化输入策略：

```text
阶段 1：离线文本入口
  假设已经拿到本地文本文件
  数据组手动清洗为 document.json
  LLM 组和后端组基于固定 JSON 契约并行开发

阶段 2：本地文档导入和集成 MVP
  支持 document.json 或本地文本导入
  写入 SQLite documents/chunks
  后续进入抽取、归一化、建图和报告流水线

阶段 3：最小自动采集闭环
  配置 sources
  手动触发 collection run
  从三类来源采集少量样本文档或 feed 条目
  写入 collected_items
  转入 documents
  后续进入清洗、抽取、建图流水线

阶段 4：复杂采集调度与增量更新
  定时调度
  增量 checkpoint
  去重与版本比较
  新情报自动触发图谱更新
  采集错误重试和运行统计
```

第一阶段的关键不是采集平台，而是固定 `document.json`、`extraction_result.json`、`graph.json` 契约。爬虫、RSS、复杂调度和增量更新不能阻塞离线闭环。

---

## 5. 数据分层

SQLite 是唯一事实源。下面的 JSON 文件是导入、导出、缓存或演示材料，不作为长期权威存储。

### 5.1 raw documents

位置：

```text
data/raw/
```

用途：保存爬虫或人工整理的原始情报文本。

示例：

```json
{
  "doc_id": "apt28_mitre_001",
  "schema_version": "1.0",
  "target_group": "APT28",
  "target_groups": ["APT28"],
  "source_url": "https://attack.mitre.org/groups/G0007/",
  "source_type": "security_report",
  "source_name": "MITRE ATT&CK",
  "title": "APT28 - MITRE ATT&CK",
  "language": "en",
  "raw_text": "...",
  "content_hash": "sha256:...",
  "published_at": null,
  "retrieved_at": "2026-07-07T00:00:00+08:00",
  "source_reliability": "A",
  "tlp": "TLP:CLEAR",
  "tags": ["mitre", "apt", "security_report"],
  "metadata": {
    "publisher": "MITRE",
    "collector": "数据组"
  }
}
```

### 5.2 cleaned docs

位置：

```text
data/cleaned/cleaned_docs.json
```

用途：保存清洗、去重、切块后的标准输入。

```json
{
  "doc_id": "apt28_mitre_001",
  "schema_version": "1.0",
  "target_group": "APT28",
  "target_groups": ["APT28"],
  "source_type": "security_report",
  "source_name": "MITRE ATT&CK",
  "title": "APT28 - MITRE ATT&CK",
  "language": "en",
  "clean_text": "...",
  "chunks": [
    {
      "chunk_id": "apt28_mitre_001_c001",
      "chunk_index": 0,
      "section_title": "Techniques Used",
      "text": "...",
      "char_start": 0,
      "char_end": 1200,
      "text_hash": "sha256:..."
    }
  ]
}
```

### 5.3 extraction results

位置：

```text
data/extracted/extraction_results.json
```

用途：保存 LLM 抽取出的候选实体、候选关系、证据片段。

注意：这一层仍然不是最终事实源，需要经过后端归一化。

```json
{
  "schema_version": "1.0",
  "run_id": "extract_apt28_mitre_001_001",
  "doc_id": "apt28_mitre_001",
  "chunk_id": "apt28_mitre_001_c001",
  "entities": [
    {
      "name": "APT28",
      "type": "APT_GROUP",
      "aliases": ["Fancy Bear", "Sofacy"],
      "description": "与俄罗斯 GRU 有关联的 APT 组织",
      "mention_text": "APT28",
      "evidence": "APT28 is a threat group...",
      "char_start": 0,
      "char_end": 27,
      "confidence": 0.96,
      "candidate_status": "candidate",
      "validation_status": "unchecked"
    }
  ],
  "relations": [
    {
      "head": "APT28",
      "head_type": "APT_GROUP",
      "relation": "USES",
      "tail": "X-Agent",
      "tail_type": "MALWARE",
      "evidence": "APT28 utilizes malware such as X-Agent...",
      "char_start": 120,
      "char_end": 170,
      "confidence": 0.91,
      "candidate_status": "candidate",
      "validation_status": "unchecked"
    }
  ]
}
```

### 5.4 canonical graph

位置：

```text
data/graph/graph.json
```

用途：保存从 SQLite 导出的标准图谱快照，用于前端 mock、演示兜底、Neo4j 同步输入。

注意：`graph.json` 不是事实源。事实源是 SQLite 中的实体、关系、证据和文档表。

```json
{
  "version": "2.0",
  "schema_version": "1.0",
  "generated_at": "2026-07-06T21:30:00+08:00",
  "exported_from": "sqlite",
  "source_of_truth": "data/threatgraph_osint.db",
  "nodes": [
    {
      "id": "apt_group:apt28",
      "name": "APT28",
      "type": "APT_GROUP",
      "aliases": ["Fancy Bear", "Sofacy", "Sednit"],
      "description": "与俄罗斯 GRU 有关联的 APT 组织",
      "confidence": 0.96,
      "source_count": 3,
      "first_seen": "2014-01-01",
      "last_seen": "2026-07-01",
      "tags": ["apt", "mitre"],
      "evidence_ids": ["ev_apt28_001"]
    }
  ],
  "edges": [
    {
      "id": "edge_apt28_uses_xagent",
      "source": "apt_group:apt28",
      "target": "malware:x-agent",
      "type": "USES",
      "label": "使用",
      "confidence": 0.91,
      "source_count": 2,
      "evidence_count": 1,
      "validation_status": "valid",
      "evidence_ids": ["ev_apt28_002"]
    }
  ],
  "evidence": [
    {
      "id": "ev_apt28_001",
      "doc_id": "apt28_mitre_001",
      "chunk_id": "apt28_mitre_001_c001",
      "source_url": "https://attack.mitre.org/groups/G0007/",
      "source_type": "security_report",
      "source_name": "MITRE ATT&CK",
      "text": "APT28 is a threat group...",
      "evidence_type": "direct_quote",
      "quote_start": 0,
      "quote_end": 27,
      "published_at": null,
      "retrieved_at": "2026-07-07T00:00:00+08:00",
      "source_reliability": "A",
      "language": "en"
    }
  ]
}
```

### 5.5 SQLite 表设计

SQLite 是唯一事实源。建议表设计如下：

```text
documents
  doc_id
  target_group
  source_url
  source_type
  title
  language
  raw_text
  metadata_json
  created_at

chunks
  chunk_id
  doc_id
  text
  char_start
  char_end
  token_count

extraction_runs
  run_id
  doc_id
  model_name
  prompt_version
  status
  started_at
  finished_at
  error_message

extracted_entities
  extracted_entity_id
  run_id
  chunk_id
  name
  type
  aliases_json
  description
  evidence_text
  confidence

extracted_relations
  extracted_relation_id
  run_id
  chunk_id
  head_name
  head_type
  relation_type
  tail_name
  tail_type
  evidence_text
  confidence

entities
  entity_id
  name
  type
  aliases_json
  description
  confidence
  source_count
  created_at
  updated_at

relations
  relation_id
  source_entity_id
  target_entity_id
  relation_type
  label
  confidence
  created_at
  updated_at

evidence
  evidence_id
  doc_id
  chunk_id
  entity_id
  relation_id
  evidence_text
  source_url
  language

reports
  report_id
  target_group
  title
  markdown
  generated_at
  graph_version

evaluation_runs
  eval_run_id
  run_id
  precision
  recall
  f1
  relation_precision
  notes
  created_at

sources
  source_id
  name
  source_type
  collector_type
  url
  target_groups_json
  enabled
  config_json
  created_at
  updated_at

collection_runs
  collection_run_id
  source_id
  status
  started_at
  finished_at
  items_found
  items_imported
  error_message

collected_items
  item_id
  collection_run_id
  source_id
  target_group
  source_url
  title
  raw_text
  content_hash
  status
  created_at

report_sections
  section_id
  report_id
  section_type
  title
  markdown
  evidence_ids_json
  analysis_refs_json
  graph_refs_json
```

设计原则：

1. `extracted_*` 表保存 LLM 候选输出。
2. `entities` 和 `relations` 表保存归一化后的 canonical graph。
3. `evidence` 表连接文档、切块、实体、关系，是报告可追溯性的关键。
4. `graph.json` 由 `entities`、`relations`、`evidence` 导出。
5. Neo4j 只从 `entities`、`relations`、`evidence` 或导出的 `graph.json` 同步。

### 5.6 行为分析与推理数据

行为分析不是舆情分析，而是威胁行为分析。它基于 canonical graph 回答：

```text
APT 组织怎么攻击？
用了哪些攻击技术？
处于哪些攻击阶段？
偏好攻击哪些目标？
能否根据证据推断候选关联？
```

核心数据：

```text
mitre_mappings：MITRE ATT&CK 映射
behavior_patterns：攻击行为模式
inferred_relations：推断关系
threat_assessments：威胁评估
```

字段含义：

```text
attack_stage：攻击阶段，如侦察、初始访问、执行、持久化、C2、目标达成
mitre_mapping：MITRE ATT&CK 映射，把技术实体或关系映射到 T 编号和战术阶段
behavior_pattern：行为模式，如“APT28 偏好鱼叉式钓鱼投递恶意附件”
inferred_relation：推断关系，不是原文直接说的事实，而是基于证据推断出的候选关系
rationale：推理理由
confidence：置信度
status：推断状态，candidate 候选、accepted 接受、rejected 拒绝
```

约束：

1. 行为分析必须基于 SQLite canonical graph 和 evidence。
2. 智能推理只能生成候选关系，不能覆盖原始抽取事实。
3. 每条推断必须保留 `rationale`、`confidence` 和 `evidence_ids`。
4. 报告中必须区分“原文证据事实”和“系统推断结论”。

---

## 6. 实体与关系设计

### 6.1 实体类型

```text
APT_GROUP
ORGANIZATION
PERSON
MALWARE
TOOL
CVE
TECHNIQUE
TARGET
COUNTRY
REGION
INDUSTRY
TIME
EVENT
CAMPAIGN
BEHAVIOR_PATTERN
```

说明：

1. `TARGET` 用于课程要求里的攻击目标。
2. `INDUSTRY` 用于行业目标，如金融、政府、能源。
3. `EVENT` 用于关键攻击事件。
4. `CAMPAIGN` 用于攻击活动。
5. `BEHAVIOR_PATTERN` 用于把行为分析结果纳入图谱展示。

### 6.2 关系类型

```text
USES
TARGETS
EXPLOITS
ATTRIBUTED_TO
AFFILIATED_WITH
LOCATED_IN
HAPPENED_AT
PART_OF
LEADS_TO
RELATED_TO
DISCOVERED_BY
CAUSES
HAS_BEHAVIOR
```

说明：

1. 关系类型控制在 10-13 个，避免 LLM 输出过散。
2. `RELATED_TO` 只作为兜底关系，不能滥用。
3. 时间、因果、攻击链关系必须保留证据。
4. `HAS_BEHAVIOR` 用于连接 APT 组织和行为模式节点。

---

## 7. ID 设计

不要让 LLM 决定最终实体 ID。

LLM 只输出：

```text
name
type
aliases
description
evidence
confidence
```

后端归一化服务生成稳定 ID：

```text
apt_group:apt28
apt_group:lazarus
apt_group:kimsuky
malware:x-agent
technique:t1566.001
cve:cve-2021-44228
country:ukraine
industry:finance
```

规则：

1. 小写。
2. 空格转短横线。
3. CVE 保留原编号。
4. MITRE ATT&CK 技术保留 T 编号。
5. 别名合并到同一标准实体。

---

## 8. FastAPI 接口设计

前端只依赖 API，不直接读取本地文件。

### 8.1 系统接口

```text
GET /api/v1/health
```

### 8.2 采集接口

```text
GET  /api/v1/sources
POST /api/v1/sources
POST /api/v1/collection-runs
GET  /api/v1/collection-runs/{collection_run_id}
```

第一阶段可以先使用本地文本或 `document.json` 导入。课程验收增强阶段再手动触发最小采集任务，采集结果写入 SQLite；后续增强再实现定时调度、增量 checkpoint 和新情报自动入图。

### 8.3 文档接口

```text
GET /api/v1/documents
GET /api/v1/documents/{doc_id}
```

### 8.4 流水线接口

```text
POST /api/v1/pipeline/run
GET  /api/v1/pipeline/status/{job_id}
```

`POST /pipeline/run` 支持：

```json
{
  "target_group": "APT28",
  "use_cache": true,
  "steps": ["clean", "extract", "normalize", "build_graph", "analyze_behavior", "infer", "report"]
}
```

### 8.5 图谱接口

```text
GET /api/v1/graph?target=APT28&depth=2
GET /api/v1/graph/path?source=apt_group:apt28&target=malware:x-agent
GET /api/v1/graph/timeline?target=APT28
```

路径追踪实现策略：

```text
优先级 P0：SQLite relations 表做基础 BFS 路径查询，保证接口可用
优先级 P1：Neo4j Cypher 做正式多跳路径查询，用于演示高阶图数据库能力
```

说明：

1. 路径追踪接口不能只在 Neo4j 可用时才存在。
2. Neo4j 是增强能力，但 SQLite 需要提供演示兜底。
3. 前端只调用 `/graph/path`，不感知底层使用 SQLite BFS 还是 Neo4j Cypher。

图谱响应：

```json
{
  "success": true,
  "data": {
    "nodes": [],
    "edges": [],
    "evidence": []
  }
}
```

### 8.6 实体接口

```text
GET /api/v1/entities/search?q=APT28
GET /api/v1/entities/{entity_id}
```

### 8.7 报告接口

```text
GET /api/v1/reports/{target_group}
POST /api/v1/reports/{target_group}/generate
```

优先级 P0 返回基础 `markdown` 报告。增强阶段扩展结构化 `sections`、`evidence_ids`、`analysis_refs` 和 `graph_refs`，方便前端展示课程要求中的画像、行为模式、关联网络、时间线、威胁等级和预警建议。

### 8.8 行为分析与推理接口

```text
POST /api/v1/analysis/{target_group}/run
GET  /api/v1/analysis/{target_group}/behavior
GET  /api/v1/analysis/{target_group}/mitre
GET  /api/v1/analysis/{target_group}/inferences
GET  /api/v1/analysis/{target_group}/threat-assessment
```

说明：

1. `behavior` 返回攻击阶段和行为模式。
2. `mitre` 返回 MITRE ATT&CK 技术映射。
3. `inferences` 返回候选推断关系。
4. `threat-assessment` 返回威胁等级、风险分数和防护建议。

### 8.9 评测接口

```text
GET /api/v1/evaluation/summary
POST /api/v1/evaluation/run
```

### 8.10 Neo4j 同步接口

```text
POST /api/v1/neo4j/sync
GET  /api/v1/neo4j/status
```

说明：

1. Neo4j 同步接口只读取 canonical graph。
2. 不允许 LLM 结果直接写入 Neo4j。
3. 增强阶段 / 优先级 P1 实现 Neo4j 同步和路径查询。
4. 如果 Neo4j 不可用，基础图谱展示和报告生成仍然通过 SQLite 工作。

---

## 9. 项目目录

```text
threatgraph-osint/
  README.md
  pyproject.toml
  package.json
  docker-compose.yml
  .env.example
  .gitignore

  docs/
    architecture.md
    api-contract.md
    data-contract.md
    reference-comparison.md
    report-template.md
    team-workflow.md

  backend/
    Dockerfile
    app/
      main.py
      core/
        config.py
        response.py
        schemas.py
      api/
        documents.py
        collection.py
        pipeline.py
        graph.py
        entities.py
        analysis.py
        reports.py
        evaluation.py
        neo4j_sync.py
      services/
        collection_service.py
        document_service.py
        cleaning_service.py
        extraction_service.py
        normalization_service.py
        behavior_analysis_service.py
        inference_service.py
        graph_store.py
        report_service.py
        evaluation_service.py
        neo4j_sync_service.py
      pipeline/
        run_pipeline.py
    tests/

  frontend/
    Dockerfile
    src/
      api/
        client.ts
        graph.ts
        entities.ts
        analysis.ts
        reports.ts
      types/
        graph.ts
        entity.ts
        analysis.ts
        report.ts
      components/
        GraphChart.tsx
        SearchPanel.tsx
        DetailPanel.tsx
        TimelinePanel.tsx
        BehaviorPanel.tsx
        MitrePanel.tsx
        ReportPanel.tsx
      pages/
        Dashboard.tsx
        GraphExplorer.tsx
        Analysis.tsx
        Reports.tsx
        Evaluation.tsx
      App.tsx
      main.tsx

  data/
    sources/
    raw/
    cleaned/
    extracted/
    graph/
    reports/
    evaluation/

  scripts/
    collect_sources.py
    seed_demo_data.py
    run_pipeline.py
    export_graph_json.py
    sync_neo4j.py
```

---

## 10. Docker 环境策略

本项目采用 Docker Compose 作为标准开发和演示环境。

服务命名：

```text
backend：FastAPI 后端
frontend：React + TypeScript + Vite 前端
neo4j：增强阶段 / 优先级 P1 图数据库
```

SQLite 不单独作为服务运行，而是一个挂载文件：

```text
data/threatgraph_osint.db
```

推荐管理命令：

```bash
# 构建并启动全部服务
docker compose up --build

# 后台启动全部服务
docker compose up -d

# 只启动后端
docker compose up backend

# 只启动前端
docker compose up frontend

# 只启动 Neo4j
docker compose up neo4j

# 查看全部服务状态
docker compose ps

# 查看后端日志
docker compose logs -f backend

# 查看前端日志
docker compose logs -f frontend

# 查看 Neo4j 日志
docker compose logs -f neo4j

# 进入后端容器执行命令
docker compose exec backend bash

# 执行流水线脚本
docker compose exec backend python scripts/run_pipeline.py --target APT28

# 导出 graph.json
docker compose exec backend python scripts/export_graph_json.py

# 同步 Neo4j
docker compose exec backend python scripts/sync_neo4j.py

# 停止服务
docker compose down
```

默认访问地址：

```text
前端：http://localhost:5173
后端：http://localhost:8000
后端 API 文档：http://localhost:8000/docs
Neo4j Browser：http://localhost:7474
```

环境原则：

1. Docker Compose 是推荐运行方式。
2. 后端仍保留本地 `uv` 运行能力。
3. 前端仍保留本地 `pnpm` 运行能力。
4. Neo4j 优先通过 Docker Compose 管理，不要求组员本机安装。
5. `.env` 统一管理 LLM API、Neo4j 密码、SQLite 路径等配置。
6. 基础阶段可以不启动 Neo4j；增强阶段必须能通过 Docker Compose 启动 Neo4j 并完成同步。

---

## 11. 前端职责

前端组负责：

1. 调用 FastAPI。
2. 展示图谱、详情、搜索、时间线、报告。
3. 使用 ECharts-for-React 绘制关系图。
4. 使用 TypeScript 定义 API 响应、图节点、图边、报告结构类型。
5. 不处理实体归一化。
6. 不直接读取 LLM 原始输出。
7. 不直接访问 Neo4j。

前端核心页面：

```text
Dashboard：总览
GraphExplorer：知识图谱
EntityDetail：实体详情
Report：报告展示
Evaluation：评测结果
```

---

## 12. 后端职责

后端负责：

1. 管理文档数据。
2. 调用 LLM。
3. 校验 LLM JSON 输出。
4. 实体归一化和去重。
5. 构建 canonical graph。
6. 基于图谱进行行为分析和 MITRE ATT&CK 映射。
7. 基于证据生成候选推断关系。
8. 提供统一 API。
9. 生成报告。
10. 评估实体和关系抽取质量。
11. 在增强阶段同步 Neo4j 并提供 Cypher 路径查询能力。

---

## 13. Neo4j 职责

Neo4j 只负责：

1. 多跳路径查询。
2. 复杂图查询。
3. 图谱增强展示。
4. 多维度查询演示，如按组织、时间、地区、攻击类型组合查询。
5. 答辩时展示专业图数据库能力。

Neo4j 不负责：

1. 保存唯一事实源。
2. 接收未经归一化的 LLM 输出。
3. 承担报告复现的唯一依据。
4. 阻塞主流程运行。

---

## 14. 阶段与 MVP 验收标准

### 14.1 Demo 标准

Demo 用来证明核心概念能跑，可以有手动步骤和 mock 数据。最低标准：

1. 至少 1 个目标组织样本。
2. 本地文本或 `document.json` 可作为输入。
3. 能产出 `extraction_result.json` 或等价 mock。
4. 能产出 `graph.json`。
5. 前端能基于 `graph.json` 展示图谱、实体详情和证据。
6. 能生成基础报告片段。

### 14.2 MVP 标准

MVP 用来证明团队可以交付和继续开发，必须满足：

1. 至少 1 个目标组织端到端跑通。
2. SQLite 作为唯一事实源。
3. 能从 SQLite 导出 `data/graph/graph.json`。
4. 能本地导入文档，不依赖爬虫平台。
5. 能展示实体和关系图谱。
6. 能按组织查询。
7. 能通过 SQLite BFS 提供基础路径追踪。
8. 能展示实体详情和证据片段。
9. 能完成基础 MITRE 映射或行为模式分析。
10. 能生成基础报告。
11. 其他组员能按文档复现。
12. 没有 Neo4j 时系统仍能运行。

### 14.3 课程验收增强标准

课程最终演示建议满足：

1. 至少 3 个目标组织：APT28、Lazarus、Kimsuky。
2. 至少 3 类数据源：安全类、新闻类、社媒/论坛类。
3. 能通过最小采集入口从三类来源导入样本文档。
4. 能完成 MITRE 映射和行为模式分析。
5. 能展示简单评测结果。
6. 能将 SQLite canonical graph 同步到 Neo4j。
7. 能查询 Neo4j 连接状态和同步状态。
8. 能通过 Neo4j Cypher 查询多跳关联路径。
9. Neo4j 同步失败不能污染 SQLite 事实源。
10. 报告接口返回结构化 sections，并能追溯 evidence、analysis 和 graph 引用。

---

## 15. 后续待定问题

后续开发前建议继续确认：

1. 后端包管理用 `uv`、`pip` 还是 Poetry。
2. LLM 使用 OpenAI、DeepSeek、通义，还是统一 OpenAI-compatible API。
3. 评测集 `golden.json` 是否由数据组维护为唯一人工标注基准。
4. 是否使用单根目录统一启动脚本。

---

## 16. 当前决策

已确认：

1. 前端使用 React + TypeScript + Vite + ECharts-for-React。
2. 后端使用 FastAPI。
3. SQLite 作为唯一事实源。
4. `graph.json` 作为导出格式和前端 mock。
5. Neo4j 作为增强阶段 / 优先级 P1 的图查询增强，不作为事实源。
6. Docker Compose 作为标准开发和演示环境。
7. 服务通过 `docker compose` 命令直接管理。
8. 第一阶段先使用本地文本文件或 `document.json` 跑通离线链路。
9. 自动采集不阻塞第一阶段；三类来源最小采集放到课程验收增强阶段。
10. 基础报告可先返回 markdown，结构化报告接口放到增强阶段。
11. 后续开发以本架构和 `docs/stage-roadmap.md` 为准。
