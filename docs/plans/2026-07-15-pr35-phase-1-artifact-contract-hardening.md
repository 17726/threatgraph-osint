# PR35 第一阶段 LLM 工件契约加固 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 PR35 现有版本化命名改动上修复会阻断合入的身份、时间和关联校验问题，并明确它只交付第一阶段工件契约，不提前实现完整实验运行包。

**Architecture:** 第一阶段继续使用独立 JSON 文件表达抽取、候选审计、Golden 和评测导出，但以 JSON 字段中的 `run_id` 为权威身份，文件名只承担可读标签。SQLite 继续承载运行时图谱事实，Neo4j 只接收 SQLite canonical graph 的可重建投影；Provider Raw Response、Manifest、Chunk-independent Golden v2 和多作用域评测留到后续独立 PR。

**Tech Stack:** Python 3、JSON Schema Draft 2020-12、jsonschema、pytest、SQLite、Neo4j 5 Community、GitHub Pull Request。

---

## 0. 本次边界

本次直接在 PR35 分支 `codex/llm-versioned-artifacts` 实施，不创建 worktree，原因是项目负责人已明确要求直接使用现有工作区和 PR 分支。

本次必须完成：

1. 合并最新 `main`，保留已合入的前端改动。
2. 时间处理拒绝没有时区的 datetime/ISO 字符串，避免不同主机生成不同 UTC 标签。
3. `run_id` 在可读标签之外增加不可碰撞后缀，时间戳不再承担唯一身份。
4. JSON Schema 的 `date-time` 使用 `FormatChecker` 真正执行格式校验。
5. Golden 的 `language` 成为必填字段，因为正式文件名依赖它。
6. Candidate Audit 与 Extraction Result 同时校验 `doc_id` 和 `run_id`。
7. Prompt 文件名与 `prompt_version=1.0` 保持一致，不再继续使用 `extract-v1.md`。
8. 文档明确 PR35 只提交经选择的实验制品，不要求所有本地运行进入 Git。
9. 文档明确 SQLite 与 Neo4j 的主从关系和故障恢复路径。

本次不完成：

1. Provider Raw Response 与 Provider Attempt 持久化。
2. 每个 Run 的目录和 Manifest。
3. Run Configuration/Fingerprint/内容哈希体系。
4. Golden v2 与切块无关的全文坐标。
5. `raw_emission`、`validated_candidate`、`accepted_graph` 多作用域指标。
6. SQLite 新增评测明细表和历史数据迁移。
7. Neo4j 同步和 Cypher 路径查询实现。

## Task 1：补运行身份和 UTC 失败测试

**Files:**

- Create: `backend/tests/test_artifact_naming.py`
- Modify: `backend/tests/test_llm_service.py`

**Step 1：写拒绝无时区时间的测试**

覆盖 `iso_timestamp()`、`filename_timestamp()` 和 `timestamp_from_iso()`，传入 naive datetime 或不带 UTC offset 的 ISO 字符串时应抛出 `ValueError`。

**Step 2：写 Run ID 唯一性测试**

相同 Document、模型、Prompt、Schema 和时间戳连续生成两个 Run ID，断言可读前缀一致但完整 ID 不相同，并符合 Schema 正则。

**Step 3：运行测试确认失败**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_artifact_naming.py -v
```

Expected：naive datetime 未被拒绝，或相同参数得到相同 Run ID，因此测试失败。

## Task 2：最小实现身份与 UTC 加固

**Files:**

- Modify: `backend/app/services/artifact_naming.py`
- Modify: `backend/app/services/llm_service.py`
- Modify: `docs/schemas/extraction-result.schema.json`
- Move: `docs/prompts/extract-v1.md` -> `docs/prompts/extract-1.0.md`
- Modify: `data/examples/extraction_result.apt28.thn.beardshell.example.json`
- Move: `data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760.json` -> `data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json`

**Step 1：实现统一 aware datetime 校验**

增加私有函数检查 `tzinfo` 和 `utcoffset()`，所有 UTC 转换入口复用该函数。

**Step 2：给 Run ID 增加唯一后缀**

默认使用 UUID 的短十六进制后缀，保留 Document、模型、Prompt、Schema 和 UTC 时间戳作为展示标签。

**Step 3：同步 Schema 和已提交示例**

Run ID 正则增加短十六进制后缀；现有人工示例使用固定后缀，避免测试资产每次变化。

**Step 4：同步 Prompt 文件身份**

运行时加载 `docs/prompts/extract-1.0.md`，并由测试断言默认文件名与 `prompt_version=1.0` 一致。

**Step 5：运行测试确认通过**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_artifact_naming.py backend/tests/test_llm_service.py -v
```

Expected：PASS。

## Task 3：补 Golden 和 Candidate Audit 绑定失败测试

**Files:**

- Modify: `backend/tests/test_extraction_evaluator.py`
- Modify: `backend/tests/test_validate_extraction_result.py`

**Step 1：写 Golden language 必填测试**

删除 `language` 后调用 Golden Schema 校验，断言返回包含 `language` 的错误。

**Step 2：写 date-time 格式测试**

将 Extraction Result 的 `generated_at` 改成无时区或非法日期，断言契约校验失败。

**Step 3：写 Candidate Audit Run ID 不一致测试**

保持 `doc_id` 一致但修改 `candidate_audit.run_id`，断言 evaluator 拒绝评测。

**Step 4：运行测试确认失败**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_extraction_evaluator.py backend/tests/test_validate_extraction_result.py -v
```

Expected：至少上述新增测试失败。

## Task 4：实现 Schema 格式和跨文件绑定校验

**Files:**

- Modify: `docs/schemas/golden.schema.json`
- Modify: `backend/app/services/extraction_evaluator.py`
- Modify: `scripts/validate_extraction_result.py`

**Step 1：要求 Golden language**

把 `language` 加入 Golden 顶层 `required`。

**Step 2：启用 JSON Schema FormatChecker**

Extraction 和 Golden 的校验器统一传入 `FormatChecker()`，确保 `format: date-time` 不只是注释。

**Step 3：校验 Candidate Audit Run ID**

Candidate Audit 存在时要求其 `run_id` 与 Extraction Result 完全一致；历史缺失字段不得静默当作匹配。

**Step 4：运行相关测试**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_extraction_evaluator.py backend/tests/test_validate_extraction_result.py -v
```

Expected：PASS。

## Task 5：收敛第一阶段文档边界

**Files:**

- Modify: `README.md`
- Modify: `TODO.md`
- Modify: `docs/architecture.md`
- Modify: `docs/data-contract.md`
- Modify: `docs/guides/llm-extraction-and-evaluation.md`
- Modify: `docs/plans/2026-07-14-llm-extraction-evaluation-architecture-closure.md`

**Step 1：定义 Git 实验归档范围**

把“所有正式运行提交 Git”收窄为“Promoted Experiment 和已审核 Baseline 提交 Git”；普通 Attempt 和本地调试运行留在运行时存储或本地制品目录。

**Step 2：定义 PR35 与后续阶段**

明确 PR35 只提供版本、命名和最小关联契约；完整 Run Bundle、Raw Response、Hash、Chunk v2 和多层指标由后续 PR 实现。

**Step 3：明确 SQLite 与 Neo4j 边界**

SQLite 保存 canonical graph、证据、导入状态和同步水位；Neo4j 保存可由 SQLite 重建的查询投影，负责多维度查询、关键路径和图算法。任何写入先落 SQLite，再按增量事件同步 Neo4j；Neo4j 故障不反向污染 SQLite。

**Step 4：检查文档一致性**

```bash
git diff --check
```

Expected：无空白错误，且没有把 Neo4j 描述为 LLM 输出的直接写入目标。

## Task 6：完整验证、提交和更新 PR35

**Files:**

- Verify: all files changed by PR35

**Step 1：运行后端测试**

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

Expected：全部通过。

**Step 2：运行 JSON 和离线契约校验**

```bash
docker compose run --rm backend python -m compileall backend scripts -q
docker compose run --rm backend python scripts/validate_extraction_result.py data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json --document data/examples/document.apt28.thn.beardshell.example.json --json
```

Expected：编译通过，样例校验返回 `ok`。

**Step 3：审查差异和敏感信息**

```bash
git diff --check
git status --short
git diff main...HEAD
```

Expected：只有 PR35 第一阶段范围内的代码、测试、数据和文档变更。

**Step 4：提交**

```bash
git add backend docs data scripts README.md TODO.md
git commit -m "fix: 加固 LLM 工件身份与关联契约"
```

**Step 5：推送并更新 PR35**

```bash
git push origin codex/llm-versioned-artifacts
```

Expected：PR35 指向新提交，检查通过后使用 squash 或 merge 合入；后续阶段另开 PR，不继续扩大 PR35。
