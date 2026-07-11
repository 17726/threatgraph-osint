# P0 实体与关系本体扩展 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 扩展 P0 实体与关系类型，建立可执行的单主类型标注规则，并让所有正式黄金集通过统一质量门禁。

**Architecture:** Schema 是实体和关系枚举的契约源，Python 校验器负责矩阵、端点和证据检查，离线归一化管线负责正式 ID 与关系标签。Golden 与 extraction 共用关系矩阵，但保持各自顶层 Schema；现有黄金集按新本体迁移，不自动补充原文未出现的上位概念。

**Tech Stack:** JSON Schema Draft 2020-12、Python、pytest、Markdown。

---

### Task 1: 用失败测试锁定新枚举和矩阵

**Files:**
- Modify: `backend/tests/test_validate_extraction_result.py`
- Modify: `backend/tests/test_offline_extraction_pipeline.py`

**Step 1: 添加新类型与关系测试**

断言三个 Schema 都包含 `LOCATION`、`INFRASTRUCTURE`，并包含 `PRECEDES`、`INSTANCE_OF`、`IN_INDUSTRY`。

**Step 2: 添加关系矩阵测试**

覆盖：

```text
MALWARE USES INFRASTRUCTURE
APT_GROUP TARGETS LOCATION
CAMPAIGN ATTRIBUTED_TO APT_GROUP
EVENT PRECEDES EVENT
ORGANIZATION INSTANCE_OF TARGET
ORGANIZATION IN_INDUSTRY INDUSTRY
```

**Step 3: 添加归一化 ID 测试**

断言：

```text
INFRASTRUCTURE -> infrastructure:<slug>
LOCATION -> location:<slug>
```

**Step 4: 运行测试并确认失败**

Run: `python -m pytest backend/tests/test_validate_extraction_result.py backend/tests/test_offline_extraction_pipeline.py -v`

Expected: FAIL，指出新枚举、矩阵或 ID 前缀尚未实现。

### Task 2: 实现 Schema、矩阵和归一化支持

**Files:**
- Modify: `docs/schemas/extraction-result.schema.json`
- Modify: `docs/schemas/golden.schema.json`
- Modify: `docs/schemas/graph.schema.json`
- Modify: `scripts/validate_extraction_result.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`

**Step 1: 扩展三个 Schema**

同步新增实体和关系枚举。

**Step 2: 扩展关系矩阵常量**

实现设计文档中的新关系方向，并调整 `USES`、`TARGETS`、`ATTRIBUTED_TO`。

**Step 3: 扩展正式 ID 和关系标签**

增加 `infrastructure`、`location` 前缀及三个中文关系标签。

**Step 4: 运行测试并确认通过**

Run: `python -m pytest backend/tests/test_validate_extraction_result.py backend/tests/test_offline_extraction_pipeline.py -v`

Expected: PASS。

**Step 5: 提交**

```bash
git add backend/tests/test_validate_extraction_result.py backend/tests/test_offline_extraction_pipeline.py docs/schemas scripts/validate_extraction_result.py backend/app/services/offline_extraction_pipeline.py
git commit -m "feat: 扩展实体与关系本体契约"
```

### Task 3: 建立正式黄金集质量门禁

**Files:**
- Create: `scripts/validate_golden.py`
- Create: `backend/tests/test_golden_contract.py`

**Step 1: 添加失败测试**

遍历 `data/evaluation/golden*.json`，检查 Golden Schema、关系矩阵、同 chunk 端点和对应文档证据位置。

**Step 2: 运行测试并确认当前数据失败**

Run: `python -m pytest backend/tests/test_golden_contract.py -v`

Expected: FAIL，列出当前 Kimsuky 黄金集的矩阵错误和 APT28 基础设施类型迁移要求。

**Step 3: 实现 CLI 校验器**

支持传入 golden 与文档路径，复用关系矩阵和证据位置校验；CLI 失败返回非零退出码。

### Task 4: 修正现有黄金集

**Files:**
- Modify: `data/evaluation/golden.en.apt28_080.json`
- Modify: `data/evaluation/golden.en.kimsuky_060.json`

**Step 1: 迁移 APT28 基础设施**

将 C2 域名从 `TOOL` 改为 `INFRASTRUCTURE`，同步关系端点类型和 notes。

**Step 2: 修正 Kimsuky 关系**

```text
Andariel AFFILIATED_WITH Lazarus Group
Operation Blacksmith ATTRIBUTED_TO Lazarus Group
NineRAT USES Telegram
Operation Blacksmith DISCOVERED_BY Cisco Talos
HazyLoad DISCOVERED_BY Microsoft
```

**Step 3: 拆分行业实体**

将制造业、农业、物理安全拆成三个 `INDUSTRY` 实体和三条 `TARGETS` 关系，保持证据文本不变。

**Step 4: 运行黄金集门禁**

Run: `python -m pytest backend/tests/test_golden_contract.py -v`

Expected: PASS。

**Step 5: 提交**

```bash
git add scripts/validate_golden.py backend/tests/test_golden_contract.py data/evaluation
git commit -m "fix: 修正黄金集本体与关系方向"
```

### Task 5: 同步文档与 LLM Prompt

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/data-contract.md`
- Modify: `docs/prompts/extract-v1.md`
- Modify: `docs/schemas/relationship-matrix.md`
- Modify: `docs/schemas/README.md`
- Modify: `docs/guides/golden-annotation-reference.md`

**Step 1: 同步实体与关系枚举**

更新所有正式契约和 Prompt 白名单。

**Step 2: 增加互斥决策表**

写明具体类型优先、`TARGET` 只承载泛指目标、行业只在原文明示时标注、一个实体一个主类型。

**Step 3: 增加关系方向和混合表达示例**

明确 `PART_OF`、`INSTANCE_OF`、`IN_INDUSTRY`、`DISCOVERED_BY`、`PRECEDES` 的方向。

**Step 4: 增加 Golden 校验命令**

在 guide 中给出 `scripts/validate_golden.py` 的使用方法。

**Step 5: 提交**

```bash
git add docs
git commit -m "docs: 完善黄金集本体标注规则"
```

### Task 6: 验证、发布 PR 与自我 CR

**Files:**
- Review: all files changed from `origin/main`

**Step 1: 完整验证**

Run: `python -m pytest backend/tests -v`

Run: `git diff --check origin/main...HEAD`

Run: `python scripts/validate_golden.py data/evaluation/golden.en.apt28_080.json data/documents/apt28/apt28_080.json`

Run: `python scripts/validate_golden.py data/evaluation/golden.en.kimsuky_060.json data/documents/kimsuky/kimsuky_060.json`

Expected: 全部成功。

**Step 2: 推送并创建草稿 PR**

推送 `feat/arch/ontology-v1`，创建面向 `main` 的草稿 PR，列出决策点、迁移影响和验证结果。

**Step 3: PR 后自我 CR**

检查：

1. Schema、代码、矩阵和 Prompt 枚举完全一致。
2. 新关系方向无歧义，`PART_OF` 未被复用。
3. Golden 没有自动补充原文未出现的行业或上位类别。
4. 现有数据无矩阵错误、反向关系和非原子行业实体。
5. 前端/API 不依赖封闭类型联合，新增类型不会造成展示回归。

重要问题修正后追加独立 commit 并推送到同一 PR。
