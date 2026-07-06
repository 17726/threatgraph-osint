# TypeDB CTI 架构借鉴分析

## 资料来源

1. TypeDB CTI GitHub：https://github.com/typedb-osi/typedb-cti
2. TypeDB CTI 用例：https://typedb.com/use-cases/cyber-threat-intelligence
3. TypeDB 概念文档：https://typedb.com/docs/home/what-is-typedb/

## 项目定位

TypeDB CTI 使用 TypeDB 和 TypeQL 表达 STIX 2.1 网络威胁情报 schema。它强调强类型、语义关系、schema 校验和复杂关系推理，适合构建高一致性的威胁情报知识库。

它对本项目的价值不是替换 SQLite 或 Neo4j，而是提醒我们：LLM 抽取结果必须经过 schema 约束和关系合法性检查，不能把自由文本关系直接变成正式图谱事实。

## 与本项目架构对比

相同点：

1. 都关注 CTI 实体和关系建模。
2. 都希望避免无约束关系污染图谱。
3. 都需要支持复杂关系查询和推理。
4. 都可借鉴 STIX 2.1 的语义结构。

TypeDB CTI 的优势：

1. schema-first，实体类型、关系类型、属性类型都先定义。
2. 关系可包含角色语义，比普通边更适合表达复杂 CTI 关系。
3. 强类型和约束能减少非法数据进入知识库。
4. 适合研究型场景下做复杂推理。

TypeDB CTI 相对本项目的不足：

1. 引入 TypeDB 会显著增加部署和学习成本。
2. TypeQL、schema 和数据导入需要额外开发时间。
3. 课程 MVP 更需要稳定演示链路，不需要完整 STIX 语义数据库。
4. 前端、后端、评测都要重新适配，短期收益不如 SQLite + Neo4j 清晰。

本项目当前架构的优势：

1. SQLite 简单透明，适合课程复现和团队协作。
2. Neo4j 只做增强阶段 / 优先级 P1 图查询增强，职责清楚。
3. 数据契约已经定义实体、关系、证据和推理分层。
4. 后端可以在写入 canonical graph 前实现轻量 schema 校验。

## 是否应该学习

应该学习 TypeDB CTI 的 schema-first 和语义约束思想，但不建议把 TypeDB 放进 P0 或 P1 主链路。

建议学习：

1. 先定义实体类型和关系类型，再允许 LLM 输出映射到这些类型。
2. 对关系组合做合法性校验，例如 APT 组织可以 `USES` 恶意软件或技术，但不能随意 `USES` 时间实体。
3. 把候选推断关系和正式事实关系分开。
4. 为将来 STIX 子集兼容预留字段。

不建议学习：

1. P0/P1 不引入 TypeDB 服务。
2. 不完整实现 STIX 2.1 schema。
3. 不把关系推理复杂化到影响 MVP 交付。

## 阶段与优先级建议

### 优先级 P0

可吸收：

1. 实体类型和关系类型使用白名单。
2. LLM 输出先进入 `extracted_*` 候选表。
3. 归一化服务负责生成稳定 ID 和合并别名。
4. 写入 `relations` 前做基础合法性检查。

不放入 P0：

1. TypeDB 部署。
2. TypeQL schema。
3. 完整 STIX schema 校验。

### 优先级 P1

可吸收：

1. 增加关系合法性矩阵。
2. 增加 schema 校验测试用例。
3. 推断关系保持 `candidate/accepted/rejected` 状态。
4. Neo4j 同步前再次校验 canonical graph。

### 优先级 P2

可吸收：

1. STIX 2.1 子集 schema。
2. 更复杂的规则推理。
3. 评估 TypeDB 作为研究型替代图后端。
4. 生成可交换、可验证的标准化 CTI 包。

## 结论

TypeDB CTI 对本项目最大的启发是“先有 schema，再有事实”。我们当前不需要引入 TypeDB，但应该把 schema 校验和关系约束放进优先级 P0/P1 的实现思路中，防止 LLM 生成的弱结构数据污染正式图谱。
