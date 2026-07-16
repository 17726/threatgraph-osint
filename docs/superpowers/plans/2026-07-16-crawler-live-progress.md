# 爬虫实时进度实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将采集页面从固定 `3/3` 改为显示采集、验证、导入和 Live 建图的真实进度，并恢复“至少一篇 Live 成功即任务成功”的错误返回语义。

**Architecture:** crawler 在任务状态内维护 `progress`，统一入口和导入服务在实际边界更新阶段计数；backend 原样转发状态，frontend 根据轮询结果渲染阶段文案、来源和百分比。现有总量字段保留，新增字段均可选，旧客户端缺少进度时降级为通用执行提示。

**Tech Stack:** Python 3.13、FastAPI、pytest、React 19、TypeScript、Vitest、Docker Compose。

## Global Constraints

- SQLite 是唯一事实源。
- 前端只调用 FastAPI，不直接访问 crawler。
- crawler 只通过 Compose 内部网络暴露 `8100/tcp`。
- `limit` 表示每个来源最多成功生成的文章数。
- 任务至少一篇 Live Pipeline 成功时返回 `succeeded`。
- 不提交 `.env`、API Key 或 `temp/` 内容。

---

### Task 1: 恢复 crawler 宽松终态并定义进度状态

**Files:**
- Modify: `crawler/app/service.py`
- Test: `crawler/tests/test_crawler_service.py`

**Interfaces:**
- `CrawlerService` 状态新增 `progress` 对象。
- `_finalize_result()` 在无 crawler 脚本退出错误时，仅按 `items_pipeline_succeeded > 0` 判断成功，不再要求每个来源达到 `limit`。

- [ ] **Step 1: Write the failing tests**

```python
def test_partial_source_success_is_succeeded_again():
    result = service._finalize_result(
        {"limit": 1, "selected_sources": ["奇安信威胁情报中心", "Microsoft"]},
        {
            "items_pipeline_succeeded": 1,
            "source_results": {"Microsoft": {"items_pipeline_succeeded": 1}},
        },
        None,
    )
    assert result["status"] == "succeeded"


def test_new_run_has_collecting_progress():
    result = service._failed_result({"crawl_run_id": "r", "keyword": "APT28"}, "x")
    assert result["progress"]["phase"] == "failed"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `docker compose run --rm crawler pytest crawler/tests/test_crawler_service.py::test_partial_source_success_is_succeeded_again crawler/tests/test_crawler_service.py::test_new_run_has_collecting_progress -q`

Expected: FAIL because current finalization rejects missing sources and result objects do not consistently expose `progress`.

- [ ] **Step 3: Implement minimal terminal and state fields**

Add a `progress` object with `phase`, `current`, `total`, `target`, `source`, and `message` to pending, running, failed, and final results. Remove the selected-source missing check from `_finalize_result`; keep crawler subprocess failures and zero successful Pipeline as failures. Set `completed` or `failed` phase at finalization.

- [ ] **Step 4: Run tests to verify pass**

Run: `docker compose run --rm crawler pytest crawler/tests/test_crawler_service.py -q`

Expected: PASS after updating the old conflicting assertion.

### Task 2: Report collecting and validating progress

**Files:**
- Modify: `scripts/run_all_crawlers.py`
- Modify: `scripts/filter_by_relevance.py`
- Modify: `crawler/app/service.py`
- Test: `crawler/tests/test_run_all_crawlers.py`
- Test: `crawler/tests/test_filter_by_relevance_config.py`

**Interfaces:**
- `run_all_crawlers.py` receives an optional progress file path through `CRAWLER_PROGRESS_FILE`.
- Progress file JSON uses the design schema and is read by crawler service while polling subprocess execution.
- `filter_by_relevance.py` updates the same file after each input document is processed.

- [ ] **Step 1: Write the failing tests**

```python
def test_collecting_total_is_selected_sources_times_limit():
    assert run_all_crawlers.progress_total(5, 2) == 10


def test_progress_file_writer_records_phase(tmp_path):
    path = tmp_path / "progress.json"
    run_all_crawlers.write_progress(path, phase="collecting", current=3, total=10, target="APT28", source="FreeBuf")
    assert json.loads(path.read_text())["progress"]["current"] == 3
```

- [ ] **Step 2: Run tests to verify failure**

Run: `docker compose run --rm crawler pytest crawler/tests/test_run_all_crawlers.py -q`

Expected: FAIL because progress helpers and file updates do not exist.

- [ ] **Step 3: Implement progress writer and subprocess propagation**

Derive selected source count from the global mask, initialize collecting progress with `total=source_count*limit`, pass `CRAWLER_PROGRESS_FILE` to each crawler, and merge isolated outputs without changing the progress file. Have crawler scripts update the file after each successful saved document with the canonical source display name.

- [ ] **Step 4: Implement validation progress**

When filtering begins, write `phase=validating`, `current=0`, and `total` equal to the number of merged JSON documents. Increment after each document is kept, discarded, or recorded as an error. If filtering is disabled, write a completed validation state before promote.

- [ ] **Step 5: Run tests to verify pass**

Run: `docker compose run --rm crawler pytest crawler/tests -q`

Expected: all crawler tests pass.

### Task 3: Report import and Live Pipeline progress

**Files:**
- Modify: `crawler/app/service.py`
- Modify: `backend/app/services/crawl_service.py`
- Test: `crawler/tests/test_crawler_service.py`
- Test: `backend/tests/test_crawl_service.py`

**Interfaces:**
- `_import_documents()` updates `progress.phase=importing` and increments after each document's import and Live Pipeline attempt.
- backend `public_status()` includes `progress` without transforming it.

- [ ] **Step 1: Write the failing tests**

```python
def test_import_progress_reaches_document_total(monkeypatch, tmp_path):
    result = service._import_documents(payload)
    assert result["progress"] == {
        "phase": "importing",
        "current": 2,
        "total": 2,
        "target": "APT28",
        "source": None,
        "message": "正在导入",
    }
```

- [ ] **Step 2: Run test to verify failure**

Run: `docker compose run --rm crawler pytest crawler/tests/test_crawler_service.py::test_import_progress_reaches_document_total -q`

Expected: FAIL because `_import_documents()` currently returns only aggregate counters.

- [ ] **Step 3: Implement importing progress**

Set total to promoted document count before iterating, update the source and current document context, and increment once after each import plus Pipeline attempt, including failures. Keep `items_pipeline_succeeded` and `items_pipeline_failed` unchanged.

- [ ] **Step 4: Forward progress through backend**

Add `progress` to backend run initialization, crawler status merge, and public status field lists. Preserve `null` source for validating/importing phases without a single current source.

- [ ] **Step 5: Run tests to verify pass**

Run: `docker compose run --rm backend python -m pytest backend/tests/test_crawl_service.py -q` and `docker compose run --rm crawler pytest crawler/tests -q`

Expected: both commands pass.

### Task 4: Render truthful frontend progress

**Files:**
- Modify: `frontend/src/api/crawler.ts`
- Modify: `frontend/src/components/CrawlerModal.tsx`
- Test: `frontend/src/components/CrawlerModal.test.tsx`

**Interfaces:**
- `CrawlRunStats.progress` is optional and typed with phase, current, total, target, source, and message.
- Modal renders the optional progress object and falls back to `任务正在执行` when absent.

- [ ] **Step 1: Write the failing tests**

```tsx
it("renders collecting progress from backend", async () => {
  mockStatus({
    status: "running",
    progress: { phase: "collecting", current: 3, total: 10, target: "APT28", source: "FreeBuf", message: "正在采集" },
  });
  expect(await screen.findByText("3/10 正在采集 目标：APT28 来源：FreeBuf")).toBeInTheDocument();
});

it("renders validation and import phases", async () => {
  mockStatusSequence([
    { status: "running", progress: { phase: "validating", current: 4, total: 10, target: "APT28", source: null, message: "正在验证" } },
    { status: "running", progress: { phase: "importing", current: 6, total: 10, target: "APT28", source: null, message: "正在导入" } },
  ]);
  expect(await screen.findByText("4/10 正在验证 目标：APT28")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `npm --prefix frontend run test -- CrawlerModal.test.tsx`

Expected: FAIL because the modal currently renders hard-coded `1/3` and `3/3` text.

- [ ] **Step 3: Implement typed progress rendering**

Add the optional type, derive a display line from `run.progress`, compute percentage with `total=0` protection, remove hard-coded 3-step text, and render source only when non-null. Keep the existing completion summary unchanged.

- [ ] **Step 4: Run frontend tests and build**

Run: `npm --prefix frontend run test -- CrawlerModal.test.tsx` and `npm --prefix frontend run build`

Expected: tests and production build pass.

### Task 5: Contract and full verification

**Files:**
- Modify: `docs/api-contract.md`
- Modify: `docs/superpowers/specs/2026-07-16-crawler-progress-design.md` only if implementation details require clarification.

- [ ] **Step 1: Document progress response**

Add the optional `progress` response field and the restored terminal status rule to the crawl API contract.

- [ ] **Step 2: Run all required verification**

Run:

```bash
docker compose run --rm crawler pytest crawler/tests -q
docker compose run --rm backend python -m pytest backend/tests -q
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run format:check
docker compose config
```

Expected: all tests, build, format check, and Compose validation pass.

- [ ] **Step 3: Inspect final diff**

Run: `git diff --check` and `git status --short --branch`.

Expected: only intended crawler/backend/frontend/docs files are changed; `.env` and `temp/` remain untracked and unstaged.
