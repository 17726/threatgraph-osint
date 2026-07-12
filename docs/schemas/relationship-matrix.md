# 最小关系合法性矩阵

> 当前版本：`schema_version = "1.0"`
> 用途：限制 LLM 关系抽取结果，避免关系类型发散。
> 规则：不在表里的关系先进入 `extracted_relations`，但 `validation_status` 应标为 `invalid`，不能直接写入正式 `relations`。

## 实体类型

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

## 关系合法性

| relation_type   | 合法主体类型                        | 合法客体类型                                    | P0 说明                                                 |
| --------------- | ----------------------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| USES            | PERSON, ORGANIZATION, COUNTRY, APT_GROUP, CAMPAIGN | MALWARE, TOOL, TECHNIQUE, INFRASTRUCTURE | 主体使用恶意软件、工具、技术或基础设施                  |
| TARGETS         | APT_GROUP, CAMPAIGN, MALWARE        | COUNTRY, REGION, INDUSTRY, ORGANIZATION, PERSON, LOCATION | 攻击目标、行业、国家、组织、人员或地点                  |
| EXPLOITS        | PERSON, ORGANIZATION, COUNTRY, APT_GROUP, CAMPAIGN, MALWARE, TOOL | CVE | 利用漏洞                                                |
| ATTRIBUTED_TO   | APT_GROUP, CAMPAIGN, MALWARE        | COUNTRY, ORGANIZATION                           | 归因到国家或组织，必须有证据                            |
| AFFILIATED_WITH | APT_GROUP, ORGANIZATION              | APT_GROUP, ORGANIZATION, COUNTRY                | 无方向的关联、合作或联系，不表示成员或控制              |
| LOCATED_IN      | ORGANIZATION, PERSON, LOCATION, INFRASTRUCTURE, EVENT | COUNTRY, REGION, LOCATION | 地理位置                                                |
| HAPPENED_AT     | EVENT, CAMPAIGN                     | TIME                                            | 时间发生点                                              |
| PART_OF         | ORGANIZATION, EVENT, CAMPAIGN       | ORGANIZATION, CAMPAIGN, APT_GROUP                | 组织组成、事件属于活动、活动属于组织                    |
| LEADS_TO        | TECHNIQUE, BEHAVIOR_PATTERN, EVENT  | TECHNIQUE, BEHAVIOR_PATTERN, EVENT              | 攻击链步骤或行为递进                                    |
| DISCOVERED_BY   | CVE, MALWARE, TOOL, CAMPAIGN        | ORGANIZATION, PERSON                            | 发现者或披露者                                          |
| CAUSES          | CVE, TECHNIQUE, MALWARE             | EVENT, BEHAVIOR_PATTERN                         | 导致某类事件或行为                                      |
| HAS_BEHAVIOR    | APT_GROUP, CAMPAIGN                 | BEHAVIOR_PATTERN, TECHNIQUE                     | 组织或活动具备某种行为模式                              |
| MEMBER_OF       | PERSON                              | APT_GROUP, ORGANIZATION                          | 人员明确属于团体或组织                                  |
| CONTROLS        | PERSON, APT_GROUP, ORGANIZATION     | FINANCIAL_ACCOUNT, INFRASTRUCTURE, ORGANIZATION | 主体明确控制、管理或支配对象                            |
| TRANSFERS_TO    | FINANCIAL_ACCOUNT                   | FINANCIAL_ACCOUNT                               | 账户或钱包之间明确的资金转移方向                       |
| INSTANCE_OF     | ORGANIZATION, PERSON, LOCATION, INFRASTRUCTURE | ORGANIZATION, PERSON, LOCATION, INFRASTRUCTURE | 同类具体实例与泛指类别                                  |
| PRECEDES        | EVENT, CAMPAIGN, TECHNIQUE, BEHAVIOR_PATTERN | EVENT, CAMPAIGN, TECHNIQUE, BEHAVIOR_PATTERN | 纯时间先后，不表示因果                                  |
| RELATED_TO      | 任意                                | 任意                                            | 兜底关系，只允许人工确认或报告展示，不建议 LLM 默认输出 |

### 合法类型配对

上表的主体和客体列用于概览，实际校验使用以下精确配对；未列出的组合均非法：

```text
USES：
  PERSON / ORGANIZATION / COUNTRY / APT_GROUP / CAMPAIGN
    -> MALWARE / TOOL / TECHNIQUE / INFRASTRUCTURE

TARGETS：
  APT_GROUP / CAMPAIGN / MALWARE
    -> COUNTRY / REGION / INDUSTRY / ORGANIZATION / PERSON / LOCATION

EXPLOITS：
  PERSON / ORGANIZATION / COUNTRY / APT_GROUP / CAMPAIGN / MALWARE / TOOL
    -> CVE

PART_OF：
  ORGANIZATION -> ORGANIZATION / APT_GROUP
  EVENT -> CAMPAIGN
  CAMPAIGN -> APT_GROUP

INSTANCE_OF：
  ORGANIZATION -> ORGANIZATION
  PERSON -> PERSON
  LOCATION -> LOCATION
  INFRASTRUCTURE -> INFRASTRUCTURE
```

## 校验策略

1. LLM 输出的关系先进入 `extracted_relations`。
2. 后端按本矩阵校验 `head_type + relation_type + tail_type`。
3. 合法关系可进入归一化流程，非法关系保留为候选并写明 `validation_errors`。
4. `RELATED_TO` 不作为默认关系。除非原文关系不清晰但需要保留上下文，否则不要使用。
5. `ATTRIBUTED_TO`、`AFFILIATED_WITH`、`CAUSES` 必须有强证据，不能只凭模型推断。
6. `MEMBER_OF`、`CONTROLS`、`TRANSFERS_TO`、`INSTANCE_OF`、`PRECEDES` 只能在原文明确表达时标注，不能根据共现或其他关系推断。
7. 除 `RELATED_TO` 外，关系必须满足矩阵中列出的合法 `(head_type, tail_type)` 配对；不能将主体集合和客体集合任意组合。
