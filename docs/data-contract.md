# 数据契约

> 适用范围：ThreatGraph-OSINT 项目  
> 唯一事实源：SQLite  
> 导出格式：`data/graph/graph.json`  
> 图查询增强：Neo4j，增强阶段 / 优先级 P1

---

## 1. 数据栈结论

```text
SQLite：唯一事实源
graph.json：导出格式、离线样例、演示兜底、Neo4j 同步输入
Neo4j：增强阶段 / 优先级 P1 图查询增强，不保存唯一事实
```

禁止链路：

```text
LLM 原始输出 -> Neo4j -> 前端
```

允许链路：

```text
sources / data/raw -> SQLite collected_items
data/documents/*.json(clean_text) 或 collected_items 清洗结果 -> SQLite documents -> SQLite chunks
LLM 输出 -> SQLite extracted_* 候选表
归一化 -> SQLite entities/relations/evidence
导出 -> graph.json
同步 -> Neo4j
```

### 1.1 开源项目借鉴后的字段调整

这次架构不推翻 SQLite 事实源，也不把 Neo4j 改成主库。需要吸收的是几个数据建模原则：

| 参考项目   | 吸收原则                   | 落到本项目的字段 / 约束                                                             |
| ---------- | -------------------------- | ----------------------------------------------------------------------------------- |
| OpenCTI    | 证据和来源是一等公民       | `evidence_ids`、`source_name`、`source_reliability`、`published_at`、`retrieved_at` |
| MISP       | 文档是情报容器，不只是文本 | `source_type`、`target_groups_json`、`tags_json`、`tlp`、`content_hash`             |
| SpiderFoot | 采集运行和正式文档隔离     | `collection_runs`、`collected_items`、`documents` 分层，采集失败不污染图谱          |
| GraphRAG   | LLM 输出只能是候选层       | `extracted_*` 增加 `candidate_status`、`normalized_*_id`、`validation_errors_json`  |
| TypeDB CTI | schema-first 和关系合法性  | `schema_version`、`validation_status`、实体类型 / 关系类型合法性矩阵                |

字段调整结论：

1. 所有对外 JSON 都带 `schema_version`，避免前后端和 LLM 组字段漂移。
2. `documents` 必须保留来源元信息和清洗正文：来源名称、来源类型、发布时间、抓取时间、可信度、标签、`clean_text` 和 `content_hash`。
3. `chunks` 由后端基于 `documents.clean_text` 生成，必须保留原文位置：`chunk_index`、`char_start`、`char_end`、`text_hash`；`text_hash` 固定为 `sha256(chunks.text)`。
4. `extracted_*` 必须保留候选状态和校验结果：`candidate_status`、`validation_status`、`validation_errors_json`。
5. LLM 候选结果可以引用归一化结果，但不能决定最终 ID：使用 `normalized_entity_id`、`normalized_relation_id` 记录后端归一化结果。
6. `evidence` 必须补齐证据类型和原文位置：`evidence_type`、`quote_start`、`quote_end`。
7. `entities` / `relations` 保留 `first_seen`、`last_seen`、`tags_json`，便于时间线和来源统计。
8. `graph.json` 是导出快照，需要带 `exported_from` 和 `source_of_truth`，明确它不是事实源。

### 1.2 当前冻结的契约文件

Schema 文件：

```text
docs/schemas/document.schema.json
docs/schemas/extraction-result.schema.json
docs/schemas/golden.schema.json
docs/schemas/graph.schema.json
docs/schemas/relationship-matrix.md
```

可复制样例：

```text
data/examples/document.apt28.thn.beardshell.example.json
data/examples/reference.apt28.mitre.example.json
data/examples/extraction_result.apt28.thn.beardshell.example.json
data/examples/graph.apt28.thn.beardshell.example.json
data/examples/golden.apt28.thn.beardshell.example.json
```

正式 P0 文档：

```text
data/documents/<target_group>/*.json
```

`data/examples/` 只用于字段对齐和 mock；真实清洗文档进入 `data/documents/`，并且必须兼容 `docs/schemas/document.schema.json`。

使用规则：

1. data 组提交真实样本时，复制 `document.apt28.thn.beardshell.example.json` 的字段结构，在 `data/documents/<target_group>/` 下新增文档，替换 `clean_text`、来源，并按 `clean_text` 重新生成 `content_hash`。
2. arch / qa / be 做标准名和别名对齐时，参考 `reference.apt28.mitre.example.json`。
3. llm 组提交候选抽取时，复制 `extraction_result.apt28.thn.beardshell.example.json` 后替换候选实体和候选关系。
4. be 导出图谱时，输出必须兼容 `graph.schema.json` 和 `graph.apt28.thn.beardshell.example.json`。
5. qa 做人工标准答案时，先从 `golden.apt28.thn.beardshell.example.json` 扩展，并保持兼容 `docs/schemas/golden.schema.json`。
6. 字段改动先改 schema 和样例，再同步代码；不能只改一端。

APT28 首个样例的字段标准：

1. Securelist、Mandiant、Microsoft、ESET 等厂商威胁情报文章使用 `source_type = vendor_report`。
2. MITRE ATT&CK、MISP Galaxy 等标准知识库使用 `source_type = knowledge_base`。
3. `target_group` 只放标准名，例如 `APT28`；别名放在实体 `aliases_json` / JSON 样例的 `aliases` 中。
4. 仓库 P0 `document.json` 使用 `clean_text` 保存人工清洗后的正文，不要求保存完整网页原文；原始采集文本只放在 `data/raw/` 或 `collected_items.raw_text`。
5. `evidence_type = summary` 表示证据文本来自人工清洗摘要；只有保留短原文片段时才使用 `direct_quote`。

### 1.3 三份 JSON 的开发工作流

```text
document.json
  data 组交付到 data/documents/ 的清洗后文档，是后端切块后的 LLM 输入来源

extraction_result.json
  llm 组基于 document.json 生成的候选实体和候选关系，是后端归一化的输入

golden.json
  qa 组维护的人工标准答案，用于评测候选抽取质量；结构和 extraction_result 一样按 chunks 归属实体和关系，但不包含候选状态、置信度或后端最终实体/关系 ID

graph.json
  be 从 SQLite 正式图谱导出的快照，是演示兜底和 Neo4j 同步输入；如用于前端 mock，需要先适配为 API 的轻量图谱视图
```

边界：

1. `document.json` 只承载来源元信息和清洗正文 `clean_text`，不承载最终实体 ID，也不要求 data 组手写 chunks。
2. `extraction_result.json` 只承载 LLM 候选结果，不承载最终 `entity_id` / `relation_id`。
3. `golden.json` 只承载人工标准答案，实体和关系都必须归属到后端生成的 `chunk_id`；临时 mock 阶段可以使用 `${doc_id}_c001`，但不能由 data / QA / LLM 自行引入新的切块规则。
4. `golden.json` 的实体使用 `name`、`type`、`aliases` 和证据字段描述，不包含人工生成的 `canonical_id` 或最终 `entity_id`；正式 `entity_id` 由后端归一化服务生成。
5. `golden.json` 的关系字段和 `extraction_result.json` 保持一致，统一使用 `head_name`、`head_type`、`relation_type`、`tail_name`、`tail_type`。
6. `graph.json` 只承载后端归一化后的正式图谱快照，不能由 LLM 直接生成。
7. `/api/v1/graph` 的响应结构以 `docs/api-contract.md` 为准，不直接绑定完整 GraphSnapshot。
8. `docs/schemas/graph.schema.json` 只约束导出的 `data/graph/graph.json` 快照。
9. `reference.*.json` 是标准知识库参考，不进入“真实文章清洗 -> LLM 抽取”的主链路。

### 1.4 P0 文档清洗边界

P0 阶段的清洗是格式清洗，不是语义筛选。data 组需要把网页、PDF 或本地文本整理成可读、可切块、可追溯的正文。

应该做：

1. 去掉导航栏、菜单、广告、推荐文章、评论区、页脚、订阅提示和脚本噪声。
2. 保留标题、正文段落、小标题、列表、表格中的有效文字和必要上下文。
3. 保留原文顺序，尽量不改写原句。
4. 记录 `source_url`、`source_name`、`published_at`、`retrieved_at`、`language`、`target_group` 和基于 `clean_text` 的 `content_hash`。

不应该做：

1. 不提前删除作者评估、推测或讨论性段落。
2. 不提前判断哪些句子是事实、哪些关系成立。
3. 不把正文改写成自己的总结后再当作完整原文。
4. 不把整个浏览器页面原样转成 TXT 后直接提交。

仓库里的 `document.apt28.thn.beardshell.example.json` 选自 `data/documents/apt28/apt28_049.json`，用于展示一条可证据对齐的完整样例链路；data 组真实工作时继续按同一字段契约导入。

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

来源字段语义以本节和 SQLite `sources` 表为准，不再依赖 `data/sources/` 下的解释性 JSON。历史转换工具产出的来源索引如果只用于复查或迁移，放在 `data/raw/<collector>/`，不要作为 P0 主数据目录。

字段含义：

```text
source_type：来源类型，如 vendor_report、knowledge_base、government_notice、news、social_forum、blog；security_report 只作为无法细分时的泛称
collector_type：采集器类型，如 local_json、http_page、rss_feed
target_groups_json：该来源默认覆盖的目标组织
config_json：采集器配置，如语言、默认目标组织、解析规则
source_reliability：来源可信度，A/B/C/D 或 unknown
tags_json：来源标签，如 vendor、mitre、news、social
```

```sql
CREATE TABLE sources (
  source_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  collector_type TEXT NOT NULL,
  url TEXT NOT NULL,
  target_groups_json TEXT NOT NULL DEFAULT '[]',
  source_reliability TEXT NOT NULL DEFAULT 'unknown',
  tags_json TEXT NOT NULL DEFAULT '[]',
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

保存采集到的原始条目。这里还不是最终文档事实，需要清洗为 `documents.clean_text` 后再进入切块和抽取。

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
  raw_content_hash TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  source_reliability TEXT NOT NULL DEFAULT 'unknown',
  tags_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL CHECK (status IN ('collected', 'imported', 'skipped', 'failed')),
  created_at TEXT NOT NULL,
  FOREIGN KEY (collection_run_id) REFERENCES collection_runs(collection_run_id),
  FOREIGN KEY (source_id) REFERENCES sources(source_id)
);
```

### 3.4 documents

保存清洗后的标准文档。`clean_text` 是后端切块和 LLM 抽取的输入，`content_hash` 固定为 `sha256(clean_text 按 UTF-8 编码后的字节)`。

```sql
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL DEFAULT '1.0',
  collection_item_id TEXT,
  target_group TEXT NOT NULL,
  target_groups_json TEXT NOT NULL DEFAULT '[]',
  source_url TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
  clean_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  published_at TEXT,
  retrieved_at TEXT,
  source_reliability TEXT NOT NULL DEFAULT 'unknown',
  tlp TEXT NOT NULL DEFAULT 'TLP:CLEAR',
  tags_json TEXT NOT NULL DEFAULT '[]',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY (collection_item_id) REFERENCES collected_items(item_id)
);
```

### 3.5 chunks

保存后端基于 `documents.clean_text` 生成的 LLM 输入片段。data 组不手写 chunks。

```sql
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL DEFAULT 0,
  section_title TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  text_hash TEXT NOT NULL,
  token_count INTEGER,
  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
);
```

### 3.6 extraction_runs

保存每次 LLM 抽取任务。

```sql
CREATE TABLE extraction_runs (
  run_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL DEFAULT '1.0',
  doc_id TEXT NOT NULL,
  model_name TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  parameters_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
  validation_status TEXT NOT NULL DEFAULT 'unchecked' CHECK (validation_status IN ('unchecked', 'valid', 'invalid')),
  validation_errors_json TEXT NOT NULL DEFAULT '[]',
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
  mention_text TEXT NOT NULL DEFAULT '',
  evidence_text TEXT NOT NULL,
  char_start INTEGER,
  char_end INTEGER,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  candidate_status TEXT NOT NULL DEFAULT 'candidate' CHECK (candidate_status IN ('candidate', 'accepted', 'rejected', 'merged')),
  normalized_entity_id TEXT,
  validation_status TEXT NOT NULL DEFAULT 'unchecked' CHECK (validation_status IN ('unchecked', 'valid', 'invalid')),
  validation_errors_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
  FOREIGN KEY (normalized_entity_id) REFERENCES entities(entity_id)
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
  char_start INTEGER,
  char_end INTEGER,
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  candidate_status TEXT NOT NULL DEFAULT 'candidate' CHECK (candidate_status IN ('candidate', 'accepted', 'rejected', 'merged')),
  normalized_relation_id TEXT,
  validation_status TEXT NOT NULL DEFAULT 'unchecked' CHECK (validation_status IN ('unchecked', 'valid', 'invalid')),
  validation_errors_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id),
  FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
  FOREIGN KEY (normalized_relation_id) REFERENCES relations(relation_id)
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
  first_seen TEXT,
  last_seen TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
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
  source_count INTEGER NOT NULL DEFAULT 0,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT,
  last_seen TEXT,
  validation_status TEXT NOT NULL DEFAULT 'valid' CHECK (validation_status IN ('valid', 'invalid')),
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
  evidence_type TEXT NOT NULL DEFAULT 'direct_quote' CHECK (evidence_type IN ('direct_quote', 'summary', 'inference_support')),
  quote_start INTEGER,
  quote_end INTEGER,
  source_url TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT '',
  source_name TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  retrieved_at TEXT,
  source_reliability TEXT NOT NULL DEFAULT 'unknown',
  language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
  created_at TEXT NOT NULL,
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
2. data / QA 不手工生成最终 ID，golden 实体不携带 `canonical_id` 或 `entity_id`。
3. 后端归一化服务负责基于实体名称、类型和别名生成 ID。
4. 别名归并到同一实体。
5. CVE、MITRE ATT&CK 编号保留原始编号。

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
  "schema_version": "1.0",
  "generated_at": "2026-07-06T22:00:00+08:00",
  "exported_from": "sqlite",
  "source_of_truth": "data/threatgraph_osint.db",
  "nodes": [
    {
      "id": "apt_group:apt28",
      "name": "APT28",
      "type": "APT_GROUP",
      "aliases": ["Fancy Bear", "Sofacy"],
      "description": "与俄罗斯 GRU 有关联的 APT 组织",
      "confidence": 0.96,
      "source_count": 3,
      "first_seen": "2014-01-01",
      "last_seen": "2026-07-01",
      "tags": ["apt", "russia", "mitre"],
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
      "source_count": 2,
      "evidence_count": 1,
      "first_seen": "2015-01-01",
      "last_seen": "2024-12-31",
      "validation_status": "valid",
      "evidence_ids": ["ev_apt28_mitre_001_c3d4"]
    }
  ],
  "evidence": [
    {
      "id": "ev_apt28_mitre_001_a1b2",
      "doc_id": "apt28_mitre_001",
      "chunk_id": "apt28_mitre_001_c001",
      "entity_id": "apt_group:apt28",
      "relation_id": null,
      "source_url": "https://attack.mitre.org/groups/G0007/",
      "source_type": "knowledge_base",
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
6. `graph.json` 作为完整 GraphSnapshot，可用于离线演示兜底和 Neo4j 同步输入；前端模拟 `/api/v1/graph` 时仍按 `docs/api-contract.md` 的轻量 GraphView 返回。
7. `schema_version` 变更前必须同步架构、后端、前端和 LLM。
8. `evidence.text` 可以是原文短片段或人工清洗后的证据短句，但必须能通过 `doc_id`、`chunk_id`、`quote_start`、`quote_end` 回到原文。

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
INFRASTRUCTURE
LOCATION
```

一个文本实体只能选择一个主类型。命名组织、人、国家、地区或地点使用对应具体类型；`TARGET` 仅用于原文明示的泛指受害群体或机构类别；`INDUSTRY` 仅表示原文明示的行业。P0 不根据常识从具体组织自动补行业或目标类别。

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
PRECEDES
INSTANCE_OF
IN_INDUSTRY
```

关系方向和合法端点以 `docs/schemas/relationship-matrix.md` 为准。`PART_OF` 不得用于表示实例归类或行业归属。

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
