# LLM 抽取与评测架构收口 Implementation Plan

> **状态说明（2026-07-15）：** 本文件是总体方向和任务池，不是不可修改的最终方案。
> PR35 第一阶段只落实版本命名、UTC、运行身份和跨文件绑定；Git 归档范围、SQLite/Neo4j
> 边界及后续阶段以 `docs/plans/2026-07-15-pr35-phase-1-artifact-contract-hardening.md`
> 和后续 ADR 为准。
>
> 同日已确认的 Golden 全文标注、Experiment 归档、版本职责和切块评测边界见
> `docs/decisions/2026-07-15-llm-golden-experiment-decisions.md`。评测指标计算逻辑见
> `docs/reviews/2026-07-15-llm-evaluation-metrics-review.md`，当前仍是二审稿，尚未实现。
> 本计划中关于强可复现门槛、Golden v2、Experiment 目录和指标改造的内容继续作为任务候选，
> 不能据此判断 `main` 已具备相应能力。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 Document 导入、确定性切块、LLM 原始响应、候选审计、正式抽取、Golden 标注和评测结果收口为一条可复现、可审计的链路，并形成能够证明项目价值的持续迭代记录。

**Architecture:** Git 中的 `data/documents/`、Golden、Promoted Experiment 与 Baseline 是可复现输入和实验档案；SQLite 保存运行期事实、模型原始响应、候选、正式抽取和评测运行；Neo4j 保存可由 SQLite 重建的图查询投影。Golden 绑定文档内容哈希和全文位置，不绑定切块结果；评测按文档级规范化后比较，同时分别报告原始发射层与有效候选层指标。

**Tech Stack:** Python 3、FastAPI、SQLite、Pydantic/JSON Schema、pytest、React/TypeScript、Vitest、Docker Compose。

---

## 0. 执行约束与完成定义

### 0.1 执行约束

1. 实施前先确认 PR #33（`codex/llm-import-clean-text`）状态。它与 `offline_extraction_pipeline.py` 重叠，应作为前置依赖合入或明确重放，不在本计划中重复实现 `raw_text -> clean_text` 迁移。
2. 禁止在 `main` 上修改。建议实施分支：`fix/arch/llm-evaluation-closure`；每个任务按下面建议提交，便于逐项评审与回退。
3. 先更新契约和失败测试，再写实现；跨组字段变化必须由架构与数据规范组评审。
4. SQLite 是运行期 canonical 事实源；Promoted Experiment 和已审核 Baseline 可以作为不可变 JSON 运行包进入 Git。普通本地运行不得形成未声明的平行事实源。
5. 不提交 API Key、鉴权头、未脱敏提示词中的隐私数据或真实课程原始 PDF。
6. 本计划不把 Neo4j 纳入抽取或评测链路；只有校验通过的正式抽取结果可进入后续图谱同步。

### 0.2 Definition of Done

- 同一 Document、同一抽取配置、同一模型响应可以重放并得到相同候选、正式抽取和评测结果。
- Document、chunk set、extraction run、Golden set、evaluation run 都有稳定 ID、版本、内容哈希和时间戳。
- Golden 不依赖 chunk ID；改变切块参数后无需重标 Golden，仍可比较召回率、准确率、成本和时延。
- 原始模型响应先于解析持久化；解析失败、Schema 失败和关系证据失败均可审计。
- 评测至少给出实体与关系的 TP/FP/FN、P/R/F1、support，并区分 `raw_emission` 与 `validated_candidate` 两个作用域。
- 关系评测同时报告端到端指标和“实体端点均正确时”的条件关系指标。
- API 和前端读取真实评测运行，不再以 `mockEval.ts` 冒充验收结果。
- 至少形成一个可复现基线包和一份切块消融实验报告，报告可追溯到数据、配置、模型与代码提交。
- 后端测试、前端测试/构建/格式检查全部通过；无法执行的命令在 PR 中说明原因。

## 1. `/grill` 质询后的阶段性决策

### 1.1 数据对象与职责

| 对象 | 含义 | 事实源 | 是否入 Git | 与评测的关系 |
| --- | --- | --- | --- | --- |
| Document import package | 可复现输入文档及元数据 | Git 文件 | 是，脱敏后 | Golden 与运行都引用其内容哈希 |
| `documents` / `document_chunks` | 已导入、已规范化的运行期文档与切块 | SQLite | 否 | 评测运行通过 Document 身份关联 |
| provider raw response | DeepSeek 等供应商返回的原始响应正文与元数据 | SQLite | 仅随 Promoted Experiment 脱敏归档 | 可重放解析，解释漏抽、格式错与成本 |
| raw emission | 从响应中能识别出的每一条原始候选，包括重复、非法和最终被拒绝项 | SQLite | 否 | 衡量模型输出纪律和端到端失败 |
| validated candidate | 通过基础 Schema/类型/证据范围校验并完成去重归并的候选 | SQLite | 否 | 衡量语义抽取质量 |
| extraction result | 被接受的实体、关系和证据，是后续图谱输入 | SQLite | 被提升实验以 JSON 归档 | 作为默认业务预测集参与评测 |
| candidate audit | 每条候选的校验、拒绝、归并原因 | SQLite | 被提升实验与结果成对归档 | 形成错误分类与可解释性 |
| Golden set | 人工确认的标准答案和标注政策 | Git 文件 + SQLite 注册信息 | 是 | 唯一标准答案，不由待评模型生成 |
| evaluation result | 某一预测快照对某一 Golden 的度量与明细 | SQLite | Promoted Experiment / Baseline 归档 | 记录 TP/FP/FN、P/R/F1 和错误明细 |

### 1.2 对当前疑问的明确结论

1. `data/documents/*` 不是 SQLite 的替代品。它是版本化、可审查、可重复导入的输入包；进入系统后，SQLite 中的 `documents` 才是运行期事实。
2. `data/examples/extraction_result.apt28.thn.beardshell.example.json` 当前是“人工复核的结果示例”，不是 DeepSeek 原始 JSON 响应。它必须改名或补充元数据，避免被误认为 provider raw response。
3. `extracted_*` 表示正式抽取域：经校验、归并并接受的实体、关系、证据。它不是评测结果，也不等于模型原始输出。
4. `evaluation_result.*.json` 是评测运行的可移植导出，记录 prediction 对 Golden 的 TP/FP/FN、P/R/F1 与逐项明细；它本身不是 Golden，也不是新的抽取事实源。
5. “F1 预测命中”应拆成可解释定义：`TP` 是规范化后与 Golden 匹配的预测；`FP` 是无匹配预测；`FN` 是未被预测命中的 Golden；`P=TP/(TP+FP)`、`R=TP/(TP+FN)`、`F1=2PR/(P+R)`。必须同时披露匹配规则和 support，不能只给一个 F1。
6. 现有 PQA 验收数字若缺少可重放脚本、输入快照、Golden 版本、模型配置和输出明细，只能标记为“历史观察值”，不能作为正式基线。
7. 切块是值得验证的优化方向，但不能先宣称“会提高召回率”。必须以同一 Document 与同一 Golden 做全篇、无重叠切块、重叠切块的消融实验，并同时看召回、精度、成本、时延和跨块重复。

### 1.3 Golden 身份与切块解耦

Golden v2 固定以下身份：

```text
golden_set_id + golden_version + annotation_policy_version
document_id + document_content_hash
entity/relation canonical identity + full-document evidence offsets
```

Golden 不保存某次运行的 `chunk_id` 作为匹配主键。chunk 只是推理策略，预测结果必须先把局部 offset 还原为全文 offset，再按 Document 聚合和去重后进行比较。这样才能回答“切块是否提升召回率”，而不是把评测绑定到某一种切块实现。

### 1.4 两层评测作用域

```text
Document
  -> chunk set
  -> provider raw response
  -> raw emission
  -> Schema / 关系矩阵 / 证据校验 / 去重归并
  -> validated candidate
  -> accepted extraction result
  -> 与 Golden v2 文档级比较
```

- `raw_emission`：所有可识别发射项均计入，包括重复、非法类型、缺证据和最终拒绝项。用于发现模型格式纪律、幻觉、重复和解析鲁棒性问题。
- `validated_candidate`：只评测通过基础校验并去重后的候选。用于隔离“模型语义能力”与“格式/治理能力”。
- 正式报告以 `validated_candidate` 的实体/关系端到端 F1 为主指标，同时必须附 `raw_emission` 指标、拒绝原因分布、条件关系 F1、成本和时延。

### 1.5 当前实现差距与对应任务

| 当前状态 | 架构问题 | 收口任务 |
| --- | --- | --- |
| runner 将整篇 Document 直接标为 `${doc_id}_c001` | 没有正式 chunk identity，无法验证切块效果或稳定还原 offset | Task 5-6 |
| `data/examples/extraction_result...example.json` 与 `data/extracted/...v1.json` 内容角色接近 | 示例、原始响应、正式抽取和运行导出边界不清 | Task 3、7-8 |
| provider raw response 没有独立、强制的先行持久化 | 解析失败后无法审计或重放 | Task 4、6 |
| candidate audit sidecar 与 SQLite 未形成统一记录 | 被拒绝/归并项可能丢失，raw 指标无法计算 | Task 4、7-8 |
| `evaluation_result.*.json` 只落文件 | 运行身份、输入快照和指标明细没有统一事实源 | Task 10-12 |
| Golden v1 绑定 chunk 或 chunk 边界 | 改切块即破坏可比性，无法做严格消融 | Task 2、5、9 |
| 关系矩阵同时存在于 Markdown 与 Python 常量 | 文档和运行校验可能漂移 | Task 2 |
| `demo_store.py` 与离线管线各自初始化 SQLite | 表结构和迁移入口不唯一 | Task 4 |
| `EvaluationPage` 使用 `mockEval.ts` | UI 展示不能证明真实验收运行 | Task 12-13 |
| 2026-07-13 基线只有单文档、单次、已校验候选口径 | 有探索价值，但缺 raw audit，不能作为完整端到端基线 | Task 14-16 |
| PR #33 修改 `offline_extraction_pipeline.py` 的 clean text 链路 | 与本计划核心文件重叠，存在重复修复/冲突风险 | Task 0 |

## 2. 目标目录结构

```text
data/
├── examples/                         # 小型契约示例；明确标注 manual-reviewed / synthetic
├── documents/                        # 可复现 Document 导入包，按 group 或数据集组织
│   └── <group>/
├── raw/                              # 采集器原始输入；与 LLM provider response 区分
│   └── <collector>/
├── legacy/                           # 旧命名/不可完全复现的历史样本，只读归档
├── extracted/
│   └── runs/<run_id>/                # 从 SQLite 导出的运行包，不是事实源
│       ├── manifest.json
│       ├── extraction-result.json
│       ├── candidate-audit.json
│       └── responses/                # 仅在明确脱敏后选择性导出
├── golden/v2/
│   ├── manifest.json
│   └── <group>.golden.json
├── evaluation/
│   ├── runs/<evaluation_run_id>/
│   │   └── evaluation-result.json    # 从 SQLite 导出
│   └── baselines/<baseline_id>/
│       ├── manifest.json
│       └── evaluation-result.json    # 经审核后固化的可复现基线
├── graph/                             # graph.json 等导出/前端 mock/Neo4j 同步输入
├── reports/                           # 课程与实验报告所需的生成产物
└── threatgraph_osint.db               # 本地运行库，默认不提交
```

迁移规则：

- `data/cleaned/` 退役；能证明来源和内容哈希的文件迁到 `documents/`，否则迁到 `legacy/`。
- `data/extracted/*.v1.json` 不再散落在根目录；能重建的迁为 run export，不能重建的迁到 `legacy/` 并标记 provenance。
- `data/evaluation/evaluation_result.*.json` 迁为 `runs/` 或 `baselines/`；没有运行清单的历史结果只能进 `legacy/`。
- `.gitignore` 明确区分临时运行目录和经审核基线；不能用一个宽泛规则同时忽略二者。

## 3. 分阶段实施任务

### Task 0：处理 PR #33 依赖并建立干净工作区

**Files:**

- Inspect: `backend/app/services/offline_extraction_pipeline.py`
- Inspect: PR #33 diff
- No product code changes

**Step 1：确认 PR 状态与重叠文件**

```bash
gh pr view 33 --json state,mergedAt,headRefName,headRefOid,baseRefName,files
git fetch origin
git diff origin/main...origin/codex/llm-import-clean-text -- backend/app/services/offline_extraction_pipeline.py
```

Expected：能明确 PR #33 是否已合入、其 head SHA，以及对重叠文件的修改范围。

**Step 2：选择唯一前置策略**

- 已合入：从最新 `origin/main` 建实施分支。
- 未合入但仍需采用：先等待/评审并合入 PR #33，再建分支。
- 明确放弃：在实施 PR 说明中记录原因，按 `origin/main` 开始；不得静默复制其实现。

**Step 3：建立分支并跑基线**

```bash
git switch main
git pull --ff-only origin main
git switch -c fix/arch/llm-evaluation-closure
docker compose run --rm backend python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run format:check
```

Expected：记录实施前通过/失败项；既有失败必须单独登记，不能混入本次修复。

**Commit:** 无。

### Task 1：契约优先，冻结术语、身份和数据流

**Files:**

- Create: `docs/adr/0004-llm-extraction-evaluation-persistence.md`
- Modify: `docs/architecture.md`
- Modify: `docs/data-contract.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/guides/llm-extraction-and-evaluation.md`
- Modify: `backend/tests/test_document_contract.py`
- Create: `backend/tests/test_evaluation_contract.py`

**Step 1：先写失败的契约测试**

测试应断言：

- 文档契约公开 `content_hash`、`chunk_set_id`、`chunker_version` 和全文 offset。
- 抽取运行契约公开 `document_content_hash`、模型/参数/提示词/Schema/关系矩阵版本。
- 评测契约公开 `golden_set_id/version/hash`、`prediction_run_id`、`scope`、support 和 TP/FP/FN。
- 文档中不存在“JSON 与 SQLite 同时为事实源”的歧义表述。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_document_contract.py backend/tests/test_evaluation_contract.py -v
```

Expected：FAIL，指出现有契约缺少新字段或定义。

**Step 2：写 ADR 和更新三份契约**

ADR 必须回答：

- 为什么 `data/documents` 是版本化输入而 SQLite 是运行事实；
- 为什么 provider raw response 与 `extraction_result` 不同；
- 为什么 Golden 绑定 Document hash 而非 chunk ID；
- 为什么 candidate audit 和 evaluation result JSON 是导出物；
- 为什么要同时评测 raw emission 和 validated candidate；
- 关系矩阵的机器可读单一来源在哪里。

**Step 3：重跑契约测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_document_contract.py backend/tests/test_evaluation_contract.py -v
```

Expected：PASS。

**Step 4：提交**

```bash
git add docs/adr/0004-llm-extraction-evaluation-persistence.md docs/architecture.md docs/data-contract.md docs/api-contract.md docs/guides/llm-extraction-and-evaluation.md backend/tests/test_document_contract.py backend/tests/test_evaluation_contract.py
git commit -m "docs: 冻结 LLM 抽取与评测数据契约"
```

### Task 2：建立机器可读关系矩阵与 v2 JSON Schema

**Files:**

- Create: `docs/schemas/relationship-matrix.json`
- Create: `docs/schemas/candidate-audit.schema.json`
- Create: `docs/schemas/evaluation-result.schema.json`
- Create: `docs/schemas/extraction-run-manifest.schema.json`
- Modify: `docs/schemas/extraction-result.schema.json`
- Modify: `docs/schemas/golden.schema.json`
- Modify: `docs/schemas/relationship-matrix.md`
- Modify: `docs/schemas/README.md`
- Create: `backend/app/core/relationship_matrix.py`
- Modify: `scripts/validate_extraction_result.py`
- Modify: `backend/app/services/llm_service.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`
- Modify: `backend/app/services/extraction_evaluator.py`
- Test: `backend/tests/test_relationship_matrix_contract.py`
- Test: `backend/tests/test_json_schemas.py`
- Modify: `backend/tests/test_ontology_contract.py`

**Step 1：写失败测试**

- JSON 关系矩阵是唯一机器可读来源，代码只能加载它，不能维护第二份硬编码集合。
- Markdown 表格中的关系与 JSON 一致；允许用脚本生成或在测试中校验。
- Golden v2 要求 `document_content_hash`、全文 evidence offset、annotation policy version。
- Extraction v2 要求 run identity、chunk identity、prompt/schema/matrix version。
- Evaluation result 要求作用域、匹配政策、support、TP/FP/FN 和逐项明细。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_relationship_matrix_contract.py backend/tests/test_json_schemas.py backend/tests/test_ontology_contract.py -v
```

Expected：FAIL。

**Step 2：实现最小 Schema 与加载器**

`relationship-matrix.json` 至少包含：

```json
{
  "schema_version": "1.0",
  "matrix_version": "2026-07-14",
  "relations": [
    {
      "type": "USES",
      "allowed_source_types": ["APT_GROUP", "PERSON"],
      "allowed_target_types": ["MALWARE", "TOOL"],
      "allowed_pairs": [
        ["APT_GROUP", "MALWARE"],
        ["APT_GROUP", "TOOL"],
        ["PERSON", "MALWARE"],
        ["PERSON", "TOOL"]
      ]
    }
  ]
}
```

示例只展示结构，正式矩阵必须完整迁移现有全部关系和精确 pair；校验以 `allowed_pairs` 为准，source/target 集合仅用于提示和概览。Golden v2 不保存 chunk 主键；证据位置为 Document 全文的 `[start, end)`。

现有 `scripts/validate_extraction_result.py` 中的 `ALLOWED_RELATIONS` 改为从统一加载器导出的只读兼容视图；`llm_service.py`、`offline_extraction_pipeline.py` 和 `extraction_evaluator.py` 全部使用该加载器。兼容常量只允许过渡，不得继续手工维护另一份矩阵。

**Step 3：实现 Markdown 一致性校验并通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_relationship_matrix_contract.py backend/tests/test_json_schemas.py backend/tests/test_ontology_contract.py -v
```

Expected：PASS。

**Step 4：提交**

```bash
git add docs/schemas backend/app/core/relationship_matrix.py scripts/validate_extraction_result.py backend/app/services/llm_service.py backend/app/services/offline_extraction_pipeline.py backend/app/services/extraction_evaluator.py backend/tests/test_relationship_matrix_contract.py backend/tests/test_json_schemas.py backend/tests/test_ontology_contract.py
git commit -m "feat: 统一关系矩阵并补充评测 Schema"
```

### Task 3：整理数据目录并显式标记历史资产

**Files:**

- Modify: `.gitignore`
- Create: `data/README.md`
- Move: `data/cleaned/**` -> `data/documents/**` or `data/legacy/**`
- Move: `data/extracted/*.json` -> `data/legacy/extracted/**` initially
- Move: `data/evaluation/evaluation_result.*.json` -> `data/legacy/evaluation/**` unless reproducible
- Modify: `data/examples/*.json`
- Create: `backend/tests/test_data_layout.py`

**Step 1：写目录政策失败测试**

测试应拒绝：

- `data/cleaned/` 中新增文件；
- `data/extracted/` 根目录散落 run JSON；
- 无 manifest 的 `data/evaluation/baselines/*`；
- example 文件声明为 raw response 却缺 provider metadata；
- baseline 被 `.gitignore` 意外忽略。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_data_layout.py -v
```

Expected：FAIL。

**Step 2：迁移并补 provenance**

每个遗留资产至少记录：原路径、来源、是否人工复核、是否可重放、迁移日期。示例 `extraction_result.apt28.thn.beardshell.example.json` 明确标注为 `manual-reviewed-example`；禁止把它描述成 DeepSeek 原始响应。

**Step 3：通过目录测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_data_layout.py -v
git check-ignore -v data/evaluation/baselines/.gitkeep
```

Expected：测试通过；第二条应无输出或显示显式反忽略规则。

**Step 4：提交**

```bash
git add .gitignore data backend/tests/test_data_layout.py
git commit -m "refactor: 整理抽取与评测数据目录"
```

### Task 4：统一 SQLite 初始化与迁移入口

**Files:**

- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/schema.py`
- Create: `backend/app/db/migrations/__init__.py`
- Create: `backend/app/db/migrations/0001_llm_evaluation_closure.sql`
- Modify: `backend/app/services/demo_store.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`
- Test: `backend/tests/test_db_schema.py`
- Test: `backend/tests/test_db_migrations.py`

**Step 1：写失败测试**

覆盖空库初始化、现有旧库升级、重复迁移幂等性和外键约束。要求 `demo_store.py` 与离线管线都调用同一个 schema/migration 入口，不能维护两套 `CREATE TABLE`。

目标新增/扩展表：

- `chunk_sets`：`chunk_set_id`、`document_id`、`document_content_hash`、chunker name/version/parameters/hash；
- `extraction_responses`：provider request/response、HTTP/parse 状态、token/latency、脱敏字段；
- `extracted_entities/relations/evidence`：增加 `emission_index`、raw candidate、validation status、merge target；
- `golden_sets`：只注册 Golden manifest、版本、哈希、标注政策；
- `evaluation_runs`：状态、Golden/prediction/config/code identity、作用域指标、成本与时延；
- `evaluation_matches`：逐项 TP/FP/FN 和匹配理由。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_db_schema.py backend/tests/test_db_migrations.py -v
```

Expected：FAIL。

**Step 2：实现统一 schema 与前向迁移**

迁移要求：

- 不删除旧数据；
- 新的非空身份字段先允许迁移态为空，再由 backfill 填充并在应用层拒绝新空值；
- `PRAGMA foreign_keys=ON`；
- schema version 单独记录；
- 迁移失败要事务回滚。

**Step 3：通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_db_schema.py backend/tests/test_db_migrations.py -v
```

Expected：PASS。

**Step 4：提交**

```bash
git add backend/app/db backend/app/services/demo_store.py backend/app/services/offline_extraction_pipeline.py backend/tests/test_db_schema.py backend/tests/test_db_migrations.py
git commit -m "refactor: 统一 SQLite 架构与迁移入口"
```

### Task 5：实现 Document 预检、导入和确定性切块

**Files:**

- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/routes/__init__.py`
- Create: `backend/app/services/document_importer.py`
- Create: `backend/app/services/document_chunker.py`
- Create: `backend/app/api/routes/documents.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/documents.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_document_importer.py`
- Test: `backend/tests/test_document_chunker.py`
- Test: `backend/tests/test_documents_api.py`

**Step 1：写失败测试**

至少覆盖：

- 同一规范化文本得到相同 SHA-256 `document_content_hash`；
- `raw_text` 只用于清洗，抽取只读 `clean_text`；
- 默认切块器 `paragraph-v1`，参数初始为 `max_chars=6000`、`overlap_chars=600`；
- 同文档同参数得到相同 `chunk_set_id` 与 chunks；
- chunk 保存全文 `[char_start, char_end)` 和自身 hash；
- overlap 不改变局部到全文 offset 的还原；
- API 预检不落库，正式导入在单事务中写 Document 与 chunk set；
- 内容相同但文件名不同按契约去重或明确冲突。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_document_importer.py backend/tests/test_document_chunker.py backend/tests/test_documents_api.py -v
```

Expected：FAIL。

**Step 2：实现纯函数切块器**

`chunk_set_id` 由以下规范化 JSON 求哈希：

```text
document_content_hash
chunker_name + chunker_version
max_chars + overlap_chars + boundary_policy
```

先按段落边界切分；超长段落再按句子/硬边界切分；每个 chunk 必须能映射回全文，禁止只生成 `${doc_id}_c001` 的伪切块。

**Step 3：实现预检和导入 API**

`POST /api/v1/documents/import/preflight` 返回文档身份、字符数、hash、预计 chunk 数、冲突/重复和警告；`POST /api/v1/documents/import` 返回 `document_id`、`content_hash`、`chunk_set_id`。Task 1 必须先把新增预检端点写入 API 契约。

**Step 4：通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_document_importer.py backend/tests/test_document_chunker.py backend/tests/test_documents_api.py -v
```

Expected：PASS。

**Step 5：提交**

```bash
git add backend/app/api backend/app/models backend/app/main.py backend/app/services/document_importer.py backend/app/services/document_chunker.py backend/tests/test_document_importer.py backend/tests/test_document_chunker.py backend/tests/test_documents_api.py
git commit -m "feat: 添加文档导入与确定性切块"
```

### Task 6：按 chunk 调用模型并先持久化原始响应

**Files:**

- Create: `backend/app/services/llm_provider.py`
- Modify: `backend/app/services/llm_service.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/extraction_runs.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`
- Create: `backend/app/api/routes/extractions.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_llm_provider.py`
- Test: `backend/tests/test_extraction_runner.py`

**Step 1：写失败测试**

覆盖：

- runner 必须读取已注册的 `chunk_set_id`，逐 chunk 调用，不自行拼伪 chunk；
- 在 JSON 解析前保存原始 response body、provider/model、request id、状态码、token usage、latency；
- 保存的请求信息包含 prompt template hash、schema version、matrix version 和参数，但不保存密钥/鉴权头；
- 单 chunk 失败时 run 状态为 `partial`，已完成响应不丢失且支持只重试失败 chunk；
- 状态机仅允许 `pending -> running -> succeeded|partial|failed`；
- 同一幂等键不会重复发送已成功请求。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_llm_provider.py backend/tests/test_extraction_runner.py -v
```

Expected：FAIL。

**Step 2：抽象 provider 接口并实现记录顺序**

建议接口如下；现有 `llm_service.py` 作为具体 provider adapter 复用或收口，不能再保留一条绕过记录层的直接调用路径：

```python
class LlmProvider(Protocol):
    def extract(self, request: ExtractionRequest) -> ProviderResponse: ...
```

持久化顺序必须是：创建 run -> 标记 chunk 请求 -> 收到响应即写 `extraction_responses` -> 再解析/校验。若数据库写原始响应失败，应停止解析，避免出现不可审计候选。

**Step 3：实现失败恢复与运行身份**

`run_id` 的 manifest 至少包含：

```text
document_id + document_content_hash + chunk_set_id
provider + model + model_revision_if_available
temperature + max_tokens + seed_if_supported
prompt_template_hash + schema_version + relationship_matrix_version
code_commit_sha + started_at + finished_at
```

**Step 4：通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_llm_provider.py backend/tests/test_extraction_runner.py -v
```

Expected：PASS。

**Step 5：提交**

```bash
git add backend/app/services/llm_provider.py backend/app/services/llm_service.py backend/app/repositories backend/app/services/offline_extraction_pipeline.py backend/app/api/routes/extractions.py backend/app/api/routes/__init__.py backend/app/main.py backend/tests/test_llm_provider.py backend/tests/test_extraction_runner.py
git commit -m "feat: 持久化 LLM 原始响应并支持分块抽取"
```

### Task 7：把全部可解析候选写入审计层，再形成正式抽取

**Files:**

- Create: `backend/app/services/candidate_parser.py`
- Create: `backend/app/services/candidate_validator.py`
- Create: `backend/app/services/candidate_merger.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`
- Modify: `backend/app/repositories/extraction_runs.py`
- Test: `backend/tests/test_candidate_parser.py`
- Test: `backend/tests/test_candidate_validator.py`
- Test: `backend/tests/test_candidate_merger.py`

**Step 1：写失败测试**

为每种结果建立固定用例：`accepted`、`rejected_schema`、`rejected_type`、`rejected_matrix`、`rejected_evidence`、`merged_duplicate`、`parse_failed`。断言每个可定位候选都有 `response_id`、`chunk_id`、`emission_index`、raw JSON、全文 evidence offset、状态与原因码。

同时覆盖：

- overlap 造成的同一实体/关系重复会归并，但 raw emission 仍保留两条；
- 关系端点必须能解析到候选实体，且满足关系矩阵；
- 证据文本必须与 Document 的全文 slice 一致；
- 无法安全还原 offset 的候选不能进入正式抽取；
- 人工修订必须新增 audit event，不能覆盖原始候选。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_candidate_parser.py backend/tests/test_candidate_validator.py backend/tests/test_candidate_merger.py -v
```

Expected：FAIL。

**Step 2：实现解析、校验、归并三段式纯逻辑**

- Parser 只负责尽可能识别发射项，不做业务接受决定。
- Validator 逐项产生稳定 reason code，不直接删除失败项。
- Merger 使用规范化实体 identity、关系 identity 与 evidence overlap 做确定性归并，并记录 `merged_into_id`。
- 只有 `accepted` 项写入正式 `extracted_*` 视图/记录；审计层保存全部项。

**Step 3：通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_candidate_parser.py backend/tests/test_candidate_validator.py backend/tests/test_candidate_merger.py -v
```

Expected：PASS。

**Step 4：提交**

```bash
git add backend/app/services/candidate_parser.py backend/app/services/candidate_validator.py backend/app/services/candidate_merger.py backend/app/services/offline_extraction_pipeline.py backend/app/repositories/extraction_runs.py backend/tests/test_candidate_parser.py backend/tests/test_candidate_validator.py backend/tests/test_candidate_merger.py
git commit -m "feat: 建立候选审计与正式抽取分层"
```

### Task 8：将 extraction result、candidate audit 变为 SQLite 派生导出

**Files:**

- Create: `backend/app/services/extraction_exporter.py`
- Create: `backend/app/cli/__init__.py`
- Create: `backend/app/cli/export_extraction_run.py`
- Test: `backend/tests/test_extraction_exporter.py`
- Modify: `docs/guides/llm-extraction-and-evaluation.md`

**Step 1：写失败测试**

用临时 SQLite 构造一个包含接受、拒绝和归并候选的 run，断言导出目录只有：

```text
manifest.json
extraction-result.json
candidate-audit.json
responses/<chunk_id>.json  # 仅显式 --include-responses
```

断言导出内容通过 Task 2 的 Schema，且删除导出目录后可以从数据库无损重建。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_extraction_exporter.py -v
```

Expected：FAIL。

**Step 2：实现确定性导出**

- JSON key 和数组顺序稳定；
- manifest 记录数据库 schema、导出器版本和内容 hashes；
- 默认不导出 provider raw response；显式导出时执行脱敏检查；
- 导入路径不得反向把导出 JSON 当运行事实覆盖 SQLite。

**Step 3：通过测试并做双次导出比较**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_extraction_exporter.py -v
docker compose run --rm backend python -m app.cli.export_extraction_run --run-id <fixture-run-id> --output /tmp/export-a
docker compose run --rm backend python -m app.cli.export_extraction_run --run-id <fixture-run-id> --output /tmp/export-b
diff -r /tmp/export-a /tmp/export-b
```

Expected：测试通过，`diff` 无输出。Windows 宿主执行时可改用 `Compare-Object`，但容器内优先使用上述命令。

**Step 4：提交**

```bash
git add backend/app/services/extraction_exporter.py backend/app/cli/export_extraction_run.py backend/tests/test_extraction_exporter.py docs/guides/llm-extraction-and-evaluation.md
git commit -m "feat: 支持抽取运行的可审计导出"
```

### Task 9：迁移并注册 Golden v2

**Files:**

- Create: `backend/app/services/golden_registry.py`
- Create: `backend/app/cli/migrate_golden_v2.py`
- Create: `data/evaluation/golden/v2/manifest.json`
- Create: `data/evaluation/golden/v2/*.golden.json`
- Test: `backend/tests/test_golden_registry.py`
- Test: `backend/tests/test_golden_migration.py`

**Step 1：写失败测试**

覆盖：

- Golden manifest 的文件 hash 与实际内容一致；
- 每个 Document content hash 能在导入包/SQLite 中解析且文本一致；
- evidence `[start,end)` 能精确切出 evidence text；
- Golden 中不存在作为 identity 的 `chunk_id`；
- 同一 Golden 版本不可静默覆写，内容变化必须升版本；
- 标注政策必须定义实体别名、大小写、关系方向、证据宽容度和不确定项处理。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_golden_registry.py backend/tests/test_golden_migration.py -v
```

Expected：FAIL。

**Step 2：实现旧 Golden 到 v2 的显式迁移**

迁移脚本只做可证明转换：chunk 局部 offset 可通过原 chunk 的全文起点还原时才迁移；无法证明的项输出到 review queue，不得猜测。人工复核后才生成正式 v2。

**Step 3：注册 Golden，而不是复制标准答案进运行表**

SQLite `golden_sets` 只保存 manifest identity、路径、hash、版本、annotation policy 和注册时间。评测开始时校验文件 hash，再加载标准答案；这样 Git 中 Golden 可评审，运行记录仍能追溯。

**Step 4：通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_golden_registry.py backend/tests/test_golden_migration.py -v
```

Expected：PASS，且迁移报告列出自动迁移数量和待人工复核数量。

**Step 5：提交**

```bash
git add backend/app/services/golden_registry.py backend/app/cli/migrate_golden_v2.py data/evaluation/golden/v2 backend/tests/test_golden_registry.py backend/tests/test_golden_migration.py
git commit -m "feat: 建立文档级 Golden v2 注册机制"
```

### Task 10：实现文档级、多作用域评测器

**Files:**

- Create: `backend/app/services/evaluation/__init__.py`
- Create: `backend/app/services/evaluation/matcher.py`
- Create: `backend/app/services/evaluation/metrics.py`
- Create: `backend/app/services/evaluation/evaluator.py`
- Create: `backend/app/models/evaluation.py`
- Modify and eventually retire: `backend/app/services/extraction_evaluator.py`
- Modify: `backend/tests/test_extraction_evaluator.py`
- Test: `backend/tests/evaluation/test_matcher.py`
- Test: `backend/tests/evaluation/test_metrics.py`
- Test: `backend/tests/evaluation/test_evaluator.py`

**Step 1：先用最小真值表写指标测试**

固定例：Golden 4 项，预测命中 3 项、误报 2 项，则 `TP=3, FP=2, FN=1, P=0.6, R=0.75, F1=2/3`。覆盖空集边界并明确：

- 双方为空：support 为 0，P/R/F1 返回 `null`，不伪造 1.0；
- 仅预测为空：R=0，P=`null`；
- 仅 Golden 为空：P=0，R=`null`；
- micro 指标为主；macro 仅在每组 support 可见时提供。

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_metrics.py -v
```

Expected：FAIL。

**Step 2：写 matcher 失败测试并冻结匹配政策**

实体默认 identity：`canonical_type + normalized_name`；别名匹配由 Golden 标注政策控制。关系默认 identity：`source canonical identity + relation type + target canonical identity + direction`。证据评测单独报告 exact/overlap，不用 evidence 文本差异直接推翻已定义的语义 TP，除非课程要求将证据设为硬门槛。

关系指标必须包含：

- `relation_e2e`：端点和关系均正确；
- `relation_conditional`：只在两个端点均已正确对齐的子集上比较关系类型/方向；
- `evidence_exact` 与 `evidence_overlap`。

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_matcher.py -v
```

Expected：FAIL。

**Step 3：实现两作用域评测并迁移旧入口**

同一 run 生成：

```text
scope=raw_emission
scope=validated_candidate
```

每个 scope 均按 Document 聚合、还原全文 offset、确定性去重/匹配，输出实体总体/分类型、关系总体/分类型、证据、拒绝原因和重复率。主指标不得把 rejected candidate 从 raw scope 中抹掉。将现有 `extraction_evaluator.py` 的已验证匹配判例迁到新包；过渡期只保留兼容导入，后续删除旧实现，禁止两套算法并存。

**Step 4：通过全部评测单元测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_matcher.py backend/tests/evaluation/test_metrics.py backend/tests/evaluation/test_evaluator.py -v
```

Expected：PASS。

**Step 5：提交**

```bash
git add backend/app/services/evaluation backend/app/services/extraction_evaluator.py backend/app/models/evaluation.py backend/tests/evaluation backend/tests/test_extraction_evaluator.py
git commit -m "feat: 添加文档级多作用域黄金集评测"
```

### Task 11：持久化 evaluation run 并提供确定性导出

**Files:**

- Create: `backend/app/repositories/evaluation_runs.py`
- Create: `backend/app/services/evaluation/exporter.py`
- Create: `backend/app/cli/run_evaluation.py`
- Test: `backend/tests/evaluation/test_repository.py`
- Test: `backend/tests/evaluation/test_exporter.py`
- Test: `backend/tests/evaluation/test_cli.py`

**Step 1：写失败测试**

evaluation run 必须持久化：

```text
evaluation_run_id
golden_set_id + version + manifest_hash
prediction_run_id + prediction_snapshot_hash
document_content_hashes
matching_policy_version + evaluator_version
code_commit_sha
status + started_at + finished_at
per-scope TP/FP/FN/P/R/F1/support
token/cost/latency summary
all match details and error categories
```

同一 identity 重跑可复用或生成显式 attempt，不得静默覆盖。Golden hash 或 prediction snapshot 变化必须产生新 run identity。

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_repository.py backend/tests/evaluation/test_exporter.py backend/tests/evaluation/test_cli.py -v
```

Expected：FAIL。

**Step 2：实现事务性写入和导出**

`evaluation-result.json` 只从数据库导出，通过 Task 2 Schema，包含 summary、by_type、by_document、matches、errors 与 provenance。基线目录中的结果必须与 manifest hash 一致。

**Step 3：通过测试并验证确定性**

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_repository.py backend/tests/evaluation/test_exporter.py backend/tests/evaluation/test_cli.py -v
docker compose run --rm backend python -m app.cli.run_evaluation --golden-set <fixture-golden> --prediction-run <fixture-run> --output /tmp/eval-a
docker compose run --rm backend python -m app.cli.run_evaluation --golden-set <fixture-golden> --prediction-run <fixture-run> --output /tmp/eval-b
diff -r /tmp/eval-a /tmp/eval-b
```

Expected：测试通过；除 run 时间/attempt 明确排除在内容 hash 外，两个导出一致。

**Step 4：提交**

```bash
git add backend/app/repositories/evaluation_runs.py backend/app/services/evaluation/exporter.py backend/app/cli/run_evaluation.py backend/tests/evaluation
git commit -m "feat: 持久化并导出评测运行"
```

### Task 12：实现评测 API，禁止伪造验收状态

**Files:**

- Create: `backend/app/api/routes/evaluations.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models/evaluation.py`
- Test: `backend/tests/test_evaluations_api.py`

**Step 1：写失败 API 测试**

按 `docs/api-contract.md` 覆盖：

- `POST /api/v1/evaluation/preflight`：校验 Golden、prediction、Document hash 和可评测范围，不落库；
- `POST /api/v1/evaluation/run`：沿用现有契约入口，创建评测运行并返回真实 run ID/status；
- `GET /api/v1/evaluation/summary`：沿用现有契约入口，返回最新批准基线或指定 run summary，不能返回 hard-coded 数字；
- `GET /api/v1/evaluation/runs`：分页列出真实运行及 provenance；
- `GET /api/v1/evaluation/runs/{run_id}`：返回 summary 和作用域指标；
- `GET /api/v1/evaluation/runs/{run_id}/matches`：分页返回 TP/FP/FN 明细与原因；
- `GET /api/v1/evaluation/runs/{run_id}/export`：导出或返回已生成 artifact；
- Golden hash 不匹配、prediction 不完整、文档版本不一致分别返回稳定错误码；
- 不允许用 hard-coded “PQA 通过”替代真实运行。

```bash
docker compose run --rm backend python -m pytest backend/tests/test_evaluations_api.py -v
```

Expected：FAIL。

**Step 2：实现最小 API 与错误模型**

长运行可先同步实现，但 status 模型必须兼容异步；如果同步超时风险已存在，改为后台任务时仍要确保状态先写数据库。所有响应字段与契约一致。

**Step 3：通过测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_evaluations_api.py -v
```

Expected：PASS。

**Step 4：提交**

```bash
git add backend/app/api/routes/evaluations.py backend/app/api/routes/__init__.py backend/app/main.py backend/app/models/evaluation.py backend/tests/test_evaluations_api.py
git commit -m "feat: 提供真实评测运行 API"
```

### Task 13：前端切换到真实评测数据并展示可解释指标

**Files:**

- Modify: `frontend/src/pages/EvaluationPage.tsx`
- Create: `frontend/src/api/evaluations.ts`
- Create: `frontend/src/types/evaluation.ts`
- Delete or demote: `frontend/src/data/mockEval.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Test: `frontend/src/pages/EvaluationPage.test.tsx`
- Test: `frontend/src/api/evaluations.test.ts`

**Step 1：写失败测试**

页面必须展示：

- Golden ID/版本/hash、prediction run、模型、chunk set、时间和运行状态；
- `validated_candidate` 主指标及 TP/FP/FN/support；
- `raw_emission` 指标、拒绝率、重复率；
- 实体、关系端到端、条件关系和证据指标；
- 按类型/文档明细和 TP/FP/FN 错误列表；
- 空数据、加载失败、运行未完成、指标分母为 0 的明确状态；
- 页面不得在 API 失败时静默回退成 mock “通过”。

```bash
npm --prefix frontend run test -- EvaluationPage
```

Expected：FAIL。

**Step 2：实现 API client、类型和页面**

保留 mock 仅可作为测试 fixture，并改名到 test fixtures；生产 bundle 不得 import。P/R/F1 显示分子分母或 TP/FP/FN，避免单一百分比误导。若现有 Vitest 缺少组件渲染环境，显式加入 `@testing-library/react`、`@testing-library/jest-dom` 和 `jsdom`，并提交 lockfile，不能用“无测试也通过”替代页面测试。

**Step 3：运行前端验证**

```bash
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run format:check
```

Expected：全部 PASS。

**Step 4：提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/pages/EvaluationPage.tsx frontend/src/api/evaluations.ts frontend/src/types/evaluation.ts frontend/src/pages/EvaluationPage.test.tsx frontend/src/api/evaluations.test.ts frontend/src/data/mockEval.ts
git commit -m "feat: 展示真实抽取评测结果"
```

### Task 14：建立可复现基线包与 CI 验收门禁

**Files:**

- Create: `backend/app/cli/build_evaluation_baseline.py`
- Create: `data/evaluation/baselines/<baseline_id>/manifest.json`
- Create: `data/evaluation/baselines/<baseline_id>/evaluation-result.json`
- Create: `backend/tests/evaluation/test_baseline_bundle.py`
- Create: `.github/workflows/ci.yml`
- Modify: `docs/guides/llm-extraction-and-evaluation.md`

**Step 1：定义基线 manifest 并写失败测试**

manifest 至少包括：

```text
baseline_id + created_at + reviewed_by
dataset/document hashes
golden identity/hash
prediction run identity/snapshot hash
provider/model/config/prompt/schema/matrix/chunker identities
code commit SHA
evaluation result hash
reproduction command
known limitations
```

基线测试验证所有 hash、Schema、引用文件和 reproduction metadata。CI 不调用付费外部模型，只重放已审核的脱敏响应 fixture 或固定 prediction snapshot。

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_baseline_bundle.py -v
```

Expected：FAIL。

**Step 2：将旧 PQA 结果分类**

- 具备完整输入/输出/脚本/provenance：可迁成正式 baseline，但要通过新 Schema。
- 缺任一关键项：放入 `data/legacy/evaluation/`，manifest 标记 `status=historical_observation`，报告中不得声称可复现验收。

**Step 3：生成首个可复现基线**

```bash
docker compose run --rm backend python -m app.cli.build_evaluation_baseline --evaluation-run <run-id> --baseline-id <baseline-id>
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_baseline_bundle.py -v
```

Expected：生成 manifest/result，测试 PASS。

**Step 4：增加非回归门禁**

初始门禁只检查：bundle 可重放、指标计算一致、无字段漂移。性能阈值在至少两个可信基线后再启用；启用时同时约束：

- 关系端到端 F1 不低于批准阈值；
- raw rejection/duplicate rate 不超过阈值；
- support 不得减少；
- 不得通过删除困难样本换取 F1 上升。

**Step 5：提交**

```bash
git add backend/app/cli/build_evaluation_baseline.py data/evaluation/baselines backend/tests/evaluation/test_baseline_bundle.py .github/workflows docs/guides/llm-extraction-and-evaluation.md
git commit -m "test: 建立可复现评测基线与门禁"
```

### Task 15：执行切块消融实验并形成项目价值证据

**Files:**

- Create: `configs/evaluation/chunk-ablation.yaml`
- Create: `backend/app/cli/run_chunk_ablation.py`
- Create: `docs/reports/llm-chunk-ablation.md`
- Create: `data/reports/llm-chunk-ablation.summary.json`
- Test: `backend/tests/evaluation/test_chunk_ablation.py`

**Step 1：冻结实验问题和假设**

主问题：确定性切块和 overlap 是否在不造成不可接受精度、重复、成本与时延损失的情况下提升实体/关系召回。

同一批 Golden Documents、同一模型、同一 prompt/schema/matrix，比较：

| 实验组 | 策略 | 初始参数 |
| --- | --- | --- |
| A | 全文单次 | 文档未超模型限制时使用全文 |
| B | 段落切块，无 overlap | `max_chars=6000, overlap=0` |
| C | 段落切块，有 overlap | `max_chars=6000, overlap=600` |

后续可增加 3000/9000 字符，但首轮只做三组，避免参数搜索污染结论。至少使用当前 6 篇 Golden；若每组 support 太低，报告必须明确“探索性结果”，不能外推。

**Step 2：写失败测试**

- 三组引用完全相同的 document hashes 和 Golden hash；
- 除 chunk config 外模型参数相同；
- 输出包含逐文档与总体的实体/关系 P/R/F1、raw/validated、重复率、拒绝率、tokens、估算成本和 latency；
- runner 支持从已存 raw response 重算候选/评测；
- 失败或 partial run 不进入均值，必须单列。

```bash
docker compose run --rm backend python -m pytest backend/tests/evaluation/test_chunk_ablation.py -v
```

Expected：FAIL。

**Step 3：实现实验 runner**

先用 mock/provider fixture 验证编排；真实 API 调用必须显式传 `--allow-paid-provider`，先预估请求数和 token 上限，经人工确认后执行。不得把 API Key 写入配置或 artifact。

**Step 4：运行正式实验并输出报告**

```bash
docker compose run --rm backend python -m app.cli.run_chunk_ablation --config configs/evaluation/chunk-ablation.yaml --preflight
docker compose run --rm backend python -m app.cli.run_chunk_ablation --config configs/evaluation/chunk-ablation.yaml --allow-paid-provider
```

报告必须包含：

- 数据集/Golden/代码/模型/参数身份；
- 各组 TP/FP/FN/P/R/F1/support；
- 逐文档差异，不只给平均数；
- 若有重复运行，给均值、标准差和样本数；若只有一次，不假装有统计显著性；
- chunk boundary、跨块关系、重复候选、证据错位等错误分类；
- “召回提升是否值得额外成本”的结论及下一轮单变量改动。

**Step 5：提交**

```bash
git add configs/evaluation/chunk-ablation.yaml backend/app/cli/run_chunk_ablation.py backend/tests/evaluation/test_chunk_ablation.py docs/reports/llm-chunk-ablation.md data/reports/llm-chunk-ablation.summary.json
git commit -m "test: 记录 LLM 切块消融实验"
```

### Task 16：把迭代证据纳入课程报告并完成全量验证

**Files:**

- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `docs/stage-roadmap.md`
- Modify: `docs/guides/llm-extraction-and-evaluation.md`
- Modify: `docs/reports/llm-extraction-baseline.md`
- Create: `docs/reports/llm-evaluation-iteration-log.md`

**Step 1：建立迭代日志模板**

每轮只追加，不覆盖历史。模板：

```markdown
## Iteration <n> — <date>

- 问题/假设：
- 唯一改动变量：
- 数据集与 Golden：ID、version、hash、support
- 模型与运行配置：
- 基线 run / 新 run：
- 指标差异：实体、关系 e2e、关系 conditional、证据、raw rejection、duplicate、cost、latency
- TP/FP/FN 典型案例：
- 结论：支持 / 不支持 / 证据不足
- 风险与限制：
- 下一轮动作及停止条件：
```

报告中应把该链路解释为项目价值：系统不仅“能调用 LLM”，还能够追溯文档、控制 Schema、审计证据、量化错误、验证切块策略并防止回归。课程价值来自可复现工程闭环，而不是某一次孤立的高 F1。

**Step 2：更新 README、Roadmap、TODO 和指南**

- README 展示真实链路和复现入口；
- Roadmap 把“有脚本”与“有可复现基线”分开标记；
- TODO 只勾选实际完成项；
- 指南给出 Document 导入 -> extraction run -> Golden registration -> evaluation run -> baseline/export 的唯一命令路径；
- 现有 `llm-extraction-baseline.md` 保留 2026-07-13 历史结果及其限制，增加其 baseline status、可复现性缺口和新基线链接，不改写历史数字；
- 删除或显著标记已过时的“旧版真实抽取评测指南”。

**Step 3：运行全量后端验证**

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

Expected：全部 PASS，无 skipped 核心评测测试。

**Step 4：运行全量前端验证**

```bash
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run format:check
```

Expected：全部 PASS。

**Step 5：执行仓库与敏感信息检查**

```bash
git diff --check
git status --short
git grep -n -I -E "(sk-[A-Za-z0-9_-]{20,}|Authorization: Bearer|DEEPSEEK_API_KEY=.+)" -- . ':!docs/plans/*'
```

Expected：无 whitespace error；只有预期文件；敏感信息检查无真实凭据命中。

**Step 6：最终提交**

```bash
git add README.md TODO.md docs/stage-roadmap.md docs/guides/llm-extraction-and-evaluation.md docs/reports
git commit -m "docs: 补充 LLM 评测迭代与课程价值说明"
```

## 4. 推荐 PR 拆分与评审顺序

不要把全部任务重新堆成一个无法评审的大 PR。建议按依赖拆成 5 个 PR；每个 PR 都指向前一个已合入 PR 的 `main`：

| PR | 范围 | 对应任务 | 必须评审方 | 合入条件 |
| --- | --- | --- | --- | --- |
| A | ADR、数据/API 契约、Schema、关系矩阵、目录政策 | 1-3 | 架构与数据规范组 + LLM 组 | 契约测试通过，术语无歧义 |
| B | SQLite 迁移、Document 导入、确定性切块 | 4-5 | 架构与数据规范组 | 旧库可升级，切块可重复 |
| C | 原始响应、候选审计、正式抽取、导出 | 6-8 | LLM 组 + 架构组 | 原始响应可重放，JSON 为派生物 |
| D | Golden v2、评测器、持久化、API、前端 | 9-13 | QA 组 + LLM 组 + 前端组 | 指标真值表/API/页面测试通过 |
| E | 基线门禁、切块实验、课程报告 | 14-16 | QA 组 + 课程报告负责人 | 基线可复现，实验限制披露完整 |

若 PR #33 未合入，先处理它；不要在 PR A-E 中夹带重复的 `clean_text` 修复。旧 PR 已合入后的新问题应在旧 PR 留追踪回复/链接，但修复必须新开 PR，避免改写已合入历史。

## 5. 指标解释、课程要求与项目价值判定

### 5.1 什么指标才有价值

- **必须有 support 和 TP/FP/FN**：只给 P/R/F1 不能判断 1 个样本与 100 个样本的差别。
- **关系端到端 F1 是核心业务指标**：项目目标是威胁知识图谱，只有实体准确而关系错误，图谱价值有限。
- **条件关系 F1 用于诊断**：它回答“端点已识别正确后，关系分类是否仍然失败”，但不能代替端到端指标。
- **raw 与 validated 差距体现治理价值**：差距过大说明系统主要靠后处理兜底；两者共同改善才说明模型与工程同时优化。
- **成本、时延、重复率是必要约束**：切块召回增加但请求成本翻倍、重复候选暴增时，不能简单判定为更优。
- **逐类型与逐文档结果防止平均数掩盖问题**：尤其要单列低频关系和跨块关系。

### 5.2 什么结论暂时不能说

- 6 篇 Golden 可以证明链路可用并做探索性对比，不能证明对所有威胁情报材料泛化。
- 单次非确定性模型运行不能证明稳定提升；至少固定可用 seed/temperature，或重复运行并报告方差。
- 人工复核示例不能冒充模型原始输出；历史 PQA 数字不能冒充可复现验收。
- 评测器与 Golden 若由同一提示词自动生成且没有独立人工复核，会产生同源偏差。

### 5.3 课程报告建议叙事

1. **问题**：非结构化威胁情报不能直接进入知识图谱，LLM 输出又存在格式、幻觉、证据和重复问题。
2. **架构**：以 SQLite 为事实源，用 Document hash、chunk set、raw response、candidate audit 和 Golden version 建立可追溯链路。
3. **方法**：Schema + 关系矩阵 + 证据校验 + 文档级 Golden 评测。
4. **实验**：严格控制变量比较全文与切块策略，并报告准确性、召回、成本和错误类型。
5. **迭代**：每轮从 FP/FN 分类提出一个可证伪假设，记录 baseline/new run 和决策。
6. **价值**：把“一次模型演示”提升为可审计、可优化、可回归验证的工程系统。

## 6. 风险、停止条件与回退策略

| 风险 | 触发信号 | 处理/停止条件 |
| --- | --- | --- |
| PR #33 重叠冲突 | 同时改 `offline_extraction_pipeline.py` | 停止实施重叠任务，先决定合入/放弃，不手工拼接未评审逻辑 |
| Golden 迁移证据不足 | 无法从旧 chunk 还原全文 offset | 进入人工 review queue；禁止猜 offset 或自动接受 |
| SQLite 迁移损坏旧数据 | 行数/hash 前后不一致 | 事务回滚，用旧库副本重现；未通过备份恢复测试不得合入 |
| provider 原始响应含敏感信息 | prompt/response 出现隐私或凭据 | 默认不导出；先脱敏和增加检测，再允许固化 fixture |
| 评测匹配政策争议 | 同一预测在不同人判断下 TP/FP 不一致 | 暂停性能结论，先版本化 annotation/matching policy 并补判例测试 |
| 样本量过小 | 分类型 support < 5 或总体仅 6 文档 | 只写探索性结论，不设置强性能门禁 |
| 切块成本失控 | preflight 超出预算或请求数异常 | 不执行付费运行；先调整实验规模并记录预算上限 |
| 前端先于 API 造假数据 | API 错误时显示“通过” | 测试必须失败；禁止 mock fallback 进入生产代码 |
| JSON 与 DB 漂移 | 同 run 导出 hash 不稳定 | 阻断基线发布，修复排序/版本/provenance 后重导 |

回退原则：每个 PR 只做其表格范围；数据库迁移只允许前向修复，应用层可通过 feature flag 暂时隐藏新入口，但不得删除已记录的 raw response、candidate audit 或 evaluation run。

## 7. 最终交付物清单

- [ ] 一份经评审的 LLM 抽取与评测 ADR。
- [ ] 更新后的 architecture/data/API 契约与机器可读关系矩阵。
- [ ] Golden v2、candidate audit、extraction run、evaluation result Schema。
- [ ] 唯一 SQLite 初始化/迁移入口及升级测试。
- [ ] 确定性 Document importer/chunker 与全文 offset。
- [ ] 可重试的 per-chunk provider runner 和原始响应审计。
- [ ] raw emission、validated candidate、accepted extraction 三层可追溯数据。
- [ ] SQLite 派生的 extraction/audit/evaluation exports。
- [ ] 文档级 Golden v2 registry 和迁移 review queue。
- [ ] 双作用域实体/关系/证据评测器与指标真值表。
- [ ] 真实 evaluation API 和不回退 mock 的前端页面。
- [ ] 可重放、带 manifest/hash 的首个 baseline bundle。
- [ ] 全文/无重叠/有重叠三组切块消融实验。
- [ ] 持续追加的 LLM 评测迭代日志和课程报告章节。
- [ ] 后端、前端、契约、Schema、敏感信息和 diff 全量验证记录。

## 8. 实施顺序总览

```text
PR #33 决策
  -> 契约/ADR/Schema/目录
  -> SQLite 迁移
  -> Document 导入与确定性切块
  -> 原始响应持久化
  -> 候选审计与正式抽取
  -> Golden v2
  -> 双作用域评测与结果持久化
  -> API/前端
  -> 可复现基线门禁
  -> 切块消融
  -> 课程报告与持续迭代日志
```

该顺序不可把 Golden/评测提前建立在未冻结的 Document/chunk/extraction identity 上；否则后续每次切块或 Schema 变更都会让历史指标失去可比性。
