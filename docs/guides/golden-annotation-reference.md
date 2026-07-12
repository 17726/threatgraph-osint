# 黄金集标注参考手册

> 适用对象：QA 组人工制作 `golden.json`。正式契约以 `docs/schemas/golden.schema.json`、`docs/data-contract.md` 和 `data/examples/golden.apt28.thn.beardshell.example.json` 为准。

---

## 1. 基本定位

`golden.json` 是人工标准答案，用来评测 LLM 候选抽取结果，不是 LLM 输出，也不是最终图谱快照。

正式 golden 应当是在当前标注范围和规则下可直接用于评测的完整正确答案。`entities` 和 `relations` 只放人工确认的正例；待确认项、被排除项和 LLM 错误样例不混入标准答案。

`chunk_id` 由后端切块生成；后端切块不可用时，临时使用 `${doc_id}_c001` 单 chunk 约定。

建议文件位置：

```text
data/evaluation/golden.<target_group>.<dataset>.json
```

示例：

```text
data/evaluation/golden.apt28.core.json
data/evaluation/golden.kimsuky.core.json
```

历史迁移材料或旧格式文件不要直接放入 `data/evaluation/` 作为正式 golden；需要复查时放在 `data/raw/<collector>/`。

---

## 2. 顶层结构

```json
{
  "schema_version": "1.0",
  "target_group": "APT28",
  "doc_ids": ["apt28_049"],
  "chunks": [
    {
      "chunk_id": "apt28_049_c001",
      "doc_id": "apt28_049",
      "char_start": 0,
      "char_end": 4849,
      "note": "临时单 chunk 样例；正式流程使用后端生成的 chunk。",
      "entities": [],
      "relations": []
    }
  ],
  "notes": "人工核验后的标准答案，用于评测实体和关系抽取。"
}
```

| 字段             | 填写规则                                                                                       |
| ---------------- | ---------------------------------------------------------------------------------------------- |
| `schema_version` | 固定 `"1.0"`。                                                                                 |
| `target_group`   | 本 golden 主评测目标组织，例如 `APT28`、`Kimsuky`、`Lazarus`。                                 |
| `doc_ids`        | 本 golden 覆盖的文档 ID 列表，必须能对应到 `data/documents/<target_group>/*.json` 或样例文档。 |
| `chunks`         | 后端切块结果。实体和关系都写在对应 chunk 内。                                                  |
| `notes`          | 写明数据来源、统一排除口径、标注范围和已知限制。                                                 |

---

## 3. chunk 填写规则

```json
{
  "chunk_id": "apt28_049_c001",
  "doc_id": "apt28_049",
  "char_start": 0,
  "char_end": 4849,
  "note": "当前文档作为单 chunk 标注。",
  "entities": [],
  "relations": []
}
```

| 字段                      | 填写规则                                                                     |
| ------------------------- | ---------------------------------------------------------------------------- |
| `chunk_id`                | 使用后端生成值。mock 阶段可用 `${doc_id}_c001`。                             |
| `doc_id`                  | 该 chunk 所属文档 ID。                                                       |
| `char_start` / `char_end` | chunk 在文档 `clean_text` 中的位置；不确定时先用后端输出，不手写新切块规则。 |
| `note`                    | 可选，说明临时单 chunk、截断、人工复查等情况。                               |
| `entities`                | 当前 chunk 的人工标准实体。                                                  |
| `relations`               | 当前 chunk 的人工标准关系。                                                  |

QA 不负责重新切块。若发现 chunk 范围影响标注，应反馈给后端或架构组，而不是在 golden 中自行发明新的 chunk 规则。

顶层 `notes` 适合记录整份 golden 共用的口径，例如：

```text
本黄金集只标注与威胁事件、攻击活动、工具、漏洞、目标、归因、发现或披露等情报事实相关的实体；文章作者、编辑和页面维护者等来源元信息主体不列入 entities。
```

单个 chunk 的局部排除或争议写在该 chunk 的 `note` 中，例如：`排除 John Doe：仅为文章署名作者，与威胁事件事实无关。`

---

## 4. entities 填写规则

实体写在所属 chunk 的 `entities` 数组里，不再带 `chunk_id` 字段。

```json
{
  "name": "APT28",
  "type": "APT_GROUP",
  "aliases": ["UAC-0001"],
  "evidence_text": "Russia-linked APT28 (aka UAC-0001) threat actors",
  "char_start": 92,
  "char_end": 142
}
```

| 字段                      | 填写规则                                                                                                 |
| ------------------------- | -------------------------------------------------------------------------------------------------------- |
| `name`                    | 实体标准名。优先使用文档中的主称呼；同一实体跨文档尽量保持一致。                                         |
| `type`                    | 只能从实体类型枚举中选择。拿不准时先记录为待确认，不要为了过 schema 随便填。                             |
| `aliases`                 | 同一实体的其他名称；没有别名填 `[]`，不要把别名拆成多个实体。                                             |
| `evidence_text`           | 从当前 chunk 文本中连续截取的证据片段。                                                                  |
| `char_start` / `char_end` | `evidence_text` 在当前 chunk 文本中的 0-based 起止位置；单 chunk mock 时等同于在 `clean_text` 中的位置。 |

实体类型枚举：

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

常见选择：

| 类型                 | 适用对象                                                        |
| -------------------- | --------------------------------------------------------------- |
| `APT_GROUP`          | APT28、Lazarus、Kimsuky、KONNI 等组织或攻击团伙。               |
| `ORGANIZATION`       | 安全厂商、政府机构、受害组织、研究机构。                        |
| `MALWARE`            | 恶意软件、后门、木马、载荷家族。                                |
| `TOOL`               | PowerShell、certutil.exe、KakaoTalk、合法管理工具、协议或 API。 |
| `CVE`                | 标准 CVE 编号。                                                 |
| `TECHNIQUE`          | 钓鱼邮件、DLL 侧加载、XSS、凭据窃取等攻击手法。                 |
| `INFRASTRUCTURE`    | 域名、IP、URL、C2 地址或服务器等攻击基础设施。                 |
| `LOCATION`          | 具体地点、军事基地、机场或设施位置。                            |
| `FINANCIAL_ACCOUNT` | 银行账户、支付账户或加密货币钱包。                              |
| `COUNTRY` / `REGION` | 国家或地区。                                                    |
| `CAMPAIGN` / `EVENT` | 系列攻击活动或单次事件。                                        |

---

## 5. 实体名称、别名和 ID 归属

golden 实体不填写 `canonical_id` 或最终 `entity_id`。QA 负责确认 `name`、`type`、`aliases` 和证据，后端归一化服务负责合并同一实体并生成正式 `entity_id`。

对齐规则：

1. `name` 使用团队确认的首选名称；有权威标准名时优先使用标准名。
2. 同一实体的其他名称写入 `aliases`，不要按别名重复创建实体。
3. 实体匹配同时考虑 `type`、标准化后的 `name` 和 `aliases`，不能只比较原始字符串。
4. 同名但类型不同的对象不能直接合并。
5. 无法确认两个名称是否指向同一实体时，先在 chunk 的 `note` 中记录待复核，不强行合并。
6. 正式 `entity_id` 及候选实体的 `normalized_entity_id` 均由后端生成，不由 data、QA 或 LLM 手工填写。

### 5.1 实体是否进入 golden

1. 与威胁事件相关的实体应写入 `entities`，即使当前 chunk 没有足够证据标注它与其他实体的关系。
2. 文章作者、编辑、页面维护者等只承担来源元信息角色的对象，不写入 `entities`。
3. 如果作者或研究人员在正文中承担发现、披露、归因等情报事实角色，可以按证据标注对应实体和关系。
4. 不要先把无关实体写进 `entities`，再依赖 `notes` 将其排除；评测器会把 `entities` 中的内容视为正例。

---

## 6. relations 填写规则

关系写在所属 chunk 的 `relations` 数组里，不再带 `chunk_id` 字段。

```json
{
  "head_name": "APT28",
  "head_type": "APT_GROUP",
  "relation_type": "USES",
  "tail_name": "BEARDSHELL",
  "tail_type": "MALWARE",
  "evidence_text": "APT28 ... deliver two previously undocumented malware families dubbed BEARDSHELL and COVENANT.",
  "char_start": 92,
  "char_end": 235
}
```

| 字段                      | 填写规则                                                       |
| ------------------------- | -------------------------------------------------------------- |
| `head_name`               | 关系主体名称，必须能在当前 chunk 的 `entities[].name` 中找到。 |
| `head_type`               | 关系主体类型，必须和对应实体 `type` 一致。                     |
| `relation_type`           | 只能从关系类型枚举中选择，并满足关系矩阵。                     |
| `tail_name`               | 关系客体名称，必须能在当前 chunk 的 `entities[].name` 中找到。 |
| `tail_type`               | 关系客体类型，必须和对应实体 `type` 一致。                     |
| `evidence_text`           | 从当前 chunk 文本中连续截取，能证明该关系成立。                |
| `char_start` / `char_end` | `evidence_text` 在当前 chunk 文本中的 0-based 起止位置。       |

关系类型：

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

最小关系矩阵以 `docs/schemas/relationship-matrix.md` 为准。常用关系可按下面理解：

| 关系            | 含义                           | 常见主体                                      | 常见客体                                                      |
| --------------- | ------------------------------ | --------------------------------------------- | ------------------------------------------------------------- |
| `USES`          | 使用工具、恶意软件、技术或基础设施 | `PERSON` / `ORGANIZATION` / `COUNTRY` / `APT_GROUP` / `CAMPAIGN` | `MALWARE` / `TOOL` / `TECHNIQUE` / `INFRASTRUCTURE` |
| `TARGETS`       | 攻击或针对                     | `APT_GROUP` / `CAMPAIGN` / `MALWARE`          | `COUNTRY` / `REGION` / `INDUSTRY` / `ORGANIZATION` / `PERSON` / `LOCATION` |
| `EXPLOITS`      | 利用漏洞                       | `APT_GROUP` / `CAMPAIGN` / `MALWARE` / `TOOL` | `CVE`                                                         |
| `ATTRIBUTED_TO` | 归因于                         | `APT_GROUP` / `CAMPAIGN` / `MALWARE`          | `COUNTRY` / `ORGANIZATION`                                    |
| `DISCOVERED_BY` | 被披露或发现                   | `CVE` / `MALWARE` / `TOOL` / `CAMPAIGN`       | `ORGANIZATION` / `PERSON`                                     |
| `HAS_BEHAVIOR`  | 具备某种行为模式               | `APT_GROUP` / `CAMPAIGN`                      | `BEHAVIOR_PATTERN` / `TECHNIQUE`                              |
| `MEMBER_OF`     | 人员属于团体或组织             | `PERSON`                                      | `APT_GROUP` / `ORGANIZATION`                                  |
| `CONTROLS`      | 主体控制对象                 | `PERSON` / `APT_GROUP` / `ORGANIZATION`     | `FINANCIAL_ACCOUNT` / `INFRASTRUCTURE` / `ORGANIZATION`       |
| `TRANSFERS_TO`  | 账户之间资金转移             | `FINANCIAL_ACCOUNT`                           | `FINANCIAL_ACCOUNT`                                           |
| `INSTANCE_OF`   | 具体实例属于泛指类别           | 同类实体                                      | 同类实体                                                       |
| `PRECEDES`      | 纯时间先后                   | `EVENT` / `CAMPAIGN` / `TECHNIQUE` / `BEHAVIOR_PATTERN` | 同左                                                         |

`RELATED_TO` 只能作为兜底关系。除非原文确实只表达弱关联且评测需要保留上下文，否则不要使用。

### 6.1 关系置信度

golden 关系不填写 `confidence`。`extraction_result.confidence` 是模型对候选结果的自评，不是人工黄金答案的置信度，两者不能直接比较或复制。

证据不足或标注员无法确认的关系不进入正式 `relations`，应先记录在 chunk 的 `note` 中并提交复核。不要用较低的人工分数把待定关系混入正例；如后续确实需要评测标注一致性，应另行设计标注状态和裁决流程，并同步修改 Schema、数据契约和评测算法。

---

## 7. 证据和字符位置

### 7.1 evidence_text

证据必须满足：

1. 来自当前 chunk 文本的连续片段，不能拼接多处句子。
2. 尽量短，但足够证明实体或关系。
3. 如果短片段重复出现，应扩大上下文，或准确填写 `char_start` / `char_end`。
4. 一条证据可以同时支撑实体和关系。

不允许：

1. 使用自己的总结代替原文。
2. 使用原文没有出现的实体或关系。
3. 为了补全图谱凭常识添加关系。

### 7.2 char_start / char_end

位置规则：

```text
chunk_text[char_start:char_end] == evidence_text
```

`char_start` 从 0 开始，包含起始字符；`char_end` 不包含结束字符。

如果工具自动计算位置，应优先使用工具结果。手工填写时必须复核切片是否等于 `evidence_text`。

---

## 8. 标注流程

1. 读取对应 `document.json`，确认 `doc_id`、`target_group`、`clean_text` 和来源信息。
2. 使用后端生成的 chunk 列表；后端暂不可用时，只能临时按 `${doc_id}_c001` 单 chunk 标注。
3. 先判断实体是否与威胁情报事实相关，排除只承担署名、编辑或页面维护角色的来源元信息主体。
4. 逐个 chunk 标注相关实体，先保证实体证据能回到原文；相关但没有关系的实体仍需保留。
5. 只在关系证据明确时标注关系，不为待定关系填写人工置信度。
6. `MEMBER_OF`、`CONTROLS`、`TRANSFERS_TO`、`INSTANCE_OF`、`PRECEDES` 不得根据共现、控制链或常识推断。
6. 检查关系两端实体是否在同一 chunk 的 `entities` 中存在。
7. 检查实体类型、关系类型和关系矩阵。
8. 用 `docs/schemas/golden.schema.json` 校验 JSON。
9. 在 `notes` 中写明统一排除口径、样本规模和限制，不夸大评测结论。

实体和关系应分开评测：相关但没有关系的实体属于实体正例；模型抽取无关实体计为实体假阳性，遗漏相关实体计为实体假阴性，无证据关系计为关系假阳性。

---

## 9. 常见问题

| 问题                       | 处理方式                                                                         |
| -------------------------- | -------------------------------------------------------------------------------- |
| 一个实体多次出现           | 选择最能证明实体身份的一处证据；必要时使用更长上下文。                           |
| 一个实体有多个别名         | 只写一个实体，其他名称放入 `aliases`。                                           |
| 实体相关但没有关系         | 仍写入 `entities`；不要为了形成关系而补写无证据关系。                            |
| 实体与威胁事件无关         | 不写入 `entities`；统一口径写顶层 `notes`，具体争议可写 chunk 的 `note`。         |
| 关系证据不足               | 不标注该关系，宁可少不要错。                                                     |
| 是否给关系填写人工置信度   | 不填写；golden 只保留确认正例，模型 `confidence` 只属于候选抽取结果。             |
| 实体类型不确定             | 先提交待确认，不要为了过 schema 随意填 `ORGANIZATION`。                          |
| 关系两端实体不在同一 chunk | 先不标该关系，或反馈切块/跨 chunk 评测需求给架构组。                             |
| 原文是推测语气             | 可以标实体；关系需谨慎，必要时在 `notes` 说明边界。                              |
| 需要记录 LLM 错误          | 错误样例和评测结果放在 evaluation 结果文件或报告中，不塞进 golden 标准答案字段。 |
