# 本体契约同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已确认的实体类型、关系矩阵和证据边界同步到项目契约、Schema、Prompt、样例、后端校验和验收测试。

**Architecture:** 以 `scripts/validate_extraction_result.py` 的关系矩阵作为候选抽取校验的单一实现入口，文档和 JSON Schema 与其保持同一枚举。删除 `TARGET`，增加 `INFRASTRUCTURE`、`LOCATION`、`FINANCIAL_ACCOUNT` 及已确认关系；通过迁移现有示例和新增最小犯罪网络样本验证端到端归一化。

**Tech Stack:** Markdown, JSON Schema Draft 2020-12, Python, SQLite, pytest

## Global Constraints

- SQLite 是唯一事实源，`graph.json` 仅为导出快照。
- 只有原文明确证据才能标注新增关系，不根据共现或常识推断。
- 不新增实体专属字段，保留业务字段 `target_group`。
- 不覆盖工作区中此前已有的未提交决策记录。
- 代码、文档、提交说明默认使用简体中文或英文，文件使用 UTF-8。

---

### Task 1: 同步契约和关系矩阵

**Files:**
- Modify: `docs/data-contract.md`
- Modify: `docs/schemas/relationship-matrix.md`
- Modify: `docs/prompts/extract-1.0.md`
- Modify: `docs/guides/golden-annotation-reference.md`
- Modify: `docs/schemas/extraction-result.schema.json`
- Modify: `docs/schemas/golden.schema.json`
- Modify: `docs/schemas/graph.schema.json`

- [ ] **Step 1: 更新实体枚举**

从所有契约枚举中移除 `TARGET`，加入 `INFRASTRUCTURE`、`LOCATION`、`FINANCIAL_ACCOUNT`。

- [ ] **Step 2: 更新关系枚举和矩阵**

加入 `MEMBER_OF`、`CONTROLS`、`TRANSFERS_TO`、`INSTANCE_OF`、`PRECEDES`，并将 `USES`、`PART_OF`、`AFFILIATED_WITH`、`EXPLOITS` 的主体和客体限制同步为已确认版本。

- [ ] **Step 3: 更新抽取和标注规则**

明确 `TARGETS` 使用语义实体类型，`CAMPAIGN PART_OF APT_GROUP`，以及新增关系不得推断。

- [ ] **Step 4: 校验 JSON 文件语法**

运行：`python -m json.tool docs/schemas/extraction-result.schema.json`、`python -m json.tool docs/schemas/golden.schema.json`、`python -m json.tool docs/schemas/graph.schema.json`

### Task 2: 同步后端矩阵和演示数据

**Files:**
- Modify: `scripts/validate_extraction_result.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`
- Modify: `backend/app/services/demo_store.py`
- Test: `backend/tests/test_validate_extraction_result.py`
- Test: `backend/tests/test_offline_extraction_pipeline.py`

- [ ] **Step 1: 先添加新增关系的矩阵测试**

覆盖成员、控制、转账、实例分类和时间先后关系的合法/非法端点。

- [ ] **Step 2: 运行测试确认新增行为失败**

运行：`python -m pytest backend/tests/test_validate_extraction_result.py backend/tests/test_offline_extraction_pipeline.py -q`

- [ ] **Step 3: 更新后端枚举和标签**

移除 `TARGET` 前缀，增加三个实体前缀和五个关系标签；保持既有 `TARGETS` 关系对语义实体的支持。

- [ ] **Step 4: 运行目标测试确认通过**

运行：`python -m pytest backend/tests/test_validate_extraction_result.py backend/tests/test_offline_extraction_pipeline.py -q`

### Task 3: 迁移黄金集和可复制样例

**Files:**
- Modify: `data/examples/extraction_result.apt28.thn.beardshell.example.json`
- Modify: `data/examples/golden.apt28.thn.beardshell.example.json`
- Modify: `data/evaluation/golden.en.kimsuky_060.json`
- Modify: `data/evaluation/golden.en.apt28_080.json`
- Modify: `data/examples/graph.apt28.thn.beardshell.example.json`

- [ ] **Step 1: 将现有 `TARGET` 实体迁移为语义类型**

将明确的政府机构目标改为 `ORGANIZATION` 或 `INDUSTRY`，同步关系端点，删除不再合法的 `TARGET` 枚举值。

- [ ] **Step 2: 增加最小犯罪网络黄金样本**

在现有 golden 结构中补充有明确证据的 `PERSON MEMBER_OF APT_GROUP`、`APT_GROUP CONTROLS FINANCIAL_ACCOUNT`、`FINANCIAL_ACCOUNT TRANSFERS_TO FINANCIAL_ACCOUNT` 和 `APT_GROUP USES TECHNIQUE`。

- [ ] **Step 3: 校验所有样例**

运行对应 Schema 校验和抽取结果校验脚本，确保没有 `TARGET` 实例残留。

### Task 4: 端到端验收和进度记录

**Files:**
- Modify: `TODO.md`
- Test: `backend/tests/test_ontology_contract.py`

- [ ] **Step 1: 添加契约一致性测试**

测试 Schema 枚举、后端矩阵和关系矩阵文档包含同一组实体/关系，并验证 `TARGET` 不再是有效实体类型。

- [ ] **Step 2: 运行完整后端验证**

运行：`python -m pytest backend/tests -v`

- [ ] **Step 3: 更新 TODO 进度**

只勾选本轮实际完成的契约同步、校验和样本迁移项；真实犯罪网络外部来源样本若未完成，保留未完成状态并写明边界。
