# 已确认的本体与犯罪网络建模决策

> 日期：2026-07-12
> 状态：本轮讨论已确认，契约同步与数据验收待执行
> 用途：记录 PR #22 讨论中已经确认的建模结论，作为后续 Schema、Prompt、后端和测试同步依据。

## 1. 威胁主体模型

`APT_GROUP` 作为项目统一的威胁团体类型，包含：

- APT 组织
- 犯罪团伙

现有 APT28、Lazarus、Kimsuky 继续使用 `APT_GROUP`，不新增以下实体类型或字段：

```text
THREAT_ACTOR
INTRUSION_SET
THREAT_GROUP
CRIMINAL_GROUP
threat_group_types
threat_actor_roles
```

该定义不表示所有 `APT_GROUP` 都是同一种现实组织，只表示项目统一使用该实体类型承载威胁团体。

## 2. 实体类型调整

新增实体类型：

```text
INFRASTRUCTURE
LOCATION
FINANCIAL_ACCOUNT
```

含义：

```text
INFRASTRUCTURE：域名、IP、URL、C2 地址或服务器等攻击基础设施
LOCATION：军事基地、机场、具体设施或具体地点
FINANCIAL_ACCOUNT：银行账户、支付账户、加密货币钱包等资金账户
```

删除实体类型：

```text
TARGET
```

攻击目标不再使用独立实体类型，改用原有语义类型表达，例如：

```text
ORGANIZATION
PERSON
COUNTRY
REGION
INDUSTRY
LOCATION
```

目标角色由 `TARGETS` 关系表达。

## 3. 字段调整

不新增实体专属字段：

```text
threat_group_types
threat_actor_roles
financial_account_type
```

也不新增资金关系字段：

```text
fund_flow_purpose
```

现有业务字段 `target_group` 保留，用于文档、报告、行为模式和威胁评估的业务分组，不等同于实体类型。

## 4. 新增关系

新增：

```text
MEMBER_OF
CONTROLS
TRANSFERS_TO
INSTANCE_OF
PRECEDES
```

### 4.1 MEMBER_OF

表示人员属于某个团体或组织：

```text
PERSON -> APT_GROUP / ORGANIZATION
```

示例：

```text
某人员 MEMBER_OF 某 APT_GROUP
某人员 MEMBER_OF 某组织
```

只有原文明确表达成员、隶属或归属时才标注，不因人员和团体同时出现而推断。

组织与组织之间的组成关系不使用 `MEMBER_OF`，使用 `PART_OF`。

### 4.2 CONTROLS

表示主体实际控制、管理或支配对象：

主体：

```text
PERSON
APT_GROUP
ORGANIZATION
```

客体：

```text
FINANCIAL_ACCOUNT
INFRASTRUCTURE
ORGANIZATION
```

示例：

```text
PERSON CONTROLS FINANCIAL_ACCOUNT
APT_GROUP CONTROLS FINANCIAL_ACCOUNT
ORGANIZATION CONTROLS INFRASTRUCTURE
```

`CONTROLS` 与 `USES` 不合并。不能根据 `USES` 推断 `CONTROLS`。

### 4.3 TRANSFERS_TO

表示账户或钱包之间明确的资金转移方向：

```text
FINANCIAL_ACCOUNT -> FINANCIAL_ACCOUNT
```

只有原文明确出现账户或钱包之间的资金转移方向时才标注，不根据控制、关联或使用关系推断。

### 4.4 INSTANCE_OF

表示同类实体中的具体实例与泛指类别：

```text
ORGANIZATION -> ORGANIZATION
PERSON -> PERSON
LOCATION -> LOCATION
INFRASTRUCTURE -> INFRASTRUCTURE
```

示例：

```text
招商银行 INSTANCE_OF 金融机构
```

只有原文明确表达实例与类别关系时才标注，不根据常识推断。

### 4.5 PRECEDES

表示纯时间先后，不表示因果：

```text
EVENT / CAMPAIGN / TECHNIQUE / BEHAVIOR_PATTERN
    -> EVENT / CAMPAIGN / TECHNIQUE / BEHAVIOR_PATTERN
```

`LEADS_TO` 继续表示因果或行为推进。

## 5. 既有关系调整

### 5.1 PART_OF

表示部分与整体关系：

```text
ORGANIZATION -> APT_GROUP / ORGANIZATION
EVENT -> CAMPAIGN
CAMPAIGN -> APT_GROUP
```

示例：

```text
某部门 PART_OF 某公司
某事件 PART_OF 某攻击活动
某攻击活动 PART_OF 某 APT_GROUP
```

`PART_OF` 不表示实例分类，也不替代人员成员关系。

### 5.2 AFFILIATED_WITH

保留并限定为无方向、对称的关联关系：

```text
APT_GROUP / ORGANIZATION
    AFFILIATED_WITH
APT_GROUP / ORGANIZATION / COUNTRY
```

它仅表示存在关联、合作或联系，不表示：

```text
成员关系
组织从属
组成关系
控制关系
```

不允许 `PERSON` 作为该关系主体。人员归属使用 `MEMBER_OF`。

### 5.3 CAMPAIGN 与 APT_GROUP

攻击活动与威胁团体使用：

```text
CAMPAIGN PART_OF APT_GROUP
```

替代原来的：

```text
APT_GROUP RELATED_TO CAMPAIGN
```

## 6. USES 与 EXPLOITS

### 6.1 USES

主体类型：

```text
PERSON
ORGANIZATION
COUNTRY
APT_GROUP
CAMPAIGN
```

客体类型：

```text
MALWARE
TOOL
TECHNIQUE
INFRASTRUCTURE
```

示例：

```text
APT_GROUP USES TECHNIQUE
APT_GROUP USES MALWARE
ORGANIZATION USES INFRASTRUCTURE
```

不允许 `USES -> CVE`。

只有原文明确表达使用、利用或采用时才标注。

### 6.2 EXPLOITS

主体类型为 `USES` 主体类型的全部类型，并额外允许：

```text
MALWARE
TOOL
```

即：

```text
PERSON
ORGANIZATION
COUNTRY
APT_GROUP
CAMPAIGN
MALWARE
TOOL
```

客体类型固定为：

```text
CVE
```

只有原文明确表达利用漏洞、CVE 或弱点时才标注。

## 7. 其他既有关系

本轮未讨论、未修改且与上述决策不冲突的实体、字段和关系全部保留。

包括：

```text
RELATED_TO
LEADS_TO
HAS_BEHAVIOR
ATTRIBUTED_TO
DISCOVERED_BY
CAUSES
LOCATED_IN
HAPPENED_AT
```

其中 `RELATED_TO` 仅作为无法进一步细化语义时的一般关联关系。

## 8. 课程 3.b 最小能力

本轮确认的最小关系链为：

```text
PERSON MEMBER_OF APT_GROUP
APT_GROUP AFFILIATED_WITH APT_GROUP
APT_GROUP CONTROLS FINANCIAL_ACCOUNT
PERSON CONTROLS FINANCIAL_ACCOUNT
FINANCIAL_ACCOUNT TRANSFERS_TO FINANCIAL_ACCOUNT
APT_GROUP USES TECHNIQUE
```

对应课程要求：

```text
MEMBER_OF：成员关联
AFFILIATED_WITH：团体关联
CONTROLS：团体或人员与账户的控制关系
TRANSFERS_TO：账户资金流向
USES -> TECHNIQUE：作案手法
```

该模型在 Schema 能力层面覆盖课程 3.b 的最小要求。实际验收仍必须有原文证据，不能使用空字段、mock 或 LLM 推断替代真实数据。

## 9. 证据边界

新增关系统一遵守以下规则：

```text
只记录原文明确表达的事实。
不根据共现推断关系。
不根据常识补充成员、控制或资金流。
事实关系与推断关系分开保存。
```

尤其需要人工核验：

```text
MEMBER_OF
CONTROLS
TRANSFERS_TO
INSTANCE_OF
PART_OF
AFFILIATED_WITH
```

## 10. 尚需执行的工作

以下不是本轮语义决策，而是将决策落地为最终架构的执行工作：

1. 将实体和关系调整同步到 JSON Schema。
2. 将最终关系矩阵同步到 `docs/schemas/relationship-matrix.md`。
3. 同步 `docs/data-contract.md` 和 `docs/prompts/extract-1.0.md`。
4. 迁移删除 `TARGET` 后受影响的 golden、示例和测试数据。
5. 增加 `INFRASTRUCTURE`、`LOCATION`、`FINANCIAL_ACCOUNT` 的示例。
6. 增加 `MEMBER_OF`、`CONTROLS`、`TRANSFERS_TO` 的真实证据样例。
7. 补充至少一组犯罪团伙成员关系、账户控制关系和账户转账关系的 QA 验收材料。
8. 验证后端关系合法性校验和前端类型展示。
