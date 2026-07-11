# P0 实体与关系本体设计

## 目标

在不引入完整 STIX 两层身份模型的前提下，稳定区分具体实体、泛指目标类别、行业、地理位置和攻击基础设施，并补齐课程要求中的事件先后关系。

## 核心原则

1. 每个文本实体只标注一个主类型。
2. 具体命名实体优先使用具体类型，不因其遭到攻击而改标为 `TARGET`。
3. `TARGET` 仅表示原文明确出现、无法指向具体命名实体的泛指目标类别。
4. 只有原文明确出现行业时才标注 `INDUSTRY`，不根据具体机构自动向上推导行业。
5. 原文同时出现具体对象和泛指类别时，两者都保留，并用 `INSTANCE_OF` 表达层级。
6. `PART_OF` 只表示组成或结构隶属，不承担类别归属和行业归属。

## 实体类型调整

新增：

```text
LOCATION
INFRASTRUCTURE
```

边界：

| 类型 | 定义 | 示例 |
| --- | --- | --- |
| `ORGANIZATION` | 具体、可识别且具有治理结构的机构 | 招商银行、Microsoft、某政府部门 |
| `PERSON` | 具体自然人 | 张三、某具名研究员 |
| `TARGET` | 原文中的泛指目标类别 | 金融机构、外交人员、政府机构群体 |
| `INDUSTRY` | 行业或经济活动领域 | 金融业、能源、制造业 |
| `COUNTRY` | 国家 | Ukraine |
| `REGION` | 地理区域或冲突区域 | Eastern Europe、Donbas |
| `LOCATION` | 军事基地、机场、设施或具体地点 | Ramstein Air Base |
| `INFRASTRUCTURE` | 域名、IP、C2 地址等攻击基础设施 | cdnverify[.]net、1.2.3.4 |

## 关系类型调整

新增：

```text
PRECEDES
INSTANCE_OF
IN_INDUSTRY
```

最小合法方向：

| 关系 | 主体类型 | 客体类型 | 含义 |
| --- | --- | --- | --- |
| `PRECEDES` | `EVENT`, `CAMPAIGN` | `EVENT`, `CAMPAIGN` | 主体事件或活动早于客体 |
| `INSTANCE_OF` | `ORGANIZATION`, `PERSON`, `COUNTRY`, `REGION`, `LOCATION` | `TARGET` | 具体对象是泛指目标类别的实例 |
| `IN_INDUSTRY` | `ORGANIZATION`, `TARGET` | `INDUSTRY` | 具体机构或目标类别属于某行业 |

同步调整现有矩阵：

1. `USES` 允许 `MALWARE` 作为主体，允许 `INFRASTRUCTURE` 作为客体。
2. `TARGETS` 允许 `LOCATION`、`INFRASTRUCTURE` 作为客体。
3. `ATTRIBUTED_TO` 允许 `APT_GROUP` 作为客体。
4. `DISCOVERED_BY` 保持“被发现对象 -> 发现者”的方向。
5. `PART_OF` 保持 `EVENT/CAMPAIGN -> CAMPAIGN/APT_GROUP`，APT 组织之间使用 `AFFILIATED_WITH`。

## 混合表达示例

原文：`APT28 攻击了招商银行以及其他金融机构。`

```text
APT28       APT_GROUP
招商银行    ORGANIZATION
金融机构    TARGET

APT28 TARGETS 招商银行
APT28 TARGETS 金融机构
招商银行 INSTANCE_OF 金融机构
```

只有原文进一步明确提到金融业时，才增加：

```text
金融业 INDUSTRY
招商银行 IN_INDUSTRY 金融业
金融机构 IN_INDUSTRY 金融业
```

## 数据与评测约束

1. 不根据常识补充原文未出现的行业、目标类别或具体机构。
2. 枚举并列项必须拆成原子实体，例如制造业、农业、物理安全分别标注。
3. Golden Schema、Extraction Schema、Graph Schema、Prompt、关系矩阵和后端校验必须同步。
4. 所有正式 golden 必须同时通过 JSON Schema、关系矩阵、关系端点和证据位置检查。
5. 历史数据中的域名/IP 从 `TOOL` 迁移为 `INFRASTRUCTURE`；方向写反或不符合矩阵的关系必须修正。

## 非目标

1. P0 不引入统一 `IDENTITY + identity_class + sectors` 两层结构。
2. P0 不细分 `DOMAIN`、`IP_ADDRESS`、`URL`、`C2_SERVER`。
3. P0 不根据外部知识库自动补全行业层级；后续 enrichment 可以在候选层完成。
