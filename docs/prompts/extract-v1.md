# LLM 抽取 Prompt：extract-v1

适用对象：LLM 抽取与分析组 `llm`
适用输入：符合 `docs/schemas/document.schema.json` 的 `document.json`，或后端切块后的 `chunk_id + text`
适用输出：符合 `docs/schemas/extraction-result.schema.json` 的 `extraction_result.json`

## 目标

从开源威胁情报文档中抽取候选实体和候选关系，输出严格 JSON。输出只进入候选层 `extracted_entities` 和 `extracted_relations`，不能生成最终 `entity_id`、`relation_id`，不能直接写 `graph.json`、SQLite 正式图谱或 Neo4j。

## 系统提示词

```text
你是 ThreatGraph-OSINT 项目的 LLM 抽取器，只负责从输入 chunk 中抽取候选实体和候选关系。

必须遵守：
1. 只输出一个 JSON 对象，不要输出 Markdown、解释、注释或多余文本。
2. JSON 必须符合 extraction-result.schema.json。
3. schema_version 固定为 "1.0"。
4. 实体类型只能从允许列表选择。
5. 关系类型只能从允许列表选择，并且必须满足 relationship-matrix.md 的合法主体类型和客体类型。
6. 每条实体和关系都必须填写 evidence_text，且 evidence_text 必须来自输入 chunk 的原文片段。
7. char_start 和 char_end 表示 evidence_text 在 chunk text 中的字符位置；无法可靠定位时填 null，但不要编造位置。
8. candidate_status 第一版统一填 "candidate"。
9. validation_status 第一版统一填 "unchecked"，validation_errors 第一版填 []。
10. 不要生成 entity_id、relation_id、normalized_entity_id、normalized_relation_id 或 evidence_id。
11. 不要把推断关系当作原文事实。原文没有明确支撑时不要抽取关系。
12. RELATED_TO 只能在关系非常弱但必须保留上下文时使用；常规抽取不要使用 RELATED_TO。
```

## 允许的实体类型

```text
APT_GROUP
ORGANIZATION
PERSON
MALWARE
TOOL
CVE
TECHNIQUE
INFRASTRUCTURE
LOCATION
FINANCIAL_ACCOUNT
COUNTRY
REGION
INDUSTRY
TIME
EVENT
CAMPAIGN
BEHAVIOR_PATTERN
```

## 允许的关系类型

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
MEMBER_OF
CONTROLS
TRANSFERS_TO
INSTANCE_OF
PRECEDES
```

关系合法性必须参考 `docs/schemas/relationship-matrix.md`。例如：

```text
APT_GROUP USES MALWARE
APT_GROUP TARGETS COUNTRY
APT_GROUP TARGETS ORGANIZATION
APT_GROUP EXPLOITS CVE
APT_GROUP ATTRIBUTED_TO COUNTRY
APT_GROUP AFFILIATED_WITH ORGANIZATION
ORGANIZATION LOCATED_IN COUNTRY
EVENT HAPPENED_AT TIME
CAMPAIGN PART_OF APT_GROUP
TECHNIQUE LEADS_TO TECHNIQUE
APT_GROUP RELATED_TO ORGANIZATION
MALWARE DISCOVERED_BY ORGANIZATION
CVE CAUSES EVENT
APT_GROUP HAS_BEHAVIOR TECHNIQUE
PERSON MEMBER_OF APT_GROUP
APT_GROUP CONTROLS FINANCIAL_ACCOUNT
FINANCIAL_ACCOUNT TRANSFERS_TO FINANCIAL_ACCOUNT
ORGANIZATION INSTANCE_OF ORGANIZATION
EVENT PRECEDES CAMPAIGN
```

## 用户提示词模板

```text
请基于以下 document/chunk 生成 extraction_result.json。

全局信息：
- schema_version: {schema_version}
- run_id: {run_id}
- doc_id: {doc_id}
- model_name: {model_name}
- prompt_version: extract-v1

chunk 列表：
{chunks}

输出要求：
1. 顶层字段只能包含 schema_version、run_id、doc_id、model_name、prompt_version、chunks。
2. chunks 中每个对象只能包含 chunk_id、entities、relations。
3. entities 中每个对象必须包含 name、type、aliases、description、mention_text、evidence_text、char_start、char_end、confidence、candidate_status、validation_status、validation_errors。
4. relations 中每个对象必须包含 head_name、head_type、relation_type、tail_name、tail_type、evidence_text、char_start、char_end、confidence、candidate_status、validation_status、validation_errors。
5. aliases 和 validation_errors 必须是数组。
6. confidence 是 0 到 1 的数字；证据越直接越高，跨句推断或上下文较弱时降低。
7. evidence_text 必须是输入 chunk 的原文片段，不要写模型自己的解释。
8. 只输出 JSON，不要使用 Markdown 代码块。
```

## 质量检查规则

交付前必须运行：

```bash
python scripts/validate_extraction_result.py \
  data/extracted/extraction_result.apt28.thn.beardshell.v1.json \
  --document data/examples/document.apt28.thn.beardshell.example.json
```

通过标准：

1. JSON Schema 校验通过。
2. `doc_id` 与输入文档一致。
3. `chunk_id` 使用 `doc_id_cNNN` 形式，当前单 chunk 样例使用 `apt28_049_c001`。
4. 每条 `evidence_text` 能在文档 `clean_text` 中找到。
5. 如果填写 `char_start` / `char_end`，对应切片必须精确等于 `evidence_text`。
6. 每条关系满足最小关系合法性矩阵。
7. 不出现最终图谱 ID 字段。
