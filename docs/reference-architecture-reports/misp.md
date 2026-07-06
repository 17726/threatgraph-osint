# MISP 架构借鉴分析

## 资料来源

1. MISP GitHub：https://github.com/MISP/MISP
2. MISP 官网：https://www.misp-project.org/
3. MISP 数据模型：https://www.misp-project.org/datamodels/

## 项目定位

MISP 是面向威胁情报共享的开源平台，核心对象包括 Event、Attribute、Object、Tag、Galaxy 和 Feed。它强调结构化情报录入、指标共享、事件协作、导入导出和与 IDS、STIX、MISP JSON 等格式的兼容。

MISP 更偏“情报共享和指标管理”，而不是“从自然语言 OSINT 文本中用 LLM 自动抽取知识图谱”。

## 与本项目架构对比

相同点：

1. 都需要把外部情报转成结构化数据。
2. 都强调来源、标签、威胁实体、技术和指标之间的关联。
3. 都需要导入导出和报告可复用。
4. 都可以使用 ATT&CK / Galaxy 类知识辅助归类。

MISP 的优势：

1. Event 作为情报容器清晰，适合组织一次攻击事件、报告或情报包。
2. Attribute / Object 粒度成熟，适合管理 IOC、恶意软件、攻击技术等细粒度对象。
3. Tag / Galaxy 机制适合对情报进行分类、标记和关联标准知识库。
4. Feed 和导入导出能力成熟，适合接入外部情报流。

MISP 相对本项目的不足：

1. 它偏 IOC 和共享流程，对自然语言深度分析、实体关系抽取不是核心。
2. 完整 MISP 数据模型较重，P0 照搬会增加字段和页面复杂度。
3. 课程要求更关注 APT 行为模式和知识图谱推理，而不是情报社区共享。

本项目当前架构的优势：

1. `documents/chunks/extracted_*` 更适合承接 LLM 抽取流水线。
2. `entities/relations/evidence` 更适合知识图谱展示。
3. `behavior_patterns`、`mitre_mappings`、`inferred_relations` 更贴合课程题目。
4. SQLite 单事实源比完整共享平台更易在答辩环境复现。

## 是否应该学习

应该学习 MISP 的“情报容器”和“标签归类”思想，但不应把项目改成 MISP 风格的 IOC 平台。

建议学习：

1. 把每篇报告、新闻或社媒整理文本视作一个可追溯情报容器。
2. 为文档、实体、关系和报告保留标签或分类字段。
3. 用 Tag / Galaxy 的思想组织 ATT&CK 技术、APT 组织、恶意软件家族。
4. 后续导出格式可考虑兼容 MISP JSON 或 STIX 子集。

不建议学习：

1. P0 不做完整 Event / Attribute / Object 层级。
2. 不把 IOC 管理作为主线。
3. 不做复杂的共享组、发布控制和社区同步。

## 阶段与优先级建议

### 优先级 P0

可吸收：

1. 在样本数据和报告中明确“来源文档就是情报容器”。
2. 保留 `source_type`、`target_group`、`language`、`metadata_json`。
3. 通过 `mitre_mappings` 和实体类型模拟轻量 Tag / Galaxy 效果。
4. 报告中按目标组织、攻击技术、目标行业组织内容。

不放入 P0：

1. 完整 MISP 数据模型。
2. MISP 实例同步。
3. 面向 IDS 的规则导出。

### 优先级 P1

可吸收：

1. 增加轻量标签字段，例如 `tags_json` 或统一分类表。
2. 增加 RSS/feed 采集器和导入运行状态。
3. 报告接口返回结构化章节，方便后续导出。
4. 评测中统计不同来源、标签、技术映射的覆盖率。

### 优先级 P2

可吸收：

1. MISP JSON 或 STIX 子集导出。
2. 情报包导入导出。
3. 多用户协作、审核、发布和版本管理。
4. 与真实 MISP 平台进行单向数据交换。

## 结论

MISP 对本项目最有价值的不是具体技术栈，而是“情报容器 + 标签分类 + 导入导出”的架构思想。优先级 P0 可以吸收轻量分类和来源组织方式；增强阶段再强化 feed、标签、格式兼容和共享能力。
