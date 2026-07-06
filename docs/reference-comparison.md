# 开源项目对比草案

> 目的：为课程报告中的“开源参考项目对比”和“自研系统创新性”提供初始材料。  
> 状态：草案，后续由报告测试与答辩组继续补充截图、部署体验和细节验证。  
> 日期：2026-07-07

---

## 1. 对比结论

ThreatGraph-OSINT 不直接复刻某一个成熟 CTI 平台，而是面向课程第三题做一个轻量、可演示、可解释的闭环系统：

```text
多源采集 -> 清洗 -> LLM 抽取 -> SQLite 事实源 -> graph.json 导出
-> Neo4j 图查询增强 -> 行为分析 / MITRE 映射 / 候选推理 -> 报告
```

开源项目对比的重点不是证明“我们功能更多”，而是说明：

1. 我们借鉴成熟项目的数据建模、采集器、图谱查询和分析流程。
2. 我们把课程要求的 LLM 抽取、证据追溯、行为分析和可演示图谱闭环做成一条轻量链路。
3. 我们把 SQLite 作为可复现事实源，Neo4j 作为增强层，避免把图数据库当唯一事实源。

---

## 2. 推荐开发顺序

建议先做轻量对比，再搭 MVP。

```text
第 1 步：用 0.5-1 天完成架构借鉴对比
第 2 步：初始化 Docker / FastAPI / React / SQLite
第 3 步：用 mock 数据跑通采集 -> 图谱 -> 报告
第 4 步：边开发边补开源项目细节和创新点
```

原因：

1. 先轻量对比可以避免盲目设计接口。
2. 对比能帮助我们确定采集器、事件模型、证据追溯、图谱展示和报告结构。
3. 不建议等完整对比报告写完再开发，否则会拖慢 MVP。

---

## 3. 项目清单

| 项目 | 定位 | 可借鉴点 | 对本项目的启发 | 链接 |
| --- | --- | --- | --- | --- |
| OpenCTI | 开源威胁情报平台 | STIX 化建模、知识图谱、连接器、时间线、ATT&CK 映射 | 学习实体关系模型、连接器设计和图谱分析页面 | [GitHub](https://github.com/OpenCTI-Platform/opencti) / [官网](https://filigran.io/platform/opencti/) |
| MISP | 威胁情报共享平台 | Event、Attribute、Object、Tag、Galaxy、Feed 机制 | 学习 IOC、事件、标签和共享格式，不直接照搬其重型平台 | [GitHub](https://github.com/MISP/MISP) / [官网](https://www.misp-project.org/) |
| SpiderFoot | OSINT 自动化工具 | 模块化数据源、扫描任务、Web UI、CLI | 学习 P0/P1 采集器模型和 scan/run 状态设计 | [GitHub](https://github.com/smicallef/spiderfoot) |
| Maltego | 调查图谱和链接分析平台 | Transform、实体 pivot、交互式关系图 | 学习图谱交互和调查路径展示。注意：它主要是商业平台，不作为开源实现对标 | [官网](https://www.maltego.com/) |
| MITRE ATT&CK / STIX | 攻击技术知识库和机器可读格式 | ATT&CK 技术、战术、STIX 2.1 数据 | 作为 MITRE 映射和技术编号的标准来源 | [ATT&CK STIX](https://github.com/mitre-attack/attack-stix-data) / [MITRE CTI](https://github.com/mitre/cti) |
| GraphRAG | 基于图的 RAG / 文本到知识结构流程 | 从非结构化文本抽取图结构、社区摘要、图增强问答 | 学习 LLM 抽取和图结构辅助分析，但本项目优先做可控小图谱 | [GitHub](https://github.com/microsoft/graphrag) / [文档](https://microsoft.github.io/graphrag/) |
| TypeDB CTI | 基于 TypeDB 的 CTI / STIX Schema | 语义图数据库、强 schema、STIX 关系约束 | 学习更严格的数据模型和关系约束；不作为本项目主数据库 | [GitHub](https://github.com/typedb-osi/typedb-cti) / [用例](https://typedb.com/use-cases/cyber-threat-intelligence) |
| Harpoon | OSINT / 威胁情报 CLI 工具 | 插件式查询、API Key 管理、命令行工作流 | 学习轻量采集器和插件组织方式 | [GitHub](https://github.com/Te-k/harpoon) |
| GOSINT | 威胁情报收集与处理框架 | 结构化和非结构化情报收集、IOC 处理、标准化输出 | 学习采集、过滤、标准化、导出的流水线 | [GitHub](https://github.com/ciscocsirt/GOSINT) / [Cisco 介绍](https://blogs.cisco.com/security/open-source-threat-intel-gosint) |
| T-Pot | 多蜜罐平台 | 多种蜜罐、Elastic 可视化、攻击遥测采集 | 可作为“主动采集类数据源”参考，不纳入 P0 核心 | [GitHub](https://github.com/telekom-security/tpotce) |
| Cuckoo Sandbox | 恶意软件动态分析沙箱 | 自动运行样本、生成行为报告、IOC 和行为日志 | 可作为 P1/P2 enrichment 参考，不建议作为课程核心依赖 | [GitHub](https://github.com/cuckoosandbox/cuckoo) / [文档](https://cuckoo.readthedocs.io/en/latest/introduction/what/) |
| TheHive | 安全事件协同管理平台 | Case、Task、Observable、协作流程 | 学习“情报发现 -> 调查 -> 报告”的工作流组织 | [GitHub](https://github.com/TheHive-Project/TheHive) / [官网](https://strangebee.com/thehive/) |
| Yeti | DFIR / CTI 情报平台 | Observable、Threat Actor、Tag、上下文检索 | 学习“在哪见过这个 IOC/实体”的检索视角 | [GitHub](https://github.com/yeti-platform/yeti) |
| Cortex | Observable 分析引擎 | Analyzer、Responder、批量 observable enrichment | 学习分析器插件和外部服务集成方式 | [GitHub](https://github.com/TheHive-Project/Cortex) |

备注：

1. 用户早期列出的 `github.com/dtag-dev-sec/tpotce` 需要按当前主仓库修正为 `telekom-security/tpotce`。
2. 用户早期列出的 `github.com/cybermedi/GOSINT` 需要按已核验仓库修正为 `ciscocsirt/GOSINT`。
3. Maltego 主要作为成熟产品体验和交互设计参考，不作为开源代码参考。
4. Cuckoo 旧版仓库可参考行为报告结构，但不建议纳入核心运行链路。

---

## 4. 可学习的架构经验

### 4.1 采集器设计

参考项目：SpiderFoot、Harpoon、GOSINT、OpenCTI connectors。

可落到本项目：

```text
sources：来源配置
collector_type：采集器类型
collection_runs：采集运行记录
collected_items：采集到的原始条目
documents：进入事实源的正式文档
```

这样能把“外部采集过程”和“系统事实源”分开。采集失败、重复、解析失败不会直接污染正式图谱。

### 4.2 数据模型和证据追溯

参考项目：OpenCTI、MISP、MITRE ATT&CK / STIX、TypeDB CTI。

可落到本项目：

```text
entity：实体
relation：关系
evidence：证据
source：来源
confidence：置信度
tag / technique / tactic：标签、技术和战术维度
```

我们的轻量版本不完整实现 STIX，但要保留 STIX 风格的可追溯思想：每个实体、关系、行为模式和报告结论都能回到证据。

### 4.3 图谱查询和调查体验

参考项目：OpenCTI、Maltego、Yeti、TypeDB CTI、Neo4j。

可落到本项目：

```text
按组织展开图谱
按实体查看上下文
按路径追踪关联关系
按攻击阶段筛选行为
按证据回看原文
```

P0 使用 SQLite BFS 兜底。P1 使用 Neo4j/Cypher 展示多跳路径和组合查询。

### 4.4 分析器和增强服务

参考项目：Cortex、Cuckoo、T-Pot。

可落到本项目：

```text
analysis service：行为分析、MITRE 映射、推理
enrichment service：后续可接入 IOC、沙箱、蜜罐、外部 API
```

课程 MVP 不需要真的接入沙箱或蜜罐，但可以在报告里说明系统架构支持后续 enrichment。

---

## 5. 本项目创新点草案

可以在最终报告中展开为以下几点：

1. 面向课程场景做轻量闭环，不依赖重型 CTI 平台也能完成采集、抽取、图谱、分析和报告。
2. SQLite 作为唯一事实源，graph.json 作为导出和 mock，Neo4j 作为增强层，兼顾复现性和图数据库演示。
3. LLM 抽取结果先进入候选层，再归一化为 canonical graph，避免直接污染图数据库。
4. 行为分析、MITRE 映射、候选推理和报告都保留证据引用，便于答辩时解释“为什么这样判断”。
5. P0/P1 分期清晰：P0 保证课程闭环可跑，P1 增强 Neo4j、复杂采集和结构化报告。

---

## 6. 后续待补

报告测试与答辩组后续需要补：

1. 每个项目的截图或官方文档截图。
2. 每个项目的优缺点对比。
3. 本项目与 OpenCTI、MISP、SpiderFoot 的重点对照表。
4. “我们没有做什么”的边界说明，例如不做完整事件响应平台、不做完整 STIX 平台、不做真实恶意样本沙箱。
5. 最终创新点表述，避免夸大。
