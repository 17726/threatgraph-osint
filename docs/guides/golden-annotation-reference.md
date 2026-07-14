# 黄金集标注参考手册

> 适用对象：QA 组人工制作 `golden.json`。正式契约以 `docs/schemas/golden.schema.json`、`docs/data-contract.md` 和 `data/examples/golden.apt28.thn.beardshell.example.json` 为准。

---

## 1. 基本定位

`golden.json` 是人工标准答案，用来评测 LLM 候选抽取结果，不是 LLM 输出，也不是最终图谱快照。

正式 golden 应当是在当前标注范围和规则下可直接用于评测的完整正确答案。`entities` 和 `relations` 只放人工确认的正例；待确认项、被排除项和 LLM 错误样例不混入标准答案。

`chunk_id` 由后端切块生成；后端切块不可用时，临时使用 `${doc_id}_c001` 单 chunk 约定。

建议文件位置：

```text
data/golden/golden-<language>-<doc_id_1>+<doc_id_2>+...-<schema_version>-<golden_version>.json
```

示例：

```text
data/golden/golden-en-apt28_080-1.0-1.0.json
data/golden/golden-zh-kimsuky_001-1.0-1.0.json
```

多文档 Golden 按顶层 `doc_ids` 的字典序生成文件名。例如 `doc_ids` 为
`["apt28_081", "apt28_080"]` 时，文件名为
`golden-en-apt28_080+apt28_081-1.0-1.0.json`。每个 ID 单独安全化后再使用 `+` 连接。

`data/evaluation/` 只存评测结果；历史迁移材料或旧格式文件不要作为正式 golden 使用，需要复查时放在 `data/raw/<collector>/`。

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
| `schema_version` | 使用两段式数字版本，例如 `1.0`。                                                               |
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

常用实体类型表：

| 类型 | 适用对象 | 常见边界与示例 |
| --- | --- | --- |
| `APT_GROUP` | APT28、Lazarus、Kimsuky、KONNI 等威胁组织或攻击团伙。 | 统一承载 APT 组织和犯罪团伙。 |
| `ORGANIZATION` | 安全厂商、政府机构、受害组织、研究机构、公司和服务提供商。 | 只有组织或机构才使用；仿冒品牌不自动是实际攻击目标。 |
| `PERSON` | 明确指向的研究人员、受害者、攻击者或组织成员。 | 纯来源元信息主体不写入 golden。 |
| `MALWARE` | 恶意软件、后门、木马、恶意植入物、恶意载荷家族或明确的恶意样本。 | 普通文档、脚本、日志和临时文件不是自动的 `MALWARE`。 |
| `TOOL` | PowerShell、certutil.exe、BITSAdmin、合法管理工具、协议、API、系统服务或软件工具。 | 域名、IP、URL、C2、VPS 优先使用 `INFRASTRUCTURE`。 |
| `CVE` | 标准 CVE 编号，例如 `CVE-2021-44228`。 | 只标注规范 CVE 标识。 |
| `TECHNIQUE` | 钓鱼邮件、DLL 侧加载、XSS、凭据窃取、进程注入、数据擦除等攻击手法。 | 当前无专门渠道类型时，短信和短链接可统一标为技术。 |
| `INFRASTRUCTURE` | 域名、IP、URL、C2 地址、邮箱地址、VPS、服务器或其他攻击网络资产。 | 不要将 C2、VPS、域名或 IP 标为 `TOOL`。 |
| `LOCATION` | 具体地点、军事基地、机场、建筑、设施或物理位置。 | 国家和地区分别使用 `COUNTRY`、`REGION`。 |
| `FINANCIAL_ACCOUNT` | 银行账户、支付账户、加密货币钱包或其他资金账户。 | 加密货币行业或资产类别不是账户。 |
| `COUNTRY` | 国家或明确的国家级政治实体，例如韩国、朝鲜、日本。 | IP 所在国家不自动等于组织所在地。 |
| `REGION` | 地区、时区覆盖区域或国家以下的地理区域。 | 时区推测不能直接断言组织位置。 |
| `INDUSTRY` | 行业、产业或泛化的受害类别，例如金融业、加密货币行业。 | 具体公司使用 `ORGANIZATION`。 |
| `TIME` | 日期、时间、时间段、年份、月份或明确的活动时间点。 | 样本签名时间不自动等于攻击活动时间。 |
| `EVENT` | 单次攻击事件、漏洞事件、数据泄露事件或一次性事件。 | 可通过 `HAPPENED_AT` 关联时间。 |
| `CAMPAIGN` | 系列攻击活动、持续行动或共同目标/工具/主体的活动集合。 | 不要无说明地合并不同时间或不同主体的活动。 |
| `BEHAVIOR_PATTERN` | 重复行为模式、攻击流程模式或高层行为特征。 | 用于概括行为模式，不替代具体技术。 |

实体类型边界：

1. `TOOL` 表示可被使用的工具、软件、协议、API 或服务；`TECHNIQUE` 表示做事的方法；`INFRASTRUCTURE` 表示承载通信、投递或控制的网络资产。
2. 操作系统、平台、POS 系统、文件工件、进程、邮箱账号、哈希和 IOC 若没有契约中明确的类型，不得为了通过 Schema 随意标成 `ORGANIZATION` 或 `TOOL`。
3. 仿冒品牌、诱饵主题和被提及组织可以作为实体保留，但不因出现于攻击文档就自动建立 `TARGETS` 关系。
4. 当前枚举没有合适类型时，记录为待复核或在 chunk `note` 中说明，不擅自使用语义明显不匹配的类型。

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

最小关系矩阵以 `docs/schemas/relationship-matrix.md` 为准。常用关系表覆盖当前 Schema 的全部关系类型；实际标注还必须满足矩阵中的精确类型配对。

| 关系 | 含义 | 常见主体 | 常见客体 | 标注注意事项 |
| --- | --- | --- | --- | --- |
| `USES` | 主体使用恶意软件、工具、技术或基础设施。 | `PERSON` / `ORGANIZATION` / `COUNTRY` / `APT_GROUP` / `CAMPAIGN` | `MALWARE` / `TOOL` / `TECHNIQUE` / `INFRASTRUCTURE` | 必须有使用、采用、投递或调用的明确证据。 |
| `TARGETS` | 主体攻击、针对或选择某对象作为目标。 | `APT_GROUP` / `CAMPAIGN` / `MALWARE` | `COUNTRY` / `REGION` / `INDUSTRY` / `ORGANIZATION` / `PERSON` / `LOCATION` | 仿冒品牌、邮件主题和诱饵对象不自动是实际攻击目标。 |
| `EXPLOITS` | 主体利用漏洞。 | `PERSON` / `ORGANIZATION` / `COUNTRY` / `APT_GROUP` / `CAMPAIGN` / `MALWARE` / `TOOL` | `CVE` | 必须有利用漏洞的明确证据。 |
| `ATTRIBUTED_TO` | 威胁主体、活动或恶意软件被归因于国家或组织。 | `APT_GROUP` / `CAMPAIGN` / `MALWARE` | `COUNTRY` / `ORGANIZATION` | “相关”“疑似关联”不足以支持归因。 |
| `AFFILIATED_WITH` | 两个组织、团体或国家之间存在关联、合作或联系。 | `APT_GROUP` / `ORGANIZATION` | `APT_GROUP` / `ORGANIZATION` / `COUNTRY` | 不表示成员、控制、组成或同一组织。 |
| `LOCATED_IN` | 主体位于某国家、地区或具体地点。 | `ORGANIZATION` / `PERSON` / `LOCATION` / `INFRASTRUCTURE` / `EVENT` | `COUNTRY` / `REGION` / `LOCATION` | IP 所在地、活动时区和攻击者推测位置不自动等于组织所在地。 |
| `HAPPENED_AT` | 事件或活动发生在某时间。 | `EVENT` / `CAMPAIGN` | `TIME` | 样本签名时间、文件创建时间和攻击发生时间不能混用。 |
| `PART_OF` | 组织、事件或活动属于更大的组织或活动。 | `ORGANIZATION` / `EVENT` / `CAMPAIGN` | `ORGANIZATION` / `CAMPAIGN` / `APT_GROUP` | `CAMPAIGN -> PART_OF -> APT_GROUP`；不表示人员成员或实例分类。 |
| `LEADS_TO` | 技术、行为或事件在攻击链中导致后续技术、行为或事件。 | `TECHNIQUE` / `BEHAVIOR_PATTERN` / `EVENT` | `TECHNIQUE` / `BEHAVIOR_PATTERN` / `EVENT` | 不能只依据文章叙述顺序推断。 |
| `RELATED_TO` | 两个对象之间存在无法用更精确关系表达的弱关联。 | 任意 | 任意 | 仅作为人工确认的兜底关系；有更精确关系时不得使用。 |
| `DISCOVERED_BY` | 漏洞、恶意软件、工具或活动被组织或人员发现、披露或分析。 | `CVE` / `MALWARE` / `TOOL` / `CAMPAIGN` | `ORGANIZATION` / `PERSON` | 厂商归因与发现/披露不同，不能混用。 |
| `CAUSES` | 漏洞、技术或恶意软件导致某事件或行为。 | `CVE` / `TECHNIQUE` / `MALWARE` | `EVENT` / `BEHAVIOR_PATTERN` | 共同出现不等于因果。 |
| `HAS_BEHAVIOR` | 组织或活动具有某种行为模式或技术行为。 | `APT_GROUP` / `CAMPAIGN` | `BEHAVIOR_PATTERN` / `TECHNIQUE` | 高层行为使用 `BEHAVIOR_PATTERN`，具体方法使用 `TECHNIQUE`。 |
| `MEMBER_OF` | 人员明确属于某团体或组织。 | `PERSON` | `APT_GROUP` / `ORGANIZATION` | 只有原文明确表达成员、隶属或归属时才标注。 |
| `CONTROLS` | 主体明确控制、管理或支配某对象。 | `PERSON` / `APT_GROUP` / `ORGANIZATION` | `FINANCIAL_ACCOUNT` / `INFRASTRUCTURE` / `ORGANIZATION` | 不能从 `USES`、访问、关联或共现推断控制。 |
| `TRANSFERS_TO` | 一个资金账户或钱包向另一个账户或钱包转账。 | `FINANCIAL_ACCOUNT` | `FINANCIAL_ACCOUNT` | 必须有明确的资金转移方向。 |
| `INSTANCE_OF` | 具体实例属于同类型的泛指类别。 | `ORGANIZATION` / `PERSON` / `LOCATION` / `INFRASTRUCTURE` | 对应同类型实体 | 只有原文明确表达“属于某类”才标注。 |
| `PRECEDES` | 一个事件、活动、技术或行为模式在时间上先于另一个对象。 | `EVENT` / `CAMPAIGN` / `TECHNIQUE` / `BEHAVIOR_PATTERN` | 同左 | 只表达时间先后，不表达因果、组成或使用。 |

关系判断边界：

1. 原文中的推测、可能、大概或关联分析可以支持实体，但不自动支持确定的组织归因、地理位置或控制关系。
2. 组织、活动、恶意软件、工具和攻击者之间不能仅凭上下文共现建立 `USES`、`CONTROLS`、`MEMBER_OF` 或 `ATTRIBUTED_TO`。
3. `DISCOVERED_BY` 表示发现、披露或分析；安全厂商“将某活动归因于某组织”是不同语义，当前矩阵没有专门的厂商归因关系时不得改变方向强行使用 `ATTRIBUTED_TO`。
4. 关系证据应尽量包含明确的主体和客体；如果只能依赖跨句代词或外部知识，应缩小关系范围、补充 chunk `note`，或不进入正式 `relations`。

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
7. 检查关系两端实体是否在同一 chunk 的 `entities` 中存在。
8. 检查实体类型、关系类型和关系矩阵。
9. 用 `docs/schemas/golden.schema.json` 校验 JSON。
10. 在 `notes` 中写明统一排除口径、样本规模和限制，不夸大评测结论。
11. 复核推测语气：可以保留“可能位于某地区”对应的实体，但不要直接建立确定的组织位置、归因或控制关系。
12. 复核目标语义：品牌、诱饵主题、仿冒对象和邮件主题不等于实际受害者；只有原文明确表达攻击或针对时才建立 `TARGETS`。
13. 复核实体边界：域名、IP、URL、C2 和 VPS 优先归为 `INFRASTRUCTURE`；工具、技术、恶意软件和普通文件工件不能混用。
14. 如果当前枚举没有合适类型，不要为了通过 Schema 随意标为 `ORGANIZATION` 或 `TOOL`；应记录待复核项或在 chunk `note` 中说明排除。

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
| 仿冒品牌或诱饵主题          | 可以保留相关组织实体，但不自动建立 `TARGETS`；除非原文明确说该组织是实际受害者。 |
| 域名、IP、C2 或 VPS          | 默认使用 `INFRASTRUCTURE`，不要标为 `TOOL`；关系仍需原文支持。                  |
| 当前枚举没有合适实体类型     | 不要强行选择近似类型；记录待复核或明确排除，必要时提交 Schema 变更建议。         |
| 厂商归因与发现/披露           | `DISCOVERED_BY` 只表示发现、披露或分析；厂商归因语义不能改变关系方向硬套 `ATTRIBUTED_TO`。 |
| 攻击者位置与组织位置         | IP 地理位置、活动时区或匿名攻击者推断不能自动转成 APT 组织的 `LOCATED_IN`。       |
| 需要记录 LLM 错误          | 错误样例和评测结果放在 evaluation 结果文件或报告中，不塞进 golden 标准答案字段。 |
