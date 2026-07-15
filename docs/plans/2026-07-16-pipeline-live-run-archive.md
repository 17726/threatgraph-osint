# Pipeline live 运行档案与 #47 工件迁移 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让前端显式发起的 `live` Pipeline 在写入 SQLite 前持久化 Extraction、Candidate Audit 和任务运行摘要，并审核迁移 PR #47 中能够通过当前契约的抽取工件。

**Architecture:** SQLite 仍是运行时 canonical 事实源；`data/run_artifacts` 保存本机未审核 live 候选输出，`data/run_logs` 保存与 Pipeline `job_id` 绑定的运行摘要，两者默认均被 Git 忽略。只有经审核选中的历史工件才迁入 `data/extracted`、登记显式审核清单并纳入 Git；Candidate Audit 缺失会记为评测溯源限制，不伪造空审计结果。

**Tech Stack:** Python 3.13、FastAPI、SQLite、pytest、JSON Schema、Docker Compose。

---

### Task 1: 用失败测试固定 live 档案语义

**Files:**

- Modify: `backend/tests/test_pipeline_service.py`
- Create: `backend/tests/test_pipeline_run_archive.py`

**Step 1: 写失败测试**

- live 成功时保留 `<run_id>.json` 和 `<run_id>-candidate-audit.json`。
- `pipeline-run-<job_id>.json` 记录 `running -> succeeded`、`run_id`、工件路径、SHA-256、LLM 观测与导入摘要。
- LLM 或导入失败时运行摘要保留 `failed` 和错误，已生成的 Extraction/Candidate Audit 不删除。
- 服务重启标记遗留 `running` 任务时，已存在的运行摘要同步改为中断失败。

**Step 2: 运行测试确认失败**

Run:

```powershell
docker compose run --rm backend python -m pytest `
  backend/tests/test_pipeline_run_archive.py `
  backend/tests/test_pipeline_service.py -v
```

Expected: 当前 live 使用临时目录并删除 Extraction，且没有 Candidate Audit / Pipeline run log，新测试失败。

### Task 2: 实现可恢复的 live 运行档案

**Files:**

- Create: `backend/app/services/pipeline_run_archive.py`
- Modify: `backend/app/services/pipeline_service.py`
- Test: `backend/tests/test_pipeline_run_archive.py`
- Test: `backend/tests/test_pipeline_service.py`

**Step 1: 实现最小档案服务**

- 使用临时文件 + `Path.replace()` 原子替换 JSON。
- 写入前调用现有 Extraction / Candidate Audit 文件名和元数据校验器。
- 运行摘要按 `job_id` 幂等覆盖，保存创建、完成时间和工件 SHA-256。
- 对外摘要使用稳定的仓库相对路径，不泄露宿主机绝对路径。

**Step 2: 让 PipelineService 绑定 job 和档案**

- 只对 `live` 启动运行档案。
- 给默认执行链传入 `job_id`，保持注入式测试 runner 的旧调用契约。
- LLM 成功后先持久化 Extraction 和 Candidate Audit，再交给 `OfflineExtractionPipeline`。
- 无论成功、异常还是上次进程中断，都保持 SQLite job 状态与 run log 一致。

**Step 3: 运行定向测试**

Run:

```powershell
docker compose run --rm backend python -m pytest `
  backend/tests/test_pipeline_run_archive.py `
  backend/tests/test_pipeline_service.py -v
```

Expected: 新增档案和现有 Pipeline 测试全部通过。

### Task 3: 审核并迁移 PR #47 抽取工件

**Files:**

- Create: `data/extracted/extract-<doc_id>-...json`（9 份）
- Create: `docs/reports/pr47-extraction-artifact-audit.md`

**Step 1: 使用当前契约做只读审核**

- 逐份检查 JSON Schema、Document `doc_id/content_hash` 关联、证据原文与偏移、实体/关系类型矩阵、`run_id` 元数据和正式文件名。
- 单独记录 Candidate Audit 是否存在，缺失时不伪造。

**Step 2: 迁移非重复且契约合法的工件**

- 迁移 `apt28_002`、`apt28_003`、`apt28_004`、`apt28_005`。
- 迁移 `kimsuky_002`、`kimsuky_003`。
- 迁移 `lazarus_003`、`lazarus_004`、`lazarus_009`。
- `kimsuky_001` 和 `lazarus_001` 已由 #58 锁定为审计溯源更完整的工件，不再迁移 #47 的重复版本。
- 工件内容迁移提交保留 `yzq38` Author，维护者作为 Committer。

**Step 3: 记录审核边界**

- 9 份工件可用于契约校验和 `reviewed` 导入。
- 因 #47 未保留对应 Candidate Audit，不将这些运行作为 raw/validated 口径评测 Baseline，也不替换 #58 的三组织主演示清单。

### Task 4: 同步契约、全量回归并提 PR

**Files:**

- Modify: `README.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/demo-flow.md`
- Modify: `docs/data-contract.md`

**Step 1: 更新文档**

- 将 live 语义从“临时文件用后删除”改为“本机持久化 Extraction + Candidate Audit + run log”。
- 明确运行产物默认被 Git 忽略；经评审的工件才单独强制纳入 Git。
- 说明删除 SQLite 后可通过已评审 Document/Extraction 重建，未归档的本机 live 输出不是他人机器的可恢复保证。

**Step 2: 全量验证**

Run:

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
docker compose run --rm --no-deps frontend npm run test
docker compose run --rm --no-deps frontend npm run build
docker compose run --rm --no-deps frontend npm run format:check
git diff --check origin/main...HEAD
```

Expected: 后端、前端测试与构建通过，当前 Prettier 基线已由 #59 修复，因此仓库级格式检查也应通过。

**Step 3: 审计身份并提交 PR**

- 检查 #47 工件迁移提交 Author 为 `yzq38 <1825904177@qq.com>`。
- 运行档案实现、测试和审核结论由维护者独立提交。
- PR 详细列出 live 档案内容、11 份工件去留结论、限制和验证命令。
