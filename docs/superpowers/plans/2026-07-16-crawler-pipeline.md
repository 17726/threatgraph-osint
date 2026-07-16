# 爬虫统一流水线实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `run_all_crawlers.py` 通过四个统一参数完成来源筛选、三个爬虫调用、可选过滤和标准文档提升。

**Architecture:** 三个爬虫先把临时 Document 写入 `data/cleaned/<target_group>/`。调度器按来源归属表将来源分发给对应爬虫；可选调用过滤器写入 `data/cleaned_filtered/`，最后由独立 promote 脚本按正式目录最大序号生成新的 `doc_id` 并写入 `data/documents/`。

**Tech Stack:** Python 3.13、argparse、subprocess、JSON、pytest、Docker Compose。

## Global Constraints

- 对外统一入口只暴露 `--keyword`、`--limit`、`--filter`、`--sources`。
- 三个爬虫的中间输出目录统一为 `data/cleaned/<target_group>/`。
- `--sources` 使用十进制整数 bitmask；必须大于 0 且不能超出 12 位布局。
- 没有匹配来源的爬虫不得启动。
- `promote_cleaned_documents.py` 不修改输入中间文件。
- 正式 `doc_id` 按 `data/documents/<target_group>/` 当前最大序号递增。
- `convert_raw_documents.py` 和 `convert_suqi625_dataset.py` 不参与新流水线。
- 代码、测试和提交说明默认使用简体中文。

---

### Task 1: Add crawler source selection and cleaned output

**Files:**
- Modify: `scripts/crawler_v1.py`
- Modify: `scripts/crawler_supplementary.py`
- Modify: `scripts/crawler_supplementary_v2.py`
- Create: `backend/tests/test_crawler_source_selection.py`

**Interfaces:**
- Each crawler exposes local integer `--sources`; bit 0 selects its first hard-coded source.
- `crawler_v1.output_dir_for()` returns `data/cleaned/<target_group>`.
- Supplementary source registries remain the source of truth for valid keys.

- [ ] **Step 1: Write failing tests**

Add tests for `crawler_v1.output_dir_for`, local integer mask selection, and invalid masks without making network requests.

```python
from scripts import crawler_v1, crawler_supplementary, crawler_supplementary_v2


def test_crawler_v1_writes_cleaned_documents() -> None:
    assert crawler_v1.output_dir_for("APT28").as_posix().endswith("data/cleaned/apt28")


def test_source_selection_accepts_comma_separated_values() -> None:
    assert crawler_v1.parse_sources("qianxin,freebuf") == ["qianxin", "freebuf"]
    assert crawler_supplementary.parse_sources("microsoft,securelist") == ["microsoft", "securelist"]
    assert crawler_supplementary_v2.parse_sources("ofac,groupib") == ["ofac", "groupib"]


def test_source_selection_rejects_unknown_values() -> None:
    try:
        crawler_v1.parse_sources("missing")
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("unknown source should fail")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_crawler_source_selection.py -q
```

Expected: FAIL because `parse_sources` is not defined and `crawler_v1` still points at `data/documents`.

- [ ] **Step 3: Implement minimal source selection**

Add a `sources_from_mask(source_mask)` helper to each crawler, change `crawler_v1.output_dir_for()` to `data/cleaned`, and update each `main()` to pass the selected local integer mask to only the matching crawler classes. Preserve the existing per-source parsing logic and make each crawler's `run` method accept its existing keyword and limit arguments.

- [ ] **Step 4: Run tests and syntax checks**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_crawler_source_selection.py backend/tests/test_crawler_v1_document_contract.py -q
docker compose run --rm backend python -m py_compile scripts/crawler_v1.py scripts/crawler_supplementary.py scripts/crawler_supplementary_v2.py
```

Expected: all selected tests pass and compilation exits successfully.

### Task 2: Add promote_cleaned_documents.py

**Files:**
- Create: `scripts/promote_cleaned_documents.py`
- Create: `backend/tests/test_promote_cleaned_documents.py`

**Interfaces:**
- `promote_documents(input_dir: Path, output_dir: Path) -> PromotionStats`.
- `next_document_number(output_dir: Path, target_group: str) -> int`.
- CLI supports `--input`, `--output`, and optional `--target-group`.

- [ ] **Step 1: Write failing tests**

```python
import json
from pathlib import Path

from scripts.promote_cleaned_documents import promote_documents


def document(doc_id: str, url: str, text: str) -> dict:
    import hashlib
    return {
        "doc_id": doc_id,
        "schema_version": "1.0",
        "target_group": "APT28",
        "target_groups": ["APT28"],
        "source_url": url,
        "source_type": "news",
        "source_name": "Example",
        "title": "Example",
        "language": "en",
        "clean_text": text,
        "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "published_at": None,
        "retrieved_at": "2026-07-16T00:00:00Z",
        "source_reliability": "B",
        "tlp": "TLP:CLEAR",
        "tags": ["news"],
        "metadata": {},
    }


def test_promote_assigns_next_id_and_deduplicates(tmp_path: Path) -> None:
    source = tmp_path / "cleaned" / "apt28"
    target = tmp_path / "documents" / "apt28"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    (target / "apt28_007.json").write_text(json.dumps(document("old", "https://old", "old")), encoding="utf-8")
    (source / "temporary.json").write_text(json.dumps(document("tmp", "https://new", "new")), encoding="utf-8")
    (source / "duplicate.json").write_text(json.dumps(document("tmp2", "https://old", "old")), encoding="utf-8")

    stats = promote_documents(tmp_path / "cleaned", tmp_path / "documents")

    assert stats.promoted == 1
    assert stats.skipped == 1
    promoted = json.loads((target / "apt28_008.json").read_text(encoding="utf-8"))
    assert promoted["doc_id"] == "apt28_008"
```

- [ ] **Step 2: Run test and verify RED**

Run the same Docker pytest command for the new test. Expected: FAIL because the module and promotion function do not exist.

- [ ] **Step 3: Implement promotion**

Read JSON files recursively, validate the required Document fields, recompute and compare `content_hash`, collect existing `source_url` and `content_hash` values from the target directory, calculate each target group's maximum numeric suffix, assign new IDs, write atomically through a temporary sibling file, and keep input files unchanged. Return counts for promoted, skipped, and errors.

- [ ] **Step 4: Run promote tests**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_promote_cleaned_documents.py -q
```

Expected: PASS.

### Task 3: Update filter invocation contract

**Files:**
- Modify: `scripts/filter_by_relevance.py`
- Create: `backend/tests/test_filter_by_relevance_config.py`

**Interfaces:**
- Filter CLI accepts optional `--folder` from the dispatcher.
- API key is read at call time from `LLM_API_KEY` or `DEEPSEEK_API_KEY`; no fallback literal is allowed.

- [ ] **Step 1: Write failing test**

Test that clearing both environment variables causes `call_api` to raise the explicit missing-key error, and that `--folder apt28` is accepted by the parser.

- [ ] **Step 2: Run test and verify RED**

Run the focused Docker test and confirm the expected missing configuration failure.

- [ ] **Step 3: Implement minimal configuration change**

Move API-key lookup into `call_api`, retain the existing output directory, and preserve the current temporary renumbering behavior for intermediate files.

- [ ] **Step 4: Run focused tests**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_filter_by_relevance_config.py -q
```

Expected: PASS.

### Task 4: Rewrite run_all_crawlers.py as the unified dispatcher

**Files:**
- Modify: `scripts/run_all_crawlers.py`
- Create: `backend/tests/test_run_all_crawlers.py`

**Interfaces:**
- `build_parser()` exposes only `--keyword`, `--limit`, `--filter`, and `--sources`.
- `CRAWLER_WIDTHS` defines the fixed bit width of each crawler.
- `group_source_masks(sources: int) -> dict[str, int]` returns nonzero local masks and skips empty owners.
- `build_commands(args) -> list[list[str]]` creates crawler, optional filter, and promote subprocess commands.

- [ ] **Step 1: Write failing tests**

Cover full-mask selection, selected bit grouping, no command for an owner with a zero local mask, filter input selection, and parser rejection of invalid integers.

- [ ] **Step 2: Run tests and verify RED**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_run_all_crawlers.py -q
```

Expected: FAIL against the current interactive implementation.

- [ ] **Step 3: Implement dispatcher**

Use `argparse`, validate the decimal global bitmask, split it into fixed 4-bit local masks, run each selected crawler once with its local `--sources` integer, then run `filter_by_relevance.py --folder <normalized target>` only when `--filter` is present, and finally run `promote_cleaned_documents.py` with either `data/cleaned` or `data/cleaned_filtered`. Stop on the first nonzero child process and propagate its exit code.

- [ ] **Step 4: Run dispatcher tests**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_run_all_crawlers.py -q
```

Expected: PASS.

### Task 5: Full verification and documentation alignment

**Files:**
- Modify: `scripts/crawler_supplementary.py`
- Modify: `scripts/crawler_supplementary_v2.py`
- Modify: `docs/superpowers/specs/2026-07-16-crawler-pipeline-design.md` only if implementation details differ

- [ ] **Step 1: Run the complete backend test suite**

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

- [ ] **Step 2: Run syntax and help checks**

```bash
docker compose run --rm backend python -m py_compile scripts/crawler_v1.py scripts/crawler_supplementary.py scripts/crawler_supplementary_v2.py scripts/filter_by_relevance.py scripts/promote_cleaned_documents.py scripts/run_all_crawlers.py
docker compose run --rm backend python scripts/run_all_crawlers.py --help
```

- [ ] **Step 3: Inspect the final diff**

Verify that historical migration scripts are unchanged, no `.env` or API key is staged, and only intended crawler files and tests are included.
