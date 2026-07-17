# 采集流水线部分成功语义 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将采集过滤从“单篇失败导致整批失败”重构为文档级容错，使成功文档继续 promote、导入和执行 Pipeline，完整暴露失败文档，并把每次运行的中间产物归档到仓库工作区供人工检查。

**Architecture:** 相关性过滤脚本把每篇文档区分为 kept、discarded 和 retriable error，并通过工作区内的 `filter-result.json` 输出批次摘要。编排层只把脚本崩溃等系统错误视为非零退出；文档级错误返回成功并继续 promote。Crawler、Backend 和 React 共同识别 `partial_success` 终态，显示失败计数和文档原因。Crawler 在清理临时工作区前将完整运行目录原子归档到宿主机挂载的 `data/crawl_runs/<crawl_run_id>/`，归档目录被 Git 忽略。

**Tech Stack:** Python 3.13、FastAPI、React 19、TypeScript、Vitest、pytest、Docker Compose

---

### Task 1: 修复过滤断点与文档级失败语义

**Files:**
- Modify: `scripts/filter_by_relevance.py`
- Test: `crawler/tests/test_filter_by_relevance_config.py`

**Step 1: Write the failing test**

增加测试证明：
- checkpoint 中的 `error_api` 不属于已完成集合，下一次运行会重新处理；
- 单篇 API 错误不会让 CLI 返回非零；
- `CRAWLER_FILTER_RESULT_FILE` 会写出 kept、discarded、errors 和失败文档。

**Step 2: Run test to verify it fails**

Run: `docker compose run --rm crawler python -m pytest crawler/tests/test_filter_by_relevance_config.py -q`
Expected: FAIL，现有实现返回 1，且不会生成过滤摘要。

**Step 3: Write minimal implementation**

- 仅把 kept/discarded 状态视为断点完成；
- error 状态保留审计信息，但下次运行重新进入 pending；
- 输出原子写入的 `filter-result.json`；
- 文档级错误返回 0，未捕获的系统错误仍由进程返回非零。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 2: 让编排继续 promote 并读取过滤摘要

**Files:**
- Modify: `scripts/run_all_crawlers.py`
- Modify: `crawler/app/service.py`
- Test: `crawler/tests/test_run_all_crawlers.py`
- Test: `crawler/tests/test_crawler_service.py`

**Step 1: Write the failing test**

增加测试证明：
- 过滤结果含单篇失败时，成功文件仍进入 promote；
- Crawler 读取 `filter-result.json` 并把失败计入 `items_failed`；
- 至少一个 Pipeline 成功且存在文档失败时，终态为 `partial_success`；
- 批次级非零退出仍保持 `failed`。

**Step 2: Run test to verify it fails**

Run: `docker compose run --rm crawler python -m pytest crawler/tests/test_run_all_crawlers.py crawler/tests/test_crawler_service.py -q`
Expected: FAIL，当前没有过滤摘要和 `partial_success`。

**Step 3: Write minimal implementation**

- 将 `CRAWLER_FILTER_RESULT_FILE` 传给过滤子进程；
- 在清理工作区前读取摘要；
- 合并过滤失败与导入/Pipeline 失败；
- 生成 `filter_partial` 事件；
- 将有成功也有失败的批次标为 `partial_success`。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 3: 贯通 Backend 与前端部分成功终态

**Files:**
- Modify: `backend/app/services/crawl_service.py`
- Modify: `backend/tests/test_crawl_service.py`
- Modify: `frontend/src/api/crawler.ts`
- Modify: `frontend/src/components/CrawlerModal.tsx`
- Modify: `frontend/src/components/CrawlerModal.test.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Write the failing test**

增加测试证明：
- Backend 轮询把 `partial_success` 当作终态并透传 `filter_summary`；
- 前端停止轮询、刷新图谱，并显示“部分成功”与失败文档。

**Step 2: Run test to verify it fails**

Run:
- `docker compose run --rm backend python -m pytest backend/tests/test_crawl_service.py -q`
- `docker compose run --rm frontend npm run test -- --run src/components/CrawlerModal.test.tsx`

Expected: FAIL。

**Step 3: Write minimal implementation**

扩展状态联合类型、终态集合、代理字段与 UI 结果卡片；部分成功使用警告视觉，不伪装成完全成功。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 4: 持久化中间产物供人工检查

**Files:**
- Modify: `crawler/app/service.py`
- Modify: `crawler/tests/test_crawler_service.py`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`

**Step 1: Write the failing test**

增加测试证明成功、部分成功和失败任务都会在清理临时目录前归档；归档至少包含 raw、cleaned、cleaned_filtered、documents、progress.json 和 filter-result.json 中实际存在的内容，并返回 `artifact_path`。

**Step 2: Run test to verify it fails**

Run: `docker compose run --rm crawler python -m pytest crawler/tests/test_crawler_service.py -q`
Expected: FAIL，当前只删除临时工作区，不保存产物。

**Step 3: Write minimal implementation**

- 新增 `CRAWLER_ARTIFACT_ROOT=/app/data/crawl_runs`；
- 将 `./data/crawl_runs` 只挂载给 crawler；
- 使用同级临时目录复制完成后再 rename，避免人工看到半成品；
- 归档成功后清理 `/tmp` 工作区；归档失败时任务保留原终态，但增加错误事件且不删除临时目录；
- API 返回仓库相对 `artifact_path`，不暴露容器内部绝对路径。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 5: 更新契约与完整验证

**Files:**
- Modify: `README.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/docker-runtime.md`
- Modify: `docs/demo-flow.md`

**Step 1: Update documentation**

记录 `partial_success`、`filter_summary`、文档级错误与系统级错误的边界，以及 `data/crawl_runs/<crawl_run_id>/` 的人工检查方式和 Git 忽略规则。

**Step 2: Run full verification**

Run:
- `docker compose run --rm backend python -m pytest backend/tests -q`
- `docker compose run --rm crawler python -m pytest crawler/tests -q`
- `docker compose run --rm frontend npm run test -- --run`
- `docker compose run --rm frontend npm run build`
- `git diff --check`

Expected: 全部通过；若全仓历史格式检查仍失败，只报告未修改文件，不扩大范围。

**Step 3: Commit and update PR**

使用中文 Conventional Commit，推送到 `feat/arch/pipeline-observability`，更新 PR #79。
