# 数据契约

> 适用范围：ThreatGraph-OSINT 项目  
> 唯一事实源：SQLite  
> 导出格式：`data/graph/graph.json`  
> 图查询增强：Neo4j，增强阶段 / 优先级 P1

---

## 1. 数据栈结论

```text
SQLite：唯一事实源
graph.json：导出格式、前端 mock、演示兜底、Neo4j 同步输入
Neo4j：增强阶段 / 优先级 P1 图查询增强，不保存唯一事实
```

禁止链路：

```text
LLM 原始输出 -> Neo4j -> 前端
```

允许链路：

```text
sources / raw docs -> SQLite collected_items
collected_items -> SQLite documents/chunks
LLM 输出 -> SQLite extracted_* 候选表
归一化 -> SQLite entities/relations/evidence
导出 -> graph.json
同步 -> Neo4j
```

---

## 2. SQLite 文件

默认路径：

```text
data/threatgraph_osint.db
```

容器内路径：

```text
/app/data/threatgraph_osint.db
```

---

## 3. 表设计

### 3.1 sources

保存可采集来源配置。第一阶段可先使用本地文本或 `document.json` 导入；课程验收增强阶段用于手动触发三类来源最小采集；后续增强用于调度和增量更新。

字段含义：

```text
source_type：来源类型，如 security_report、news、government_notice、social_forum
collector_type：采集器类型，如 local_json、http_page、rss_feed
target_groups_json：该来源默认覆盖的目标组织
config_json：采集器配置，如语言、默认目标组织、解析规则
```

```sql
CREATE TABLE sources (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  collector_type TEXT NOT NULL,
  url TEXT NOT NULL,
  target_groups_json TEXT NOT NULL DEFAULT '[]',
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 3.2 collection_runs

保存每次采集运行记录。

```sql
CREATE TABLE collection_runs (
  collection_run_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  target_groups_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  items_found INTEGER NOT NULL DEFAULT 0,
  items_imported INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  FOREIGN KEY (source_id) REFERENCES sources(source_id)
);
```

### 3.3 collected_items

保存采集到的原始条目。这里还不是最终文档事实，需要转入 `documents` 后再进入清洗和抽取。

```sql
CREATE TABLE collected_items (
  item_id TEXT PRIMARY KEY,
  collection_run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_group TEXT NOT NULL,
  source_url TEXT NOT NULL,
  title TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
  raw_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('collected', 'imported', 'skipped', 'failed')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (collection_run_id) REFERENCES collection_runs(collection_run_id),
  FOREIGN KEY (source_id) REFERENCES sources(source_id)
);
```

### 3.4 documents

保存原始文档。

```sql
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  collection_item_id TEXT,
  target_group TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  title TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
  raw_text TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY (collection_item_id) REFERENCES collected_items(item_id)
);
```

### 3.5 chunks

保存清洗和切块后的 LLM 输入。

```sql
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  text TEXT NOT NULL,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  token_count INTEGER,
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);
```

### 3.6 extraction_runs

保存每次 LLM 抽取任务。

```sql
CREATE TABLE extraction_runs (
  run_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  model_name TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  error_message TEXT,
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);
```

### 3.7 extracted_entities

保存 LLM 候选实体。这里不是最终事实。

```sql
CREATE TABLE extracted_entities (
  extracted_entity_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  description TEXT NOT NULL DEFAULT '',
  evidence_text TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);
```

### 3.8 extracted_relations

保存 LLM 候选关系。这里不是最终事实。

```sql
CREATE TABLE extracted_relations (
  extracted_relation_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  head_name TEXT NOT NULL,
  head_type TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  tail_name TEXT NOT NULL,
  tail_type TEXT NOT NULL,
  evidence_text TEXT NOT NULL,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
);
```

### 3.9 entities

保存归一化后的实体，属于 canonical graph。

```sql
CREATE TABLE entities (
  entity_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  description TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  source_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 3.10 relations

保存归一化后的关系，属于 canonical graph。

```sql
CREATE TABLE relations (
  relation_id TEXT PRIMARY KEY,
  source_entity_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  label TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id),
  FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id)
);
```

### 3.11 evidence

保存证据。报告、详情页、评测都依赖这一层。

```sql
CREATE TABLE evidence (
  evidence_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  chunk_id TEXT,
  entity_id TEXT,
  relation_id TEXT,
  evidence_text TEXT NOT NULL,
  source_url TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
  FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
  FOREIGN KEY (relation_id) REFERENCES relations(relation_id)
);
```

### 3.12 reports

保存报告缓存。优先级 P0 可以只写 `markdown`；增强阶段增加 `report_sections` 作为结构化报告。

```sql
CREATE TABLE reports (
  report_id TEXT PRIMARY KEY,
  target_group TEXT NOT NULL,
  title TEXT NOT NULL,
  markdown TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  graph_version TEXT NOT NULL
);
```

### 3.13 report_sections

保存增强阶段结构化报告章节，便于前端展示课程要求中的画像、行为模式、关联网络、时间线、威胁等级和预警建议。

字段含义：

```text
section_type：profile、behavior_patterns、network、timeline、threat_assessment、recommendations
evidence_ids_json：支撑该章节的证据
analysis_refs_json：引用的行为分析、MITRE 映射、推理或威胁评估结果
graph_refs_json：引用的图谱节点和关系
```

```sql
CREATE TABLE report_sections (
  section_id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  section_type TEXT NOT NULL,
  title TEXT NOT NULL,
  markdown TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  analysis_refs_json TEXT NOT NULL DEFAULT '[]',
  graph_refs_json TEXT NOT NULL DEFAULT '{}',
  sort_order INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (report_id) REFERENCES reports(report_id)
);
```

### 3.14 mitre_mappings

保存 MITRE ATT&CK 映射。

字段含义：

```text
technique_id：MITRE 技术编号，如 T1566
tactic：MITRE 战术，如 Initial Access
attack_stage：攻击阶段，中文展示用，如 初始访问
entity_id：映射到的技术实体，可为空
relation_id：映射到的图谱关系，可为空
source：映射来源，rule 规则、llm 大模型、manual 人工
```

```sql
CREATE TABLE mitre_mappings (
  mapping_id TEXT PRIMARY KEY,
  target_group TEXT NOT NULL,
  technique_id TEXT NOT NULL,
  technique_name TEXT NOT NULL,
  tactic TEXT NOT NULL,
  attack_stage TEXT NOT NULL,
  entity_id TEXT,
  relation_id TEXT,
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  source TEXT NOT NULL CHECK (source IN ('rule', 'llm', 'manual')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
  FOREIGN KEY (relation_id) REFERENCES relations(relation_id)
);
```

### 3.15 behavior_patterns

保存攻击行为模式。

字段含义：

```text
stage：攻击阶段
description：行为描述
technique_ids_json：相关 MITRE 技术编号
relation_ids_json：支撑该行为模式的图谱关系
evidence_ids_json：支撑证据
```

```sql
CREATE TABLE behavior_patterns (
  pattern_id TEXT PRIMARY KEY,
  target_group TEXT NOT NULL,
  stage TEXT NOT NULL,
  description TEXT NOT NULL,
  technique_ids_json TEXT NOT NULL DEFAULT '[]',
  relation_ids_json TEXT NOT NULL DEFAULT '[]',
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  created_at TEXT NOT NULL
);
```

### 3.16 inferred_relations

保存智能推理得到的候选关系。

字段含义：

```text
source_entity_id：主体实体
target_entity_id：客体实体
relation_type：候选关系类型
rationale：推理理由
support_evidence_ids_json：支撑证据
status：candidate 候选、accepted 接受、rejected 拒绝
```

```sql
CREATE TABLE inferred_relations (
  inferred_relation_id TEXT PRIMARY KEY,
  source_entity_id TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  rationale TEXT NOT NULL,
  support_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  status TEXT NOT NULL CHECK (status IN ('candidate', 'accepted', 'rejected')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id),
  FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id)
);
```

### 3.17 threat_assessments

保存威胁评估和防护建议。

字段含义：

```text
risk_level：威胁等级，CRITICAL/HIGH/MEDIUM/LOW
risk_score：风险分数，0-100
rationale：评估理由
recommendations_json：预警和防护建议
```

```sql
CREATE TABLE threat_assessments (
  assessment_id TEXT PRIMARY KEY,
  target_group TEXT NOT NULL,
  risk_level TEXT NOT NULL CHECK (risk_level IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
  risk_score INTEGER NOT NULL CHECK (risk_score >= 0 AND risk_score <= 100),
  rationale TEXT NOT NULL,
  recommendations_json TEXT NOT NULL DEFAULT '[]',
  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
```

### 3.18 evaluation_runs

保存评测结果。

```sql
CREATE TABLE evaluation_runs (
  eval_run_id TEXT PRIMARY KEY,
  run_id TEXT,
  precision REAL,
  recall REAL,
  f1 REAL,
  relation_precision REAL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id)
);
```

---

## 4. 行为分析与推理约束

行为分析和推理必须基于已归一化的图谱事实。

允许输入：

```text
entities：实体
relations：关系
evidence：证据
mitre_mappings：已有 MITRE 映射
```

输出：

```text
mitre_mappings：MITRE 映射
behavior_patterns：行为模式
inferred_relations：候选推断关系
threat_assessments：威胁评估
```

约束：

1. `inferred_relations` 不能直接写入 `relations`。
2. 只有人工确认或规则确认后，推断关系才能转为正式 `relations`。
3. 报告中必须区分“证据事实”和“系统推断”。
4. 每个行为模式和推断关系都必须能追溯到证据。

---

## 5. ID 规则

实体 ID：

```text
apt_group:apt28
malware:x-agent
tool:cobalt-strike
cve:cve-2021-44228
technique:t1566.001
country:ukraine
industry:finance
event:apt28-ukraine-2025
```

关系 ID：

```text
rel:{source_entity_id}:{relation_type}:{target_entity_id}
```

示例：

```text
rel:apt_group:apt28:USES:malware:x-agent
```

证据 ID：

```text
ev_{doc_id}_{hash}
```

规则：

1. LLM 不生成最终 ID。
2. 后端归一化服务负责生成 ID。
3. 别名归并到同一实体。
4. CVE、MITRE ATT&CK 编号保留原始编号。

---

## 6. graph.json 契约

路径：

```text
data/graph/graph.json
```

格式：

```json
{
  "version": "2.0",
  "generated_at": "2026-07-06T22:00:00+08:00",
  "nodes": [
    {
      "id": "apt_group:apt28",
      "name": "APT28",
      "type": "APT_GROUP",
      "aliases": ["Fancy Bear", "Sofacy"],
      "description": "与俄罗斯 GRU 有关联的 APT 组织",
      "confidence": 0.96,
      "source_count": 3,
      "evidence_ids": ["ev_apt28_mitre_001_a1b2"]
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
      "evidence_ids": ["ev_apt28_mitre_001_c3d4"]
    }
  ],
  "evidence": [
    {
      "id": "ev_apt28_mitre_001_a1b2",
      "doc_id": "apt28_mitre_001",
      "chunk_id": "apt28_mitre_001_c001",
      "source_url": "https://attack.mitre.org/groups/G0007/",
      "text": "APT28 is a threat group...",
      "language": "en"
    }
  ],
  "analysis": {
    "mitre_mappings": [
      {
        "mapping_id": "mitre_apt28_t1566",
        "target_group": "APT28",
        "technique_id": "T1566",
        "technique_name": "Phishing",
        "tactic": "Initial Access",
        "attack_stage": "初始访问",
        "confidence": 0.9,
        "evidence_ids": ["ev_apt28_mitre_001_c3d4"]
      }
    ],
    "behavior_patterns": [
      {
        "pattern_id": "pattern_apt28_initial_access",
        "target_group": "APT28",
        "stage": "初始访问",
        "description": "APT28 常通过鱼叉式钓鱼获得初始访问。",
        "technique_ids": ["T1566"],
        "evidence_ids": ["ev_apt28_mitre_001_c3d4"],
        "confidence": 0.88
      }
    ],
    "inferred_relations": [
      {
        "inferred_relation_id": "infer_apt28_initial_access",
        "source": "apt_group:apt28",
        "target": "technique:t1566",
        "type": "HAS_BEHAVIOR",
        "rationale": "APT28 使用鱼叉式钓鱼技术，该技术属于初始访问阶段。",
        "confidence": 0.86,
        "status": "candidate",
        "evidence_ids": ["ev_apt28_mitre_001_c3d4"]
      }
    ]
  }
}
```

导出规则：

1. `nodes` 来自 SQLite `entities`。
2. `edges` 来自 SQLite `relations`。
3. `evidence` 来自 SQLite `evidence`。
4. `analysis` 来自 SQLite 行为分析和推理表。
5. `graph.json` 可以删除后重新生成，不影响事实源。
6. 前端 mock 数据必须与该格式一致。

---

## 7. 实体类型

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

---

## 8. 关系类型

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

---

## 9. Neo4j 同步原则

Neo4j 同步输入只能来自：

```text
SQLite canonical graph tables
或
data/graph/graph.json
```

Neo4j 节点属性至少包含：

```text
id
name
type
aliases
description
confidence
source_count
```

Neo4j 关系属性至少包含：

```text
id
type
label
confidence
evidence_ids
```

同步失败处理：

1. 不回滚 SQLite。
2. 不修改 `graph.json`。
3. 记录同步错误。
4. API 返回清晰错误。
5. 前端降级使用 SQLite 图谱接口。
