# 参考项目架构借鉴报告索引

> 目的：从成熟开源项目中提炼可借鉴的架构设计思想，辅助 ThreatGraph-OSINT 的优先级和阶段取舍。
> 日期：2026-07-07

## 选型结论

本目录优先分析 5 个对当前项目架构最有参考价值的项目：

| 项目       | 主要价值                                               | 是否建议学习                     | 适合落入优先级 |
| ---------- | ------------------------------------------------------ | -------------------------------- | -------------- |
| OpenCTI    | STIX 风格知识图谱、连接器、情报对象建模                | 强烈建议学习思想，不照搬平台     | P0 / P1 / P2   |
| MISP       | Event、Attribute、Object、Tag、Galaxy、Feed 和共享格式 | 建议学习情报容器和标签体系       | P0 / P1 / P2   |
| SpiderFoot | OSINT 采集模块、扫描任务、Web/CLI 双入口               | 建议学习采集器和运行状态设计     | P0 / P1 / P2   |
| GraphRAG   | 非结构化文本到知识图谱、社区摘要、图增强问答           | 建议学习流程，不直接引入完整框架 | P0 / P1 / P2   |
| TypeDB CTI | STIX 2.1 强 schema、语义关系约束                       | 建议学习 schema-first 思想       | P0 / P1 / P2   |

未纳入单独报告的项目不是没有价值，而是不适合当前优先级：

1. Maltego 更适合作为图谱交互体验参考，商业属性较强。
2. TheHive 当前更偏事件协同和商业维护方向，可作为报告/流程参考，不适合作为核心开源架构对标。
3. Cuckoo、T-Pot、Cortex 更偏动态分析、蜜罐或外部分析器，可放到 P2 enrichment 讨论。
4. Yeti 可作为轻量 CTI 工作台参考，但对当前课程 MVP 的增量价值低于 OpenCTI、MISP、SpiderFoot。

## 总体阶段与优先级建议

### 优先级 P0：保持最小闭环

优先级 P0 只吸收这些项目中能够直接支撑演示链路的思想：

1. OpenCTI / TypeDB CTI：实体、关系、证据、置信度和受控关系类型。
2. MISP：文档或事件作为情报容器，给来源、目标组织、标签、技术映射保留字段。
3. SpiderFoot：`sources -> collection_runs -> collected_items -> documents` 的采集运行模型。
4. GraphRAG：文档切块、结构化 LLM 抽取、缓存中间结果。

第一阶段先用本地文本和固定 JSON 契约跑通离线链路；P0 不做完整 STIX、完整连接器生态、复杂权限、复杂调度、图社区发现。

### 优先级 P1：增强图谱和采集能力

优先级 P1 适合引入会明显增强答辩展示的能力：

1. Neo4j 多跳路径查询和 Cypher 展示。
2. 更清晰的来源管理、采集重试、去重和增量 checkpoint。
3. 关系约束校验，避免 LLM 输出非法关系。
4. 结构化报告章节，报告结论能回溯到 evidence、analysis 和 graph refs。

### 优先级 P2：作为加分项或后续扩展

优先级 P2 适合放入课程报告的后续展望：

1. STIX 2.1 子集导入导出，兼容 OpenCTI / MISP。
2. 更完整的 GraphRAG 社区摘要和图增强问答。
3. 插件式采集器和 enrichment analyzer。
4. 更严格的 schema/rule 推理，甚至评估 TypeDB 作为研究型后端。
5. 团队协同、权限、版本审计、情报共享。

## 单项报告

1. [OpenCTI 架构借鉴分析](opencti.md)
2. [MISP 架构借鉴分析](misp.md)
3. [SpiderFoot 架构借鉴分析](spiderfoot.md)
4. [GraphRAG 架构借鉴分析](graphrag.md)
5. [TypeDB CTI 架构借鉴分析](typedb-cti.md)
