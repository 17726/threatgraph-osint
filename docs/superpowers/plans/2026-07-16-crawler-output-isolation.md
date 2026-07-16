# 爬虫结果隔离与来源统计修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 12 个来源同时采集时的共享目录和文件编号冲突，保证来源结果不互相覆盖，并返回来源级统计。

**Architecture:** 每个本地 crawler 使用本次任务独立的输出目录，统一入口在三个 crawler 完成后合并结果到单一目录，再执行一次过滤和 promote。Crawler service 根据文档元数据聚合来源统计，并要求所有选中来源达到 `limit` 的成功 Live Pipeline 数量后才报告任务成功。

**Tech Stack:** Python 3.13、pytest、FastAPI crawler service、Docker Compose。

## Global Constraints

- SQLite 是唯一事实源。
- crawler 只通过 Compose 内部网络暴露 `8100/tcp`。
- 前端只调用 backend，不直接调用 crawler。
- `limit` 表示每个来源最多成功生成的文章数。
- 不提交 `.env`、API Key 或 `temp/` 内容。
- 代码与输出默认使用简体中文和英文。

---

### Task 1: 固化统一入口的输出隔离行为

**Files:**
- Modify: `scripts/run_all_crawlers.py`
- Test: `crawler/tests/test_run_all_crawlers.py`

**Interfaces:**
- `build_commands(args)` 继续返回顺序命令列表。
- 每个 crawler 命令接收独立的 `CRAWLER_DATA_ROOT`，而不是依赖共享根目录。
- 新增合并辅助函数，将 crawler 子目录中的 `cleaned` 结果复制到统一 `cleaned` 目录并使用不冲突的路径名。

- [ ] **Step 1: Write the failing tests**

```python
def test_crawler_commands_use_distinct_output_roots():
    commands = run_all_crawlers.build_commands(args)
    crawler_commands = commands[:3]
    assert [command.output_root for command in crawler_commands] == [
        "crawler_v1",
        "crawler_supplementary",
        "crawler_supplementary_v2",
    ]


def test_merge_cleaned_documents_keeps_same_legacy_filename_from_each_crawler(tmp_path):
    write_document(tmp_path / "v1" / "cleaned" / "apt28" / "apt28_001.json", "Qianxin")
    write_document(tmp_path / "v2" / "cleaned" / "apt28" / "apt28_001.json", "SecureList")
    stats = run_all_crawlers.merge_cleaned_documents(tmp_path, tmp_path / "merged")
    assert stats == 2
    assert len(list((tmp_path / "merged" / "apt28").glob("*.json"))) == 2
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest crawler/tests/test_run_all_crawlers.py -q`

Expected: FAIL because crawler commands and `merge_cleaned_documents` do not yet provide isolated roots.

- [ ] **Step 3: Implement minimal isolation and merge**

Use a per-crawler directory below the run data root, pass it through the subprocess environment, and merge each source document into the common directory with a deterministic prefix containing the crawler name and original filename. Preserve JSON payload fields and do not alter `doc_id` until promote.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest crawler/tests/test_run_all_crawlers.py -q`

Expected: PASS.

### Task 2: Add source-level result accounting

**Files:**
- Modify: `crawler/app/service.py`
- Test: `crawler/tests/test_crawler_service.py`

**Interfaces:**
- `CrawlerService._import_documents(payload)` returns existing aggregate counters plus `source_results`.
- `source_results` is keyed by normalized `source_name` and contains `items_promoted`, `items_imported`, `items_skipped`, `items_failed`, and `items_pipeline_succeeded`.

- [ ] **Step 1: Write the failing test**

```python
def test_import_documents_reports_counts_per_source(tmp_path, monkeypatch):
    write_document(tmp_path / "data" / "documents" / "apt28_001.json", "Qianxin")
    write_document(tmp_path / "data" / "documents" / "apt28_002.json", "SecureList")
    result = service._import_documents(payload)
    assert result["source_results"] == {
        "Qianxin": {"items_promoted": 1, "items_imported": 1, "items_skipped": 0, "items_failed": 0, "items_pipeline_succeeded": 1},
        "SecureList": {"items_promoted": 1, "items_imported": 1, "items_skipped": 0, "items_failed": 0, "items_pipeline_succeeded": 1},
    }
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest crawler/tests/test_crawler_service.py::test_import_documents_reports_counts_per_source -q`

Expected: FAIL because `source_results` is not returned.

- [ ] **Step 3: Implement source aggregation**

Initialize source counters from each document's `source_name`, increment the relevant counter at promote/import/pipeline boundaries, and include the mapping in the result returned by `_execute` and the status endpoint.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest crawler/tests/test_crawler_service.py -q`

Expected: PASS.

### Task 3: Enforce all-selected-sources success

**Files:**
- Modify: `crawler/app/service.py`
- Modify: `scripts/run_all_crawlers.py`
- Test: `crawler/tests/test_crawler_service.py`

**Interfaces:**
- The execution payload carries the selected source names or derives them from the global mask using the shared source layout.
- A run with `limit=1` succeeds only if every selected source has one successful Live Pipeline result.
- Failed runs include missing source names and observed counts in `error_message`.

- [ ] **Step 1: Write the failing test**

```python
def test_run_fails_when_selected_source_has_no_successful_pipeline(monkeypatch):
    result = service._finalize_result(
        payload={"limit": 1, "selected_sources": ["Qianxin", "SecureList"]},
        result={"items_pipeline_succeeded": 1, "source_results": {"Qianxin": {"items_pipeline_succeeded": 1}}},
        pipeline_error=None,
    )
    assert result["status"] == "failed"
    assert "SecureList" in result["error_message"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest crawler/tests/test_crawler_service.py::test_run_fails_when_selected_source_has_no_successful_pipeline -q`

Expected: FAIL because final status currently only checks aggregate success.

- [ ] **Step 3: Implement strict finalization**

Compute required successes as `limit` for each selected source, compare against `items_pipeline_succeeded`, preserve crawler exit failures, and return `failed` when any source is below target. Keep partial documents and successful pipeline results in SQLite.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest crawler/tests/test_crawler_service.py -q`

Expected: PASS.

### Task 4: End-to-end regression verification

**Files:**
- Modify: `crawler/tests/test_crawler_api.py` only if response fixture requires the new optional field.
- Modify: `docs/api-contract.md` only if the response contract needs documenting `source_results`.

- [ ] **Step 1: Run crawler regression tests**

Run: `pytest crawler/tests -v`

Expected: all tests pass.

- [ ] **Step 2: Validate Compose configuration**

Run: `docker compose config`

Expected: exit code `0`.

- [ ] **Step 3: Build affected services**

Run: `docker compose build backend crawler`

Expected: both images build successfully.

- [ ] **Step 4: Inspect final diff and status**

Run: `git diff -- scripts/run_all_crawlers.py crawler/app/service.py crawler/tests docs/api-contract.md` and `git status --short --branch`.

Expected: only intended crawler files and the implementation plan are changed; `temp/` remains untracked and untouched.
