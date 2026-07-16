# 爬虫测试独立容器迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将历史上属于 crawler 数据采集和预处理的测试从 `backend/tests` 迁移到独立 `crawler` 测试容器，并验证 backend 测试仍能独立运行。

**Architecture:** 新增 `crawler/Dockerfile` 和 `crawler/requirements.txt`，镜像使用项目根目录作为构建上下文，复制 `scripts/` 与 `crawler/tests/`，但不复制或挂载 backend SQLite。`docker-compose.yml` 增加只用于测试的 crawler 服务；backend 保留直接依赖 FastAPI、SQLite、Neo4j 的测试。

**Tech Stack:** Docker Compose、Python 3.13、pytest、现有 `scripts/` 爬虫与转换脚本。

## Global Constraints

- 迁移的 crawler 测试为 `test_crawler_source_selection.py`、`test_crawler_v1_document_contract.py`、`test_filter_by_relevance_config.py`、`test_promote_cleaned_documents.py`、`test_run_all_crawlers.py`、`test_convert_raw_documents.py`、`test_convert_suqi625_dataset.py`。
- 不迁移直接依赖 `backend.app`、FastAPI、SQLite 或 Neo4j 的测试。
- crawler 测试容器不挂载 backend 的 SQLite 或项目 `data` 目录。
- 不修改测试断言和业务逻辑；只处理测试位置、镜像依赖和运行入口。
- 不提交 `.env`、运行缓存、`temp/` 或测试生成的运行产物。

---

### Task 1: 创建独立 crawler 测试镜像

**Files:**
- Create: `crawler/Dockerfile`
- Create: `crawler/requirements.txt`
- Create: `crawler/tests/__init__.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- `crawler` 服务默认工作目录为 `/app`，Python 路径为 `/app`。
- `docker compose run --rm crawler python -m pytest crawler/tests -v` 执行独立测试。

- [ ] **Step 1: 添加 crawler 镜像文件**

使用 Python 3.13 slim，安装 crawler 测试所需的 `pytest`、`beautifulsoup4`、`lxml`、`requests` 和现有脚本依赖；不安装 backend 专属依赖。

- [ ] **Step 2: 添加 Compose crawler 服务**

服务使用根目录构建上下文和 `crawler/Dockerfile`，只挂载 `scripts` 和 `crawler`；不挂载 `backend` 或项目 `data` 目录，不暴露宿主机端口，默认命令保持为测试入口。

- [ ] **Step 3: 构建并检查测试收集**

运行：

```bash
docker compose build crawler
docker compose run --rm crawler python -m pytest --collect-only -q crawler/tests
```

预期：成功收集迁移后的 7 个测试文件，且不从 `backend/tests` 收集 crawler 测试。

### Task 2: 迁移 crawler 测试

**Files:**
- Move: `backend/tests/test_crawler_source_selection.py` -> `crawler/tests/test_crawler_source_selection.py`
- Move: `backend/tests/test_crawler_v1_document_contract.py` -> `crawler/tests/test_crawler_v1_document_contract.py`
- Move: `backend/tests/test_filter_by_relevance_config.py` -> `crawler/tests/test_filter_by_relevance_config.py`
- Move: `backend/tests/test_promote_cleaned_documents.py` -> `crawler/tests/test_promote_cleaned_documents.py`
- Move: `backend/tests/test_run_all_crawlers.py` -> `crawler/tests/test_run_all_crawlers.py`
- Move: `backend/tests/test_convert_raw_documents.py` -> `crawler/tests/test_convert_raw_documents.py`
- Move: `backend/tests/test_convert_suqi625_dataset.py` -> `crawler/tests/test_convert_suqi625_dataset.py`

**Interfaces:**
- 测试继续从 `scripts` 导入现有 crawler 和转换模块。
- 测试路径变化不改变测试行为。

- [ ] **Step 1: 移动 7 个测试文件**

使用版本控制移动，确保 diff 保留为 rename，避免复制后遗漏 backend 原文件。

- [ ] **Step 2: 运行 crawler 测试**

运行：

```bash
docker compose run --rm crawler python -m pytest crawler/tests -v
```

预期：所有 crawler 测试通过；如果发现路径或依赖问题，只修复容器入口或测试路径，不扩大业务改动。

- [ ] **Step 3: 检查 backend 测试剩余范围**

运行：

```bash
docker compose run --rm backend python -m pytest backend/tests --collect-only -q
```

预期：backend 测试收集结果不再包含上述 7 个 crawler 测试，其他 backend 测试仍可收集。

### Task 3: 回归验证和变更检查

**Files:**
- Verify: `crawler/Dockerfile`
- Verify: `crawler/requirements.txt`
- Verify: `docker-compose.yml`
- Verify: `backend/tests/`
- Verify: `crawler/tests/`

- [ ] **Step 1: 运行 crawler 全量测试**

```bash
docker compose run --rm crawler python -m pytest crawler/tests -v
```

- [ ] **Step 2: 运行 backend 剩余测试**

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

- [ ] **Step 3: 检查差异和未跟踪文件**

```bash
git diff --check
git status --short
git diff --stat
```

确认仅包含 crawler 测试迁移、独立测试镜像、Compose 配置及必要的忽略文件，不包含 `temp/`、`.env` 或运行缓存。

- [ ] **Step 4: 提交迁移**

```bash
git add crawler docker-compose.yml backend/tests
git commit -m "test: 迁移爬虫测试到独立容器"
```
