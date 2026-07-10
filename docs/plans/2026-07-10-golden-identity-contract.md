# Golden 实体身份职责修正 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 从黄金集移除由 QA 人工生成的 `canonical_id`，明确实体最终 ID 由后端归一化生成。

**Architecture:** 黄金集只保存人工确认的实体名称、类型、别名和证据；候选抽取与黄金集使用同一实体描述字段。后端归一化服务根据 `name`、`type` 和 `aliases` 完成实体合并并生成正式 `entity_id`，评测数据不预先指定后端 ID。

**Tech Stack:** JSON Schema Draft 2020-12、JSON 示例、Markdown 契约文档、pytest。

---

### Task 1: 锁定黄金集实体字段边界

**Files:**
- Modify: `backend/tests/test_promoted_examples.py`

**Step 1: 写入失败测试**

增加断言，要求黄金集 Schema 不声明 `canonical_id`，示例实体也不包含该字段。

**Step 2: 运行测试并确认失败**

Run: `docker compose run --rm backend python -m pytest backend/tests/test_promoted_examples.py -v`

Expected: FAIL，指出 Schema 或示例仍包含 `canonical_id`。

### Task 2: 修正 Schema 与示例

**Files:**
- Modify: `docs/schemas/golden.schema.json`
- Modify: `data/examples/golden.apt28.thn.beardshell.example.json`

**Step 1: 删除 Schema 字段**

从 `golden_entity.required` 和 `golden_entity.properties` 删除 `canonical_id`。

**Step 2: 删除示例字段**

删除所有黄金集实体中的 `canonical_id`，保留 `name`、`type`、`aliases` 和证据字段。

**Step 3: 运行测试并确认通过**

Run: `docker compose run --rm backend python -m pytest backend/tests/test_promoted_examples.py -v`

Expected: PASS。

### Task 3: 同步契约与标注手册

**Files:**
- Modify: `docs/data-contract.md`
- Modify: `docs/guides/golden-annotation-reference.md`

**Step 1: 明确字段归属**

说明 QA 不生成 `canonical_id` 或最终 `entity_id`；后端归一化服务基于 `name`、`type`、`aliases` 生成正式 `entity_id`。

**Step 2: 更新别名与评测说明**

说明别名与标准名共同用于实体对齐；同一实体的别名不拆成多个黄金实体；无法确认时记录待复核，不强行合并。

**Step 3: 执行文档和 JSON 验证**

Run: `git diff --check`

Run: `docker compose run --rm backend python -m pytest backend/tests/test_promoted_examples.py -v`

Expected: 两个命令均成功。

### Task 4: 自我评审并发布 PR

**Files:**
- Review: `docs/schemas/golden.schema.json`
- Review: `data/examples/golden.apt28.thn.beardshell.example.json`
- Review: `docs/data-contract.md`
- Review: `docs/guides/golden-annotation-reference.md`
- Review: `backend/tests/test_promoted_examples.py`

**Step 1: 检查遗留引用和职责漂移**

确认黄金集相关文件不再要求 `canonical_id`，同时不误删后端正式图谱的 `entity_id` 规则。

**Step 2: 分离提交**

计划文档单独提交；测试与契约修正作为第二个提交。

**Step 3: 推送并创建 PR**

推送 `fix/arch/golden-identity-contract`，创建面向 `main` 的 PR，并列出决策点和验证结果。
