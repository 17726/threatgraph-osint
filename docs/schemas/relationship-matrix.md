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
TARGET
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
| USES            | APT_GROUP, CAMPAIGN                 | MALWARE, TOOL, TECHNIQUE, CVE                   | 组织或攻击活动使用工具、恶意软件、技术或漏洞            |
| TARGETS         | APT_GROUP, CAMPAIGN, MALWARE        | TARGET, COUNTRY, REGION, INDUSTRY, ORGANIZATION | 攻击目标、行业、国家或组织                              |
| EXPLOITS        | APT_GROUP, CAMPAIGN, MALWARE, TOOL  | CVE                                             | 利用漏洞                                                |
| ATTRIBUTED_TO   | APT_GROUP, CAMPAIGN, MALWARE        | COUNTRY, ORGANIZATION                           | 归因到国家或组织，必须有证据                            |
| AFFILIATED_WITH | APT_GROUP, ORGANIZATION, PERSON     | APT_GROUP, ORGANIZATION, COUNTRY                | 关联、隶属或协作关系                                    |
| LOCATED_IN      | ORGANIZATION, PERSON, TARGET, EVENT | COUNTRY, REGION                                 | 地理位置                                                |
| HAPPENED_AT     | EVENT, CAMPAIGN                     | TIME                                            | 时间发生点                                              |
| PART_OF         | EVENT, CAMPAIGN                     | CAMPAIGN, APT_GROUP                             | 事件属于活动，活动属于组织                              |
| LEADS_TO        | TECHNIQUE, BEHAVIOR_PATTERN, EVENT  | TECHNIQUE, BEHAVIOR_PATTERN, EVENT              | 攻击链步骤或行为递进                                    |
| DISCOVERED_BY   | CVE, MALWARE, TOOL, CAMPAIGN        | ORGANIZATION, PERSON                            | 发现者或披露者                                          |
| CAUSES          | CVE, TECHNIQUE, MALWARE             | EVENT, BEHAVIOR_PATTERN                         | 导致某类事件或行为                                      |
| HAS_BEHAVIOR    | APT_GROUP, CAMPAIGN                 | BEHAVIOR_PATTERN, TECHNIQUE                     | 组织或活动具备某种行为模式                              |
| RELATED_TO      | 任意                                | 任意                                            | 兜底关系，只允许人工确认或报告展示，不建议 LLM 默认输出 |

## 校验策略

1. LLM 输出的关系先进入 `extracted_relations`。
2. 后端按本矩阵校验 `head_type + relation_type + tail_type`。
3. 合法关系可进入归一化流程，非法关系保留为候选并写明 `validation_errors`。
4. `RELATED_TO` 不作为默认关系。除非原文关系不清晰但需要保留上下文，否则不要使用。
5. `ATTRIBUTED_TO`、`AFFILIATED_WITH`、`CAUSES` 必须有强证据，不能只凭模型推断。
