# S1 契约上手指南

> 适用阶段：Step 1 真实样本文档闭环；适用对象：data、llm、be、fe、qa；正式契约来源：`docs/schemas/`、`docs/data-contract.md`、`docs/api-contract.md`

## 1. 先理解三份 JSON 的边界

S1 阶段先用固定 JSON 契约让各组并行，不等完整采集平台和完整流水线。

```text
data 组
  -> data/documents/<target_group>/*.json(clean_text)
  -> 给 be 导入

be 横向工作流
  -> SQLite documents
  -> SQLite chunks
  -> 给 llm 使用

llm 组
  -> extraction_result.json
  -> 给 be 归一化使用

be 横向工作流
  -> SQLite canonical graph
  -> graph.json 导出快照
  -> /api/v1/graph 轻量 GraphView

fe 组
  -> 只消费 FastAPI API

qa 组
  -> golden.json / 验收记录 / 错误样例
```

核心规则：

1. `document.json` 只放来源元信息和清洗正文 `clean_text`，不放最终实体 ID，也不放 chunks。
2. `extraction_result.json` 只放 LLM 候选实体和候选关系，不放最终关系 ID。
3. `golden.json` 只放人工标准答案，按后端 chunk 归属实体和关系，关系字段和 extraction_result 保持 `head_name` / `tail_name` 命名。
4. `graph.json` 只能由 SQLite 正式图谱导出，不能由 LLM 或人工直接当事实源维护。
5. 前端默认使用 `/api/v1/graph`，不直接读取 `graph.json`。
6. 字段变更先改 schema 和样例，再同步相关组。

## 2. data 组：如何准备 document.json

data 组当前目标是准备第一份可追溯的真实样本文档。当前完整样例选用 APT28 的 The Hacker News cleaned document，后续也可以继续补充安全厂商报告，例如 Securelist、Mandiant、Microsoft、ESET 等。

参考文件：

```text
docs/schemas/document.schema.json
data/examples/document.apt28.thn.beardshell.example.json
data/documents/<target_group>/*.json
docs/data-contract.md
```

输出位置：

```text
data/documents/apt28/*.json
data/documents/lazarus/*.json
data/documents/kimsuky/*.json
```

### 2.1 手工填写字段

下面这些字段是 data 组需要理解并尽量手工确认的字段。

| 字段            | 语义                   | 填写规则                                                                                                                                                            |
| --------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `doc_id`        | 文档唯一 ID            | 用小写英文、数字、短横线或下划线。建议包含目标、来源、标题关键词和序号，例如 `apt28_049` 或 `apt28_thn_beardshell_001`。                                            |
| `target_group`  | 主目标组织             | 使用标准名，例如 `APT28`、`Lazarus`、`Kimsuky`。不要填别名或小写随意写法。                                                                                          |
| `target_groups` | 文档涉及的目标组织列表 | 单目标时填 `[target_group]`，例如 `["APT28"]`。                                                                                                                     |
| `source_url`    | 原始资料 URL           | 尽量填公开链接，不能用空字符串。确实是本地整理资料时，在 `metadata` 说明来源。                                                                                      |
| `source_type`   | 来源类型               | 厂商报告填 `vendor_report`；MITRE/MISP 等知识库填 `knowledge_base`；政府公告填 `government_notice`；新闻填 `news`；社媒或论坛整理填 `social_forum`；博客填 `blog`。 |
| `source_name`   | 发布方名称             | 例如 `Kaspersky Securelist`、`Microsoft Security Blog`、`MITRE ATT&CK`。                                                                                            |
| `title`         | 原文标题               | 保留原始标题，不要改成自己的总结标题。                                                                                                                              |
| `language`      | 文档语言               | 只填 `en` 或 `zh`。                                                                                                                                                 |
| `clean_text`    | 清洗后的正文           | 去掉网页导航、广告、评论、页脚和脚本噪声后保留正文。尽量保留原文顺序和原句，不要改写成自己的总结。                                                                  |
| `published_at`  | 原文发布时间           | 能确定时填 `YYYY-MM-DD` 或原文明确日期；不确定时填 `null`，不要填空字符串。                                                                                         |
| `retrieved_at`  | 获取或整理时间         | 填整理该样本的时间，建议 ISO 格式并带时区，例如 `2026-07-08T10:00:00+08:00`。                                                                                       |
| `tags`          | 检索和分类标签         | 不放空字符串。建议包含来源、厂商、目标组织和来源类型，例如 `["securelist", "kaspersky", "apt", "apt28", "vendor_report"]`。                                         |

如果数据组已有简化格式，可以这样映射到正式契约：

| 简化字段         | 正式字段               |
| ---------------- | ---------------------- |
| `published_date` | `published_at`         |
| `crawl_time`     | `retrieved_at`         |
| `text` / `body`  | `clean_text`           |
| `tags`           | `tags`，但要删除空标签 |

### 2.2 可默认或脚本补齐字段

这些字段有价值，但不应该增加 data 组手工负担。

| 字段                 | 价值                                         | 建议填法                                                                                |
| -------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------- |
| `schema_version`     | 标识当前 JSON 契约版本，避免后续字段漂移     | 固定填 `"1.0"`。                                                                        |
| `content_hash`       | 用于去重、判断正文是否变化、复现实验         | 可由脚本根据 `clean_text` 的 UTF-8 字节生成；正式提交时必须是 `sha256:<64位十六进制>`。 |
| `source_reliability` | 表示来源可信度，后续可用于证据权重和报告说明 | 官方知识库或知名厂商报告可填 `A`；不确定填 `unknown`。                                  |
| `tlp`                | 标识情报共享级别，避免误提交敏感材料         | 公开资料默认 `TLP:CLEAR`。                                                              |
| `metadata`           | 放扩展说明，不污染主字段                     | 没有额外信息填 `{}`；可记录 `collector`、`notes`、`aliases`、`cleaning_notes`。         |

### 2.3 清洗边界

应该做：

1. 去掉导航栏、广告、相关推荐、评论、页脚、订阅提示和脚本噪声。
2. 保留标题、正文段落、小标题、列表和表格中的有效文字。
3. 保留原文顺序，尽量不改写原句。
4. 保留能支持实体和关系抽取的证据句。

不应该做：

1. 不提前判断哪些关系是真的、哪些应该删除。
2. 不把原文改写成自己的摘要后当作完整正文。
3. 不把 MITRE ATT&CK 或 MISP Galaxy 当作首篇真实正文清洗样本。
4. 不把整个网页 HTML 原样提交。

### 2.4 data 组交付检查

提交给下游前至少检查：

1. `source_url`、`source_name`、`title`、`language`、`clean_text` 不为空。
2. `target_group` 使用标准名，别名放到 `metadata.aliases` 或后续实体别名里。
3. `source_type` 属于 schema 枚举。
4. `published_at` 不确定时是 `null`，不是 `""`。
5. `tags` 没有空字符串。
6. `clean_text` 是清洗正文，不是结论性摘要。
7. `content_hash` 和当前 `clean_text` 的 UTF-8 字节内容对应。

## 3. llm 组：拿到 document.json 后做什么

llm 组基于后端生成的 `chunks` 生成 `extraction_result.json`。第一版可以手写或使用 mock LLM 输出；如果后端切块还没完成，可以先把一篇文档视作一个 chunk，并使用 `${doc_id}_c001` 这类确定性 `chunk_id`。

参考文件：

```text
docs/schemas/extraction-result.schema.json
data/examples/extraction_result.apt28.thn.beardshell.example.json
docs/schemas/relationship-matrix.md
```

操作步骤：

1. 读取 data 组交付的 `doc_id` 和切块后的 `chunk_id`。
2. 对每个 chunk 抽取候选实体，填写 `name`、`type`、`aliases`、`mention_text`、`evidence_text` 和 `confidence`。
3. 对每个 chunk 抽取候选关系，填写 `head_name`、`head_type`、`relation_type`、`tail_name`、`tail_type`、`evidence_text` 和 `confidence`。
4. `candidate_status` 第一版统一填 `candidate`。
5. `validation_status` 第一版可填 `unchecked`，后端校验后再更新为 `valid` 或 `invalid`。
6. 关系类型必须优先从 `relationship-matrix.md` 中选择，不要临时发明新关系。
7. 证据文本必须能从原文或清洗正文中找到，不要只写模型自己的解释。

不要做：

1. 不生成最终 `entity_id` 或 `relation_id`。
2. 不直接写 `graph.json`。
3. 不把推断关系当作原文直接事实。
4. 不滥用 `RELATED_TO` 作为默认关系。

交付检查：

1. `doc_id` 和 data 组文档一致。
2. 每条实体和关系都有 `evidence_text`。
3. 每个 `type` 都在实体类型枚举里。
4. 每个 `relation_type` 都在关系类型枚举里。
5. 置信度是 0 到 1 之间的数字。

## 4. be 横向工作流：拿到候选结果后做什么

be 不是独立小组，而是后端横向工作流，默认由 arch 牵头。当前重点是把 data 和 llm 的交付接入 SQLite，并导出可复现图谱。

参考文件：

```text
docs/data-contract.md
docs/api-contract.md
docs/schemas/graph.schema.json
data/examples/graph.apt28.thn.beardshell.example.json
```

操作步骤：

1. 导入 `document.json` 到 `documents`，保存 `clean_text` 和来源元信息。
2. 基于 `clean_text` 切块并写入 `chunks`，保留 `doc_id`、`chunk_id`、`char_start`、`char_end` 和 `text_hash`，其中 `text_hash = sha256(chunks.text)`。
3. 将 `extraction_result.json` 写入 `extraction_runs`、`extracted_entities` 和 `extracted_relations`。
4. 按实体类型、关系类型和最小关系矩阵做校验。
5. 归一化实体和关系，生成最终 `entity_id` 和 `relation_id`。
6. 将可信候选写入 `entities`、`relations` 和 `evidence`。
7. 从 SQLite 导出 `data/graph/graph.json`。
8. `/api/v1/graph` 返回轻量 GraphView，不直接照搬完整 GraphSnapshot。

不要做：

1. 不让 LLM 输出直接进入正式 `entities` 和 `relations`。
2. 不让 Neo4j 成为事实源。
3. 不让前端直接读取 SQLite、`graph.json` 或 Neo4j。

交付检查：

1. 同一实体别名能归并到同一标准实体。
2. 所有 `nodes.evidence_ids` 和 `edges.evidence_ids` 都能在 `evidence` 中找到。
3. `graph.json` 可被 `docs/schemas/graph.schema.json` 校验。
4. `/api/v1/graph` 字段仍符合 `docs/api-contract.md`。

## 5. fe 组：拿到图谱契约后做什么

fe 组只对接 FastAPI，不直接读取本地文件。`graph.json` 可以作为理解字段或后端 mock 的参考，但不是前端运行时的正式输入。

参考文件：

```text
docs/api-contract.md
data/examples/graph.apt28.thn.beardshell.example.json
```

操作步骤：

1. 以 `/api/v1/graph` 响应结构定义前端 TypeScript 类型。
2. 图谱节点展示 `name`、`type`、`confidence`、`source_count` 和 `tags`。
3. 图谱关系展示 `type`、`label`、`confidence` 和 `evidence_count`。
4. 实体或关系详情页展示对应证据，不只展示自然语言结论。
5. 行为分析、MITRE 映射和推理结果优先从 `/api/v1/analysis/*` 获取。

不要做：

1. 不直接读取 `data/graph/graph.json`。
2. 不在前端做实体归一化。
3. 不私自改 API 字段名。
4. 不把推断关系展示成已确认事实。

交付检查：

1. 后端返回空节点、空证据或接口失败时页面有可理解的状态。
2. 证据事实和系统推断在 UI 上能区分。
3. 前端类型和 `docs/api-contract.md` 保持一致。

## 6. qa 组：拿到样例后做什么

qa 组负责把样例变成可评测、可答辩、可复现的证据。

参考文件：

```text
data/examples/golden.apt28.thn.beardshell.example.json
docs/schemas/golden.schema.json
docs/team-workflow.md
docs/references/course-requirements.md
```

操作步骤：

1. 基于 `golden.apt28.thn.beardshell.example.json` 扩充人工标准答案，并通过 `golden.schema.json`。
2. 使用后端生成的 `chunk_id` 归属实体和关系；后端切块不可用时，可以临时使用 `${doc_id}_c001` 单 chunk 约定。
3. 关系字段统一填写 `head_name`、`head_type`、`relation_type`、`tail_name`、`tail_type`，不要再使用 `source` / `target` 作为 golden 字段名。
4. 记录 LLM 漏抽、错抽、关系类型错误和证据不足样例。
5. 检查 data 组文档是否有来源、时间、语言和清洗说明。
6. 检查 be 导出的 `graph.json` 是否能追溯到 evidence。
7. 准备答辩材料时区分“已经实现”“手动步骤”“P1/P2 展望”。

交付检查：

1. golden 样例不追求全量，只追求小而准确。
2. 每条标准关系都带可核对的 `evidence_text`。
3. 每条标准实体和关系都放在对应 `chunks[].entities` 或 `chunks[].relations` 中。
4. 评测结论说明样本规模和局限，不夸大能力。

## 7. 最小协作节奏

建议按下面顺序推进，不互相等待完整系统。

```text
第 1 步：data 组交 1 篇 data/documents/apt28/*.json(clean_text)
第 2 步：be 导入文档并生成 chunks；mock 阶段可先约定 ${doc_id}_c001
第 3 步：llm 组基于 chunks 交 1 份 extraction_result.json
第 4 步：be 归一化并导出 graph.json，同时提供 /api/v1/graph
第 5 步：fe 用 API 展示图谱、实体详情和证据
第 6 步：qa 用 golden.json 记录正确答案和错误样例
```

如果某一步暂时没有代码，可以先用样例 JSON 或 mock 输出推进。关键是字段不要漂移，证据链不要断。

### 7.1 真实 API 前的离线闭环命令

在接入真实 LLM API 前，先用人工审阅的 `extraction_result.json` 跑通 SQLite 候选层和正式图谱层：

```bash
python scripts/import_extraction_result.py \
  --document data/examples/document.apt28.thn.beardshell.example.json \
  --extraction-result data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760.json \
  --export-graph
```

这条命令会完成：

1. 写入 `documents` 和 `chunks`。
2. 写入 `extraction_runs`、`extracted_entities` 和 `extracted_relations`。
3. 按 schema、证据文本和关系矩阵校验候选结果。
4. 将合法候选归一化到 `entities`、`relations` 和 `evidence`。
5. 基于正式关系生成第一版 `behavior_patterns` 和报告缓存。
6. 从 SQLite 导出 `data/graph/graph.json`。

注意：该命令不调用真实 LLM API，输入仍是本地 JSON。后续接入真实 API 时，只替换 `extraction_result.json` 的生成方式，后面的校验、入库、归一化和导出流程保持不变。

## 8. 字段变更规则

任何组觉得字段不够用时，先按下面流程处理：

1. 写清楚要新增或删除的字段。
2. 说明字段属于文档层、候选层、正式图谱层、API 层还是评测层。
3. 说明示例值、是否必填、是否可由系统默认生成。
4. 先通知 arch 评审。
5. 通过后同步修改 schema、样例、契约文档和相关代码。

不要只在自己的 JSON 或代码里临时加字段。跨组字段一旦漂移，后续导入、抽取、前端展示和评测都会断。
