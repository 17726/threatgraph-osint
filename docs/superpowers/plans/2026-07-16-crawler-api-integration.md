# 三容器爬虫 API 对接实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 frontend 的采集弹窗、backend 任务管理、crawler HTTP 服务和现有爬虫脚本连接成可测试的三容器 HTTP 流水线。

**Architecture:** 开发阶段浏览器通过 frontend 页面直接请求宿主机 backend API；backend 在内存中保存单个 crawl run，查询 SQLite 计算 `start_number`，通过 HTTP 创建并轮询 crawler；crawler 在自身容器内执行脚本、逐篇调用 backend 文档导入接口并清理临时目录。crawler 只使用 Compose 内部网络，不映射宿主机端口。

**Tech Stack:** FastAPI、httpx、Python 3.13、SQLite、React 19、TypeScript、Vite、Docker Compose、pytest、Vitest。

## Global Constraints

- SQLite 是唯一事实源；crawler 不访问 backend SQLite、backend 文件或项目级 `data` 目录。
- 开发阶段允许浏览器直接访问 `http://localhost:8000/api/v1`；浏览器禁止直接访问 crawler。
- 同一时间只允许一个 `pending` 或 `running` 采集任务；任务状态只保存在 backend 内存中。
- `keyword` 只能为 `APT28`、`Kimsuky` 或 `Lazarus`；`limit` 必须为正整数；`sources` 范围为 `1` 到 `4095`。
- `crawl_run_id` 由 backend 生成，frontend 不生成；backend 必须把 `start_number` 传给 crawler 和 promote。
- backend `/api/v1/documents/import` 是唯一正式查重边界，条件为 `doc_id OR content_hash`。
- 单篇导入失败后继续；至少成功导入一篇时任务 `succeeded`，无成功导入时任务 `failed`。
- crawler 任务无论成功、失败或异常，都必须清理 `cleaned`、`cleaned_filtered`、`documents`。
- 不提交 `.env`、API Key、课程原始 PDF、私有链接和 `temp/`。

---

### Task 1: 增加脚本编号参数并移除 promote 本地查重

**Files:**
- Modify: `scripts/promote_cleaned_documents.py`
- Modify: `scripts/run_all_crawlers.py`
- Test: `crawler/tests/test_promote_cleaned_documents.py`
- Test: `crawler/tests/test_run_all_crawlers.py`

**Interfaces:**
- `promote_documents(input_dir: Path, output_dir: Path, start_number: int = 1) -> PromotionStats`
- `run_all_crawlers.py --start-number INTEGER`，默认 `1`。
- promote 输出仍为标准 Document JSON，但正式 `doc_id` 从传入编号开始递增。

- [ ] **Step 1: Write failing tests for explicit start number and metadata replacement**

在 `crawler/tests/test_promote_cleaned_documents.py` 增加测试：输入目录包含两个 JSON，调用 `promote_documents(input_dir, output_dir, start_number=108)` 后，输出文件名为 `apt28_108.json`、`apt28_109.json`，顶层 `doc_id` 和 metadata 的 `doc_id`、`document_id`、`legacy_doc_id`、`source_path`、`cleaned_path`、`document_path` 都指向新 ID/输出路径；`note`、`clean_text`、`content_hash`、`crawl_run_id` 保持原值。

增加测试证明两个输入即使 source URL 或 content hash 与输出目录已有文档相同也仍会被 promote，且 `stats.skipped == 0`。

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
docker compose run --rm crawler python -m pytest crawler/tests/test_promote_cleaned_documents.py -q
```

Expected: FAIL because `promote_documents` does not accept `start_number`, metadata is not rewritten, and current local deduplication skips documents.

- [ ] **Step 3: Implement minimal promote changes**

实现以下行为：

```python
def promote_documents(input_dir: Path, output_dir: Path, start_number: int = 1) -> PromotionStats:
    if start_number < 1:
        raise ValueError("start_number must be greater than zero")
```

删除 `existing_urls`、`existing_hashes` 及其 skip 分支；保留输入文档契约校验。按目标组织分组后使用 `start_number` 作为每组编号起点，并在写入前只更新明确 metadata 字段：字符串字段中仅当其值等于旧 doc ID 或以旧路径结尾时替换，不递归修改普通描述文本。

在 parser 中加入：

```python
parser.add_argument("--start-number", type=positive_start_number, default=1)
```

CLI 调用 `promote_documents(..., start_number=args.start_number)`。

- [ ] **Step 4: Add failing test for scheduler argument propagation**

在 `crawler/tests/test_run_all_crawlers.py` 验证 `build_commands()` 生成的 promote 命令包含 `--start-number 108`，并验证 `build_parser()` 的默认值为 `1`。

- [ ] **Step 5: Implement scheduler propagation**

在 `run_all_crawlers.py` parser 增加 `--start-number`，并将参数追加到 promote 命令；`build_commands()` 不改变现有来源 bitmask 分组逻辑。

- [ ] **Step 6: Run focused tests**

Run:

```bash
docker compose run --rm crawler python -m pytest crawler/tests/test_promote_cleaned_documents.py crawler/tests/test_run_all_crawlers.py -q
```

Expected: all focused tests PASS。

- [ ] **Step 7: Commit**

```bash
git add scripts/promote_cleaned_documents.py scripts/run_all_crawlers.py crawler/tests/test_promote_cleaned_documents.py crawler/tests/test_run_all_crawlers.py
git commit -m "feat: 支持爬虫流水线编号传递"
```

### Task 2: 实现 crawler HTTP 服务与任务执行器

**Files:**
- Create: `crawler/app/__init__.py`
- Create: `crawler/app/main.py`
- Create: `crawler/app/service.py`
- Modify: `crawler/requirements.txt`
- Modify: `crawler/Dockerfile`
- Test: `crawler/tests/test_crawler_api.py`
- Test: `crawler/tests/test_crawler_service.py`

**Interfaces:**
- `POST /api/v1/crawl/runs` 接收 `crawl_run_id`、`keyword`、`limit`、`sources`、`filter`、`start_number`，立即返回 `{crawl_run_id, status: "accepted"}`。
- `GET /api/v1/crawl/runs/{crawl_run_id}` 返回 `pending/running/succeeded/failed` 与统计字段。
- `CrawlerService.submit(payload) -> dict`；重复 run ID 返回冲突错误。
- `CrawlerService.status(crawl_run_id) -> dict`。

- [ ] **Step 1: Write failing API tests**

使用 FastAPI `TestClient` 覆盖：创建任务返回 `202` 和 `accepted`；查询未知 run 返回 `404`；重复 run ID 返回 `409`；创建请求完整传递 `start_number`。

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
docker compose run --rm crawler python -m pytest crawler/tests/test_crawler_api.py -q
```

Expected: FAIL because `crawler.app.main` does not exist。

- [ ] **Step 3: Implement in-memory crawler service and API**

使用 `ThreadPoolExecutor(max_workers=1)` 或 FastAPI `BackgroundTasks` 实现单任务执行；任务记录至少包含：

```python
{
    "crawl_run_id": str,
    "keyword": str,
    "status": str,
    "items_found": int,
    "items_promoted": int,
    "items_imported": int,
    "items_skipped": int,
    "items_failed": int,
    "document_ids": list[str],
    "workspace_cleaned": bool,
    "error_message": str | None,
}
```

执行器调用现有 `run_all_crawlers.py`，工作目录为 crawler 自身运行根目录；通过 `BACKEND_BASE_URL` 使用 `httpx.Client` 调用 backend 文档导入接口。脚本执行完成后扫描 promote 输出目录，逐篇导入并按响应中的 `status` 统计 imported/skipped；单篇异常增加 failed 后继续。

在 `finally` 中删除任务目录下的 `cleaned`、`cleaned_filtered`、`documents` 内容，并将 `workspace_cleaned` 设为清理结果。任务成功判定为 `items_imported > 0`，否则为 failed；脚本失败但已有文档成功导入时保留 succeeded 并记录错误。

- [ ] **Step 4: Add service tests with mocked subprocess and HTTP client**

验证：

- `start_number` 出现在 subprocess 命令；
- 两篇 Document 一篇 imported、一篇 skipped 时统计正确；
- 第一篇导入异常时第二篇仍被发送；
- subprocess 异常和 HTTP 异常都执行 cleanup；
- `items_imported > 0` 时最终为 succeeded；
- 无成功导入时最终为 failed。

- [ ] **Step 5: Run crawler tests**

Run:

```bash
docker compose run --rm crawler python -m pytest crawler/tests -q
```

Expected: migrated crawler tests and new API/service tests PASS。

- [ ] **Step 6: Configure crawler runtime image**

在 `crawler/requirements.txt` 增加 `fastapi`、`httpx`、`uvicorn[standard]`；Dockerfile 保留脚本、crawler 代码和运行时目录，默认 command 改为：

```text
uvicorn crawler.app.main:app --host 0.0.0.0 --port 8100
```

- [ ] **Step 7: Commit**

```bash
git add crawler/app crawler/requirements.txt crawler/Dockerfile crawler/tests/test_crawler_api.py crawler/tests/test_crawler_service.py
git commit -m "feat: 添加爬虫 HTTP 服务"
```

### Task 3: 增加 backend 采集任务 API 和 crawler 轮询

**Files:**
- Create: `backend/app/services/crawl_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_crawl_api.py`
- Test: `backend/tests/test_crawl_service.py`

**Interfaces:**
- `POST /api/v1/crawl/runs` 返回 HTTP `202`，响应 `crawl_run_id` 和 `pending`。
- `GET /api/v1/crawl/runs/{crawl_run_id}` 返回内存任务状态。
- `CrawlService.submit(keyword: str, limit: int, sources: int, filter_enabled: bool) -> dict`。
- `CrawlService.status(crawl_run_id: str) -> dict`。

- [ ] **Step 1: Write failing backend tests**

覆盖：合法请求生成 ID；非法 keyword、limit、sources 返回 `400/ERR_VALIDATION`；已有 pending/running 返回 `409`；未知 ID 返回 `404`；mock crawler 创建请求包含 `start_number`；mock crawler 状态从 running 到 succeeded 后 backend 状态同步统计；crawler 连接失败将任务置为 failed。

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_crawl_api.py backend/tests/test_crawl_service.py -q
```

Expected: FAIL because crawl service and routes do not exist。

- [ ] **Step 3: Add start-number lookup to backend service**

在 `CrawlService` 中使用现有 SQLite 文档表查询目标组织文档 `doc_id` 的最大数字；解析格式 `<group>_<number>`，无匹配时返回 `1`。不新增表、不写任务历史。

- [ ] **Step 4: Implement backend service**

使用进程内字典、`threading.Lock` 和一个单线程后台执行器；任务创建时原子检查活动任务，生成 `crawl_<UTC timestamp>_<random suffix>`，先保存 pending，再异步 POST crawler 创建接口。

轮询循环：

```python
while crawler_status not in {"succeeded", "failed"}:
    time.sleep(CRAWL_POLL_INTERVAL_SECONDS)
    crawler_status = client.get(f".../api/v1/crawl/runs/{run_id}")
```

收到 crawler 状态后复制统计、文档 ID、清理结果和错误信息；crawler 请求异常时置为 failed。

- [ ] **Step 5: Add routes and unified errors**

在 `backend/app/main.py` 注入 `CrawlService`，新增 POST/GET 两个路由。POST 使用 `JSONResponse(status_code=202, ...)`；参数错误使用现有 `ERR_VALIDATION`；冲突使用 HTTP 409；未知任务使用 HTTP 404。

- [ ] **Step 6: Run focused backend tests**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_crawl_api.py backend/tests/test_crawl_service.py -q
```

Expected: all new backend tests PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/crawl_service.py backend/app/main.py backend/app/requirements.txt backend/tests/test_crawl_api.py backend/tests/test_crawl_service.py
git commit -m "feat: 添加后端爬虫任务接口"
```

### Task 4: 更新 Compose 三容器运行配置

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/Dockerfile`
- Modify: `crawler/Dockerfile`
- Modify: `.env.example`
- Test: `backend/tests/test_compose_crawler_boundary.py`

**Interfaces:**
- backend 使用 `CRAWLER_BASE_URL=http://crawler:8100`。
- crawler 使用 `BACKEND_BASE_URL=http://backend:8000`。
- crawler 使用 `expose: ["8100"]`，不使用 `ports`。

- [ ] **Step 1: Write configuration assertions**

使用 YAML 解析 `docker-compose.yml`，断言 crawler 有 `expose: 8100`、没有 `ports`，不挂载 `./data` 或 `./backend`；backend 有 crawler URL；crawler 有 backend URL；crawler command 启动 uvicorn 而不是 pytest。

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests/test_compose_crawler_boundary.py -q
```

Expected: FAIL against the current crawler test-only configuration。

- [ ] **Step 3: Implement Compose changes**

保留 backend/frontend 现有宿主机端口；crawler 改为服务模式并增加环境变量、内部 expose 和健康依赖配置。crawler 的运行时临时目录使用容器内部路径，不新增 backend/data volume。

- [ ] **Step 4: Build service images**

Run:

```bash
docker compose build backend crawler
```

Expected: backend and crawler images build successfully。

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml backend/Dockerfile crawler/Dockerfile .env.example backend/tests/test_compose_crawler_boundary.py
git commit -m "chore: 配置爬虫三容器运行边界"
```

### Task 5: 将 frontend 采集弹窗接入真实 API

**Files:**
- Create: `frontend/src/api/crawler.ts`
- Modify: `frontend/src/components/CrawlerModal.tsx`
- Modify: `frontend/src/components/CrawlerModal.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- `createCrawlRun(payload: CrawlRunRequest): Promise<CrawlRunCreated>`。
- `fetchCrawlRun(runId: string): Promise<CrawlRunStatus>`。
- `CrawlRunRequest = { keyword: string; limit: number; sources: number; filter: boolean }`。
- `CrawlRunStatus` 包含 `crawl_run_id`、`status`、五个统计字段、`document_ids`、`workspace_cleaned` 和 `error_message`。

- [ ] **Step 1: Write failing frontend tests**

使用 mock `fetch` 覆盖：点击开始发送正确 keyword/limit/sources/filter；创建响应后轮询 run ID；running 状态显示真实阶段；succeeded 显示真实 imported/skipped 统计并触发 `onSuccess`；failed 显示错误；运行期间关闭和输入控件 disabled。

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
docker compose run --rm frontend npm run test -- --run src/components/CrawlerModal.test.tsx
```

Expected: FAIL because the component still uses local timers and demo text。

- [ ] **Step 3: Implement crawler API client**

读取现有 `frontend/src/api/client.ts` 的 base URL 和错误处理风格，新增两个函数，均请求：

```text
${API_BASE_URL}/crawl/runs
${API_BASE_URL}/crawl/runs/{crawl_run_id}
```

统一解析 `{ success, data, error }`，HTTP 非 2xx 或 `success=false` 抛出 `Error`。

- [ ] **Step 4: Replace local simulation**

删除 timers、固定 stages 和“本地模拟”文案；新增 `crawlRunId`、真实 status、stats 和 error state。提交后每 1 秒轮询一次，收到终态停止；组件卸载或关闭时清理轮询 timer。保留现有来源 bitmask 计算和参数控件。

- [ ] **Step 5: Update UI tests and styles**

将测试文案改为真实任务语义，验证结果显示 backend 返回的数字；失败状态使用 warning/error 样式，不引入与现有视觉语言无关的新布局。

- [ ] **Step 6: Run frontend tests and build**

Run:

```bash
docker compose run --rm frontend npm run test -- --run
docker compose run --rm frontend npm run build
```

Expected: all frontend tests PASS and production build succeeds。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/crawler.ts frontend/src/components/CrawlerModal.tsx frontend/src/components/CrawlerModal.test.tsx frontend/src/styles.css
git commit -m "feat: 接入真实爬虫任务接口"
```

### Task 6: 端到端联调测试、文档更新和最终验证

**Files:**
- Modify: `docs/api-contract.md`
- Modify: `README.md`
- Modify: `TODO.md`
- Create: `backend/tests/test_crawl_end_to_end.py`

- [ ] **Step 1: Update API contract**

在 `docs/api-contract.md` 增加 `POST/GET /api/v1/crawl/runs`，明确请求字段、状态、409 冲突、内存生命周期和 crawler 仅内部访问边界；不删除仍在使用的旧 collection API 说明，避免扩大范围。

- [ ] **Step 2: Update runtime documentation**

在 README 的服务表和 API 入口补充 crawler 为 Compose 内部服务，说明开发阶段浏览器可访问 backend、不能访问 crawler，以及真实采集按钮的调用链。

- [ ] **Step 3: Add mocked end-to-end contract test**

通过 FastAPI `TestClient` 和 mock HTTP transport 串联 backend 创建任务、crawler accepted/running/succeeded、crawler 导入两篇 Document、backend 状态查询，断言最终统计和 SQLite 文档/chunks 写入。

- [ ] **Step 4: Run all backend and crawler tests**

Run:

```bash
docker compose run --rm backend python -m pytest backend/tests -q
docker compose run --rm crawler python -m pytest crawler/tests -q
```

Expected: all tests PASS。

- [ ] **Step 5: Run frontend checks**

Run:

```bash
docker compose run --rm frontend npm run test -- --run
docker compose run --rm frontend npm run build
docker compose run --rm frontend npm run format:check
```

Expected: tests and build PASS；若全量 format check 仍被既存文件阻断，记录具体既存文件，不修改无关格式。

- [ ] **Step 6: Start Compose and verify service boundaries**

Run:

```bash
docker compose up -d --build backend crawler frontend
docker compose ps
```

验证 backend health 返回 200；验证 frontend 页面返回 200；验证 crawler 没有宿主机端口映射；使用 backend API 创建任务时 backend 能访问 crawler。不得使用真实外部爬虫或真实 LLM Key 做自动化测试。

- [ ] **Step 7: Review diff and status**

Run:

```bash
git status --short --branch
git diff origin/feat/crawler...HEAD --stat
git log --oneline -10
```

确认只包含本任务文件，`temp/` 保持未跟踪且未加入提交。

- [ ] **Step 8: Commit documentation and integration tests**

```bash
git add docs/api-contract.md README.md TODO.md backend/tests/test_crawl_end_to_end.py
git commit -m "test: 完成三容器爬虫链路验收"
```

## Self-Review

- Spec coverage: backend API、crawler API、backend 轮询、脚本编号传递、metadata 更新、后端唯一查重、任务部分成功、临时目录清理、frontend 真实轮询和 Compose 网络边界均有对应任务。
- Placeholder scan: 本计划不使用 `TODO`、`TBD` 或“稍后补充”等实现占位描述。
- Type consistency: crawler 和 backend 均使用 `crawl_run_id`、`status`、`items_found`、`items_promoted`、`items_imported`、`items_skipped`、`items_failed`、`document_ids`、`workspace_cleaned`、`error_message`；frontend 客户端消费同一字段。
- Scope: 不新增任务历史表、不实现并行调度、不实现浏览器到 crawler 的访问、不修改既有文档查重契约。
