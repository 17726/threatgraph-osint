# 黄金集标注参考手册

> 适用于 `data/evaluation/golden.<lang>.<dataset>.json` 格式，契约格式见 `data/examples/golden.apt28.thn.beardshell.example.json`。

---

## 1. 文件顶层字段

| 字段 | 值 | 说明 |
|---|---|---|
| `schema_version` | `"1.0"` | **固定值**，不允许改 |
| `target_group` | `"APT28"` / `"Kimsuky"` / `"Lazarus"` | 本次标注目标组织 |
| `doc_ids` | `["apt28_001"]` | 该 golden 文件覆盖的文档 ID |
| `chunks` | [...] | 后端切块信息，标注时已填好，不需要改 |
| `entities` | [...] | **你要填的实体列表** |
| `relations` | [...] | **你要填的关系列表** |

---

## 2. entities 字段详解

```json
{
  "name": "APT28",
  "type": "APT_GROUP",
  "aliases": ["Fancy Bear", "Sofacy"],
  "chunk_id": "apt28_001_c001",
  "evidence_text": "APT28, Pawn Storm, Sofacy Group, Sednit或STRONTIUM",
  "char_start": 0,
  "char_end": 271,
  "canonical_id": "apt_group:apt28"
}
```

### name（实体标准名）
- **类型**：字符串，**任意填写**
- **填写规则**：选取文档中最通用的称呼
- **示例**：`"APT28"`（不写 `"Fancy Bear"`），`"Carberp"`，`"腾讯御见威胁情报中心"`

### type（实体类型）
- **类型**：字符串，**只能从下方列表选一个**
- **填写规则**：选最匹配的类型，不确定时填 `ORGANIZATION`

| 类型 | 中文含义 | 适用场景 |
|---|---|---|
| `APT_GROUP` | APT组织 | 高级持续性威胁组织、黑客团伙，如 APT28, Lazarus, Kimsuky, KONNI |
| `ORGANIZATION` | 组织机构 | 公司、机构、安全厂商、政府单位，如 腾讯御见, 奇安信, ESTsecurity, CERT-UA, 罗马尼亚外交部 |
| `PERSON` | 个人 | 个人姓名（中文报告中出现较少） |
| `MALWARE` | 恶意软件 | 木马、后门、病毒、恶意程序，如 Carberp, PowerRatankba, cdnver.dll, Ratankba |
| `TOOL` | 工具 | 软件工具、系统程序、协议、框架（非恶意），如 certutil.exe, PowerShell, KakaoTalk, rundll32.exe |
| `CVE` | 漏洞编号 | 标准 CVE 漏洞编号，如 CVE-2017-0199 |
| `TECHNIQUE` | 攻击技术 | 攻击手法、技术，如 钓鱼邮件, XSS, DLL侧加载 |
| `TARGET` | 攻击目标 | 攻击的目标行业/群体/机构类型，如 韩国政府, 加密货币交易所, 金融机构 |
| `COUNTRY` | 国家 | 国家名称，如 俄罗斯, 韩国, 朝鲜, 乌克兰 |
| `REGION` | 区域 | 地理区域（不常用），如 东亚, 东欧 |
| `INDUSTRY` | 行业 | 行业分类（不常用），如 金融业, 国防工业 |
| `TIME` | 时间 | 时间点或时间段（不常用） |
| `EVENT` | 攻击事件 | 单次攻击事件（不常用） |
| `CAMPAIGN` | 攻击活动 | 系列攻击活动（不常用） |
| `BEHAVIOR_PATTERN` | 行为模式 | 攻击行为模式（不常用） |

### aliases（别名列表）
- **类型**：字符串数组，**任意填写**
- **填写规则**：文档中提到的该实体其他名称，无别名填 `[]`
- **示例**：`["Fancy Bear", "Sofacy"]`，`["Computer Emergency Response Team of Ukraine"]`

### chunk_id（文档块 ID）
- **类型**：字符串，**固定值**，不需要填写
- **填写规则**：格式为 `{doc_id}_c001`，已预先填好

### evidence_text（证据文本）
- **类型**：字符串，**任意填写**
- **填写规则**：从原文中截取的连续短句，能证明该实体在文档中出现，必须**唯一命中**原文
- **示例**：`"APT28, Pawn Storm, Sofacy Group, Sednit或STRONTIUM"`

### char_start / char_end（字符起止位置）
- **类型**：整数，自动计算，不需要填写
- **填写规则**：`char_start = clean_text.find(evidence_text)`，`char_end = char_start + len(evidence_text)`，满足 `clean_text[char_start:char_end] == evidence_text`

### canonical_id（规范 ID）
- **类型**：字符串，**只能按下方 ID 规则填写**
- **填写规则**：`{类型前缀}:{英文小写名}`，不能随意编造

**ID 规则详解：**

| 类型 | ID 格式 | 示例 |
|---|---|---|
| `APT_GROUP` | `apt_group:{英文小写名}` | `apt_group:apt28` |
| `ORGANIZATION` | `organization:{英文小写名}` | `organization:tencent-yujian` |
| `PERSON` | `person:{英文小写名}` | |
| `MALWARE` | `malware:{英文小写名}` | `malware:carberp` |
| `TOOL` | `tool:{英文小写名}` | `tool:certutil-exe` |
| `CVE` | `cve:{小写编号}` | `cve:cve-2017-0199` |
| `TECHNIQUE` | `technique:{英文小写名}` | `technique:phishing-emails` |
| `TARGET` | `target:{英文小写名}` | `target:korean-government` |
| `COUNTRY` | `country:{英文小写名}` | `country:russia` |
| `REGION` | `region:{英文小写名}` | |
| `INDUSTRY` | `industry:{英文小写名}` | |
| `TIME` | `time:{英文小写名}` | |
| `EVENT` | `event:{英文小写名}` | |
| `CAMPAIGN` | `campaign:{英文小写名}` | |
| `BEHAVIOR_PATTERN` | `behavior:{英文小写名}` | |

**ID 命名规则：**
1. 小写字母，空格变连字符 `-`
2. 特殊字符保留（如 `cve-2017-0199` 中的 `-`）
3. `CVE` 格式固定为 `cve:cve-xxxx-xxxx`
4. 中文名翻译为英文（如 `罗马尼亚外交部` → `romanian-ministry-of-foreign-affairs`）
5. **同一个实体在不同文档中应使用相同的 `canonical_id`**

---

## 3. relations 字段详解

```json
{
  "source": "APT28",
  "source_type": "APT_GROUP",
  "relation_type": "USES",
  "target": "Carberp",
  "target_type": "MALWARE",
  "chunk_id": "apt28_001_c001",
  "evidence_text": "本次攻击中使用的木马为Carberp银行木马的变种",
  "char_start": 430,
  "char_end": 480
}
```

### source（关系主体名称）
- **类型**：字符串，**任意填写**
- **填写规则**：关系的发出者，**必须在本文件的 entities 列表中已存在**（name 完全一致）
- **示例**：`"APT28"`，`"Lazarus"`

### source_type（关系主体类型）
- **类型**：字符串，**只能从实体类型列表选**
- **填写规则**：与 source 对应的 type，**必须在本文件的 entities 列表中已存在**
- **示例**：`"APT_GROUP"`

### relation_type（关系类型）
- **类型**：字符串，**只能从下方列表选**
- **填写规则**：必须满足关系矩阵对 `(source_type, relation_type, target_type)` 的限制，否则校验不通过

| 关系类型 | 中文含义 | 允许主体类型（source_type） | 允许客体类型（target_type） |
|---|---|---|---|
| `USES` | 使用 | APT_GROUP, CAMPAIGN | MALWARE, TOOL, TECHNIQUE, CVE |
| `TARGETS` | 攻击目标（针对） | APT_GROUP, CAMPAIGN, MALWARE | TARGET, COUNTRY, REGION, INDUSTRY, ORGANIZATION |
| `EXPLOITS` | 利用漏洞 | APT_GROUP, CAMPAIGN, MALWARE, TOOL | CVE |
| `ATTRIBUTED_TO` | 归因于 | APT_GROUP, CAMPAIGN, MALWARE | COUNTRY, ORGANIZATION |
| `AFFILIATED_WITH` | 关联 | APT_GROUP, ORGANIZATION, PERSON | APT_GROUP, ORGANIZATION, COUNTRY |
| `LOCATED_IN` | 位于 | ORGANIZATION, PERSON, TARGET, EVENT | COUNTRY, REGION |
| `HAPPENED_AT` | 发生于 | EVENT, CAMPAIGN | TIME |
| `PART_OF` | 属于、组成部分 | EVENT, CAMPAIGN | CAMPAIGN, APT_GROUP |
| `LEADS_TO` | 导致、递进 | TECHNIQUE, BEHAVIOR_PATTERN, EVENT | TECHNIQUE, BEHAVIOR_PATTERN, EVENT |
| `DISCOVERED_BY` | 被...发现 | CVE, MALWARE, TOOL, CAMPAIGN | ORGANIZATION, PERSON |
| `CAUSES` | 引起 | CVE, TECHNIQUE, MALWARE | EVENT, BEHAVIOR_PATTERN |
| `HAS_BEHAVIOR` | 具备行为 | APT_GROUP, CAMPAIGN | BEHAVIOR_PATTERN, TECHNIQUE |
| `RELATED_TO` | 相关（兜底） | 任意 | 任意 |

### target（关系客体名称）
- **类型**：字符串，**任意填写**
- **填写规则**：关系的承受者，**必须在本文件的 entities 列表中已存在**（name 完全一致）
- **示例**：`"Carberp"`，`"韩国政府"`

### target_type（关系客体类型）
- **类型**：字符串，**只能从实体类型列表选**
- **填写规则**：与 target 对应的 type，**必须在本文件的 entities 列表中已存在**

### chunk_id（文档块 ID）
- **类型**：字符串，**固定值**，不需要填写

### evidence_text（证据文本）
- **类型**：字符串，**任意填写**
- **填写规则**：原文中支撑该关系存在的连续短句，必须**唯一命中**
- **注意**：可以和实体使用同一句 evidence_text

### char_start / char_end（字符起止位置）
- **类型**：整数，自动计算，不需要填写

---

## 4. 补充规则

### 4.1 该标什么，不该标什么

**应该标注：**
- 文档中明确提到的实体（APT组织名、恶意软件名、CVE编号、攻击手法、目标国家/行业、安全厂商等）
- 原文有明显证据支撑的关系

**不应该标注：**
- 没有出现在原文中的实体
- 凭自己知识推断的关系（原文没有明确说"APT28使用xxx"就不要标）
- `RELATED_TO`（作为兜底关系，尽量不要用）

### 4.2 证据文本选取原则

1. 必须从 `clean_text` 中连续截取，不能拼接
2. 尽量短但保证唯一命中（如果 "APT28" 出现多次，就多截几个字）
3. 一条 evidence_text 可以同时作为实体和关系的证据

### 4.3 char 位置规则

```text
char_start: evidence_text 在 clean_text 中的起始位置（包含，0-indexed）
char_end:   evidence_text 在 clean_text 中的结束位置（不包含，Python切片规则）
```

验证条件：`clean_text[char_start:char_end] == evidence_text`

> 标注时你不需要算这个，我帮你自动算。但你给的 evidence_text 必须是从原文连续截取的。

### 4.4 标注时的常见问题

| 问题 | 建议 |
|---|---|
| 一个实体在文档中出现多次 | 选第一次出现的位置截 evidence_text |
| 多个别名指向同一个实体 | 只标一个实体，别名放 aliases 数组 |
| 关系证据不足 | 不标，宁可少不要错 |
| 不知道用哪个 type | 优先选文档中明确定义的，不确定用 ORGANIZATION |
| canonical_id 怎么确定英文名 | 搜一下标准英文翻译，保持一致性 |
