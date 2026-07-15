# 多文档 Golden 文件名 Implementation Plan

> **历史方案，非当前契约。** 本文件迁移自 PR #36（原提交 `6a1bffa7`），用于保留方案演进记录。
> 当前方向以“单 Document 对应一份 Golden，多文档由 Dataset/Experiment Manifest 编组”为准；
> 不应直接执行本文件中的多文档 Golden 文件名改造任务。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让正式 Golden 文件名稳定表达 JSON 中的一个或多个 `doc_ids`，同时保持现有单文档文件名兼容。

**Architecture:** 在 `artifact_naming.py` 集中实现 Golden doc-id 集合的规范化：拒绝空值和重复值，按字典序排序，每个 ID 单独安全化后用 `+` 连接。独立评测 CLI、工件生成器和文档只调用同一命名校验逻辑，不各自实现规则。

**Tech Stack:** Python 3.13、pytest、JSON Schema、Docker Compose。

## Global Constraints

- SQLite 是唯一事实源；本任务只修改 LLM Golden 工件命名，不改变 SQLite 数据模型。
- 项目默认在 Windows-x86_64 和 Docker Compose 中验证。
- 文件名中的元数据必须与 JSON 内部字段一致。
- `doc_ids` 至少包含一个非空字符串，且不允许重复。
- Golden 文件名使用排序后的 `doc_ids`；每个 ID 单独安全化后使用 `+` 连接。
- 单文档 Golden 文件名保持现有格式，例如 `golden-en-apt28_080-1.0-1.0.json`。
- 不提交 `.env`、密钥、未脱敏聊天记录或 `temp/`。

---

### Task 1: 增加多文档 Golden 命名失败测试

**Files:**
- Modify: `backend/tests/test_artifact_naming.py`

**Interfaces:**
- Consumes: `golden_filename()` and `validate_golden_artifact_filename()` from `backend.app.services.artifact_naming`.
- Produces: executable expectations for stable multi-document Golden filenames and invalid `doc_ids` rejection.

- [ ] **Step 1: Add failing tests**

Add tests covering sorted IDs, plus preservation, duplicate IDs, and empty IDs:

```python
def test_golden_filename_sorts_multiple_doc_ids():
    assert golden_filename(
        language="en",
        doc_ids=["apt28_081", "apt28_080"],
        schema_version="1.0",
        golden_version="1.0",
    ) == "golden-en-apt28_080+apt28_081-1.0-1.0.json"


def test_golden_filename_rejects_duplicate_doc_ids():
    with pytest.raises(ValueError, match="doc_ids"):
        golden_filename(
            language="en",
            doc_ids=["apt28_080", "apt28_080"],
            schema_version="1.0",
            golden_version="1.0",
        )


def test_golden_filename_rejects_empty_doc_ids():
    with pytest.raises(ValueError, match="doc_ids"):
        golden_filename(
            language="en",
            doc_ids=[],
            schema_version="1.0",
            golden_version="1.0",
        )
```

Update the existing Golden validation test payload to call the new `doc_ids` parameter through the final implementation.

- [ ] **Step 2: Run tests to verify the new tests fail**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_artifact_naming.py -v
```

Expected: FAIL because `golden_filename()` currently accepts only one `doc_id` and rejects multiple IDs.

---

### Task 2: Implement canonical multi-document Golden naming

**Files:**
- Modify: `backend/app/services/artifact_naming.py`
- Test: `backend/tests/test_artifact_naming.py`

**Interfaces:**
- Consumes: `language: str`, `doc_ids: list[str]`, `schema_version: str`, and `golden_version: str`.
- Produces: `golden_filename(...) -> str` and `validate_golden_artifact_filename(...) -> None` using the same canonical doc-id list.

- [ ] **Step 1: Change the Golden filename signature**

Replace the single-ID parameter with a list:

```python
def golden_filename(
    *,
    language: str,
    doc_ids: list[str],
    schema_version: str,
    golden_version: str,
) -> str:
```

- [ ] **Step 2: Add canonical doc-id validation**

Validate that `doc_ids` is non-empty, contains only non-empty strings, and has no duplicates. Sort the IDs before filename generation and sanitize each ID independently:

```python
def _canonical_doc_ids(doc_ids: list[str]) -> list[str]:
    if not isinstance(doc_ids, list) or not doc_ids:
        raise ValueError("doc_ids 必须至少包含一个文档 ID")
    if any(not isinstance(doc_id, str) or not doc_id for doc_id in doc_ids):
        raise ValueError("doc_ids 必须全部是非空字符串")
    if len(set(doc_ids)) != len(doc_ids):
        raise ValueError("doc_ids 不允许重复")
    return sorted(doc_ids)
```

Use:

```python
doc_id_part = "+".join(safe_filename(doc_id) for doc_id in _canonical_doc_ids(doc_ids))
```

- [ ] **Step 3: Update Golden validation to compare canonical filenames**

Read `payload["doc_ids"]` and pass the complete list to `golden_filename()`. This must reject a filename whose ID set or ordering differs from the canonical representation.

- [ ] **Step 4: Run focused tests**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_artifact_naming.py -v
```

Expected: all artifact naming tests pass.

---

### Task 3: Update manifest generation and data artifact tests

**Files:**
- Modify: `scripts/generate_data_artifacts.py`
- Modify: `backend/tests/test_data_artifacts.py`

**Interfaces:**
- Consumes: canonical `golden_filename()` and `validate_golden_artifact_filename()` behavior.
- Produces: manifest records that retain all Golden `doc_ids` and README rows that display the complete sorted ID set.

- [ ] **Step 1: Add a multi-document generator test**

Create a temporary Golden with reversed input order and assert the generated manifest keeps both IDs and the README links the plus-joined filename:

```python
def test_generator_registers_multiple_doc_ids_in_stable_filename(tmp_path):
    data_root = tmp_path / "data"
    _write_json(
        data_root / "golden/golden-en-apt28_080+apt28_081-1.0-1.0.json",
        {
            "schema_version": "1.0",
            "golden_version": "1.0",
            "language": "en",
            "target_group": "APT28",
            "doc_ids": ["apt28_081", "apt28_080"],
            "chunks": [],
            "notes": "",
        },
    )

    manifest, readme = generate_artifacts(data_root)

    assert manifest["goldens"][0]["doc_ids"] == ["apt28_080", "apt28_081"]
    assert "golden-en-apt28_080+apt28_081-1.0-1.0.json" in readme
```

- [ ] **Step 2: Update manifest records**

In `_goldens()`, retain the canonical list as `doc_ids` and use a display field such as `doc_id` only if existing README code requires it. Do not discard all but the first document ID.

- [ ] **Step 3: Update README row generation**

Display the complete ID set as `apt28_080+apt28_081` or an equivalent escaped representation, while keeping the generated file link based on the actual relative path.

- [ ] **Step 4: Run focused generator tests**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_data_artifacts.py -v
```

Expected: all generator tests pass, including multi-document registration.

---

### Task 4: Synchronize contracts and documentation

**Files:**
- Modify: `docs/data-contract.md`
- Modify: `docs/schemas/README.md`

**Interfaces:**
- Consumes: the canonical naming rules from `artifact_naming.py`.
- Produces: documentation that exactly describes sorted, sanitized, plus-joined multi-document Golden IDs.

- [ ] **Step 1: Document the filename grammar**

Add the rule:

```text
golden-<language>-<doc_id_1>+<doc_id_2>+...-<schema_version>-<golden_version>.json
```

- [ ] **Step 2: Document normalization rules**

State that `doc_ids` must be non-empty and unique; IDs are sorted lexicographically; each ID is sanitized independently; the resulting components are joined with `+`. Single-document filenames remain unchanged.

- [ ] **Step 3: Check all examples and references**

Search for calls or examples that still describe Golden filenames as requiring exactly one `doc_id`, and update only those references related to formal Golden naming.

---

### Task 5: Run complete verification

**Files:**
- Verify: `docker-compose.yml`
- Verify: `backend/app/services/artifact_naming.py`
- Verify: `scripts/generate_data_artifacts.py`
- Verify: `backend/tests/test_artifact_naming.py`
- Verify: `backend/tests/test_data_artifacts.py`
- Verify: `docs/data-contract.md`
- Verify: `docs/schemas/README.md`

- [ ] **Step 1: Run full backend tests**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run artifact generation**

Run:

```bash
docker compose run --rm backend python scripts/generate_data_artifacts.py
```

Expected: `data/runs/index.json` and `data/README.md` are generated without validation errors.

- [ ] **Step 3: Check the working tree**

Run:

```bash
git diff --check
git status --short
```

Expected: only intended source, test, documentation, and generated artifact changes are present; `temp/` remains untracked and is not staged.
