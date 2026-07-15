# PR36 替代修复：LLM 工件命名校验 Implementation Plan

**Goal:** 从最新 `main` 实现 Extraction、Candidate Audit、Golden 和 Evaluation 正式工件的文件名与 JSON payload 一致性校验，以一个最小、可评审的新 PR 替代 PR #36。

**Architecture:** JSON 内的 `run_id` 是运行权威身份，文件名只承担可读标签并必须与 payload 一致；校验保留 PR #35 已确定的 20 位 UTC 标签和 8 位随机后缀。正式输入默认严格校验，历史示例仅能通过显式 `--allow-legacy-artifacts` 跳过文件名格式检查，Schema、Document、`doc_id` 和 `run_id` 关联校验仍然执行。本 PR 不引入 Candidate Audit 新 Schema、全局 catalog、Run Manifest、多文档 Golden、评测口径调整、Docker 数据复制或 CI 自动提交。

**Tech Stack:** Python 3.13、pytest、JSON Schema Draft 2020-12、Docker Compose、GitHub Pull Request。

---

## 0. 执行边界

本计划直接在当前工作区的 `fix/llm/artifact-validation` 分支执行，不创建 worktree；项目负责人此前已明确要求直接使用现有工作区。

本 PR 必须完成：

1. 正式 Extraction 文件名必须等于 `<run_id>.json`，且 `run_id` 的可读前缀必须与 `doc_id`、模型、Prompt、Schema 和 `generated_at` 一致。
2. 正式 Candidate Audit 文件名必须等于 `<run_id>-candidate-audit.json`，并继续校验其与 Extraction 的 `run_id`、`doc_id` 一致。
3. 正式 Golden 保持单 Document 文件名：`golden-<language>-<doc_id>-<schema_version>-<golden_version>.json`。
4. 正式 Evaluation 文件名必须与 extraction/golden 元数据及 `evaluated_at` 一致。
5. Legacy 只能由调用方显式开启；开启后只跳过文件名格式，不跳过 payload、Schema 和跨工件关联校验。
6. LLM 保存入口和独立评测 CLI 在写入正式工件前调用同一套校验函数。

本 PR 明确不完成：

1. 不修改“Rejected 一律计入当前 raw 指标的 FP”历史口径；该问题另开评测语义 Issue。
2. 不新增或冻结 Candidate Audit Schema。
3. 不实现 Provider Raw Response、Provider Attempt、Run Bundle 或 `manifest.json`。
4. 不新增全局 `index.json`、catalog 或自动生成数据 README。
5. 不实现多文档 Golden；实验数据集编组留给 Dataset/Experiment Manifest。
6. 不迁移现有 6 篇 Golden 到全文坐标 Golden v2。
7. 不修改 Docker 数据复制和 GitHub Actions。

## Task 1：补正式工件命名失败测试

**Files:**

- Modify: `backend/tests/test_artifact_naming.py`
- Test: `backend/tests/test_artifact_naming.py`

**Step 1：写 Extraction 校验测试**

增加以下行为测试：

- 带 8 位随机后缀的正式 Extraction 文件通过；
- 文件名不是 `<run_id>.json` 时失败；
- `run_id` 可读前缀与 payload 元数据不一致时失败；
- `generated_at` 无时区时失败；
- `allow_legacy=True` 只允许跳过文件名比较，仍检查 Run ID 元数据。

**Step 2：写 Candidate Audit、Golden、Evaluation 校验测试**

覆盖：

- Candidate Audit 文件名与 `run_id` 一致；
- Candidate Audit 与 Extraction 的 `run_id/doc_id` 不一致时失败；
- Golden 单文档正式文件名通过，多文档 payload 不作为正式单文件通过；
- Evaluation 文件名与 extraction/golden 元数据一致，且 `extraction.run_id` 必须与其中的文档、模型和版本一致；
- 非版本化 Evaluation 输出名失败。

**Step 3：运行测试确认 RED**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_artifact_naming.py -v
```

Expected：新增校验函数尚不存在，测试因 ImportError 或缺少行为而失败。

## Task 2：实现最小命名校验

**Files:**

- Modify: `backend/app/services/artifact_naming.py`
- Test: `backend/tests/test_artifact_naming.py`

**Step 1：实现 Run ID 元数据校验**

根据 payload 构造可读前缀：

```text
extract-<doc_id>-<model>-<prompt_version>-<schema_version>-<utc_timestamp>-
```

要求 `run_id` 使用该前缀并以 8 位小写十六进制随机后缀结束。校验阶段不重新生成 Run ID。

**Step 2：实现四类工件校验函数**

新增：

```python
validate_extraction_artifact_filename(...)
validate_candidate_audit_artifact_filename(...)
validate_golden_artifact_filename(...)
validate_evaluation_artifact_filename(...)
```

所有函数使用 `Path(path).name` 校验展示文件名，避免把目录作为身份字段。

**Step 3：运行测试确认 GREEN**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_artifact_naming.py -v
```

Expected：全部通过。

## Task 3：接入保存入口和评测 CLI

**Files:**

- Modify: `backend/app/services/llm_service.py`
- Modify: `scripts/evaluate_extraction_against_golden.py`
- Modify: `scripts/run_llm_extraction.py`
- Modify: `backend/tests/test_llm_service.py`
- Modify: `backend/tests/test_extraction_evaluator.py`

**Step 1：先写入口失败测试**

覆盖：

- `save_result()` 在 payload 的 Run ID 元数据不一致时拒绝写文件；
- `save_candidate_audit()` 在审计 payload 元数据不一致时拒绝写文件；
- 独立评测 CLI 默认拒绝示例/历史文件名；
- 显式 `--allow-legacy-artifacts` 后，示例文件仍需通过 Schema 和关联校验；
- Candidate Audit 即使以 Legacy 模式输入，跨 Run 仍失败；
- 自定义 Evaluation 输出名不符合正式命名时失败。

**Step 2：运行入口测试确认 RED**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_llm_service.py backend/tests/test_extraction_evaluator.py -v
```

Expected：新增入口行为尚未实现，至少一个新增测试失败。

**Step 3：接入最小实现**

- `LLMExtractionService` 在写 Extraction/Candidate Audit 前校验 payload 和目标文件名；
- 独立评测 CLI 增加 `--allow-legacy-artifacts`；
- CLI 在加载后、评测前校验输入文件名，在写入前校验 Evaluation 输出名；
- `run_llm_extraction.py` 校验 Golden 输入和 Evaluation 输出；真实生成的 Extraction/Candidate Audit 由 service 保存入口负责校验。

**Step 4：运行入口测试确认 GREEN**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_llm_service.py backend/tests/test_extraction_evaluator.py -v
```

Expected：全部通过。

## Task 4：同步契约和指南

**Files:**

- Modify: `docs/data-contract.md`
- Modify: `docs/guides/llm-extraction-and-evaluation.md`
- Modify: `docs/schemas/README.md`
- Modify: `README.md`

**Step 1：明确文件名与字段职责**

文档写明：

- `run_id` 字段是权威身份；
- 文件名是可读标签并必须与 payload 一致；
- UTC 时间戳不是唯一身份；
- 正式 Golden 当前保持单 Document；
- Legacy 只能显式放行，不进入默认输入选择。

**Step 2：明确本 PR 不改变评测口径**

保留现状说明并标记限制：当前 evaluator 把 Candidate Audit 的 rejected 项追加到预测数量并计入 FP，这是历史 raw-like 指标，不是最终多作用域评测设计。后续必须拆分 raw emission、validated candidate 和 accepted graph 指标。

**Step 3：检查文档一致性**

```bash
git diff --check
```

Expected：无空白错误。

## Task 5：完整验证与发布

**Files:**

- Verify: all files changed by this branch

**Step 1：运行完整后端测试**

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

Expected：全部通过。

**Step 2：运行编译和正式样例校验**

```bash
docker compose run --rm backend python -m compileall backend scripts -q
docker compose run --rm backend python scripts/validate_extraction_result.py data/extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760-00000000.json --document data/examples/document.apt28.thn.beardshell.example.json --json
```

Expected：编译成功，Extraction 校验返回 `ok`。

**Step 3：检查差异和敏感信息**

```bash
git diff --check
git status --short
git diff main...HEAD
git grep -n -I -E "(sk-[A-Za-z0-9_-]{20,}|Authorization: Bearer|DEEPSEEK_API_KEY=.+)" -- . ':!docs/plans/*'
```

Expected：只有计划内文件；无真实凭据。

**Step 4：提交并推送**

```bash
git add docs/plans/2026-07-15-pr36-replacement-artifact-validation.md backend/app/services/artifact_naming.py backend/app/services/llm_service.py backend/tests/test_artifact_naming.py backend/tests/test_llm_service.py backend/tests/test_extraction_evaluator.py scripts/evaluate_extraction_against_golden.py scripts/run_llm_extraction.py README.md docs/data-contract.md docs/guides/llm-extraction-and-evaluation.md docs/schemas/README.md
git commit -m "fix: 校验 LLM 工件文件名与运行身份"
git push -u origin fix/llm/artifact-validation
```

**Step 5：创建替代 PR 并回链旧 PR**

- 新 PR 基于 `main`，说明替代 PR #36；
- PR body 写明 `Closes #34`；
- 在 PR #36 留下替代 PR 链接并关闭旧 PR；
- 新 PR 默认创建为 Draft，等待项目负责人确认后转 Ready。
