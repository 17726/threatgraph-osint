# 流水线可观察性 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让采集与文档 Pipeline 在前端和 Docker 日志中持续展示可关联、可诊断的真实执行过程，并完成一次可复现的课程演示验收。

**Architecture:** 保留现有单一复合 Pipeline 步骤，新增只描述过程的事件时间线与当前进度，不伪造独立成功步骤。文档 Pipeline 事件持久化到 SQLite；crawler 将采集、导入及子 Pipeline 的进度汇总到采集任务，backend 代理层透传并输出带任务标识的结构化日志；前端轮询并渲染当前阶段、百分比、任务标识和最近事件。

**Tech Stack:** FastAPI、Python 3.13、SQLite、httpx、React 19、TypeScript、Vitest、Docker Compose

---

### Task 1: 冻结可观察性 API 契约

**Files:**
- Modify: `docs/api-contract.md`
- Modify: `docs/demo-flow.md`

**Step 1:** 写明 Pipeline `progress` 与 `events` 字段，以及事件不是独立业务步骤的语义。

**Step 2:** 写明采集任务透传当前子 Pipeline 的 `job_id`、阶段和消息。

**Step 3:** 补充 Docker 调试命令与演示验收观察点。

### Task 2: 为文档 Pipeline 增加持久化事件

**Files:**
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/test_pipeline_service.py`

**Step 1: Write the failing test**

新增测试，要求任务状态包含有序 `events` 和最新 `progress`，失败事件保留文档、阶段、消息与时间。

**Step 2: Run test to verify it fails**

Run: `docker compose run --rm backend python -m pytest backend/tests/test_pipeline_service.py -k observability -v`

Expected: FAIL，因为尚无 `pipeline_job_events`、`progress` 与 `events`。

**Step 3: Write minimal implementation**

新增 `pipeline_job_events` 表与索引；在排队、认领、定位文档、选择抽取模式、调用 LLM、归一化建图、Neo4j 同步、成功与失败边界记录事件。每次事件同时输出包含 `job_id`、`phase`、`current/total` 的日志。

**Step 4: Run test to verify it passes**

Run: `docker compose run --rm backend python -m pytest backend/tests/test_pipeline_service.py -k observability -v`

Expected: PASS。

### Task 3: 贯穿 crawler 与子 Pipeline 调试上下文

**Files:**
- Modify: `crawler/app/service.py`
- Modify: `backend/app/services/crawl_service.py`
- Modify: `crawler/tests/test_crawler_service.py`
- Modify: `backend/tests/test_crawl_api.py`

**Step 1: Write the failing test**

新增测试，要求采集状态含最近事件，导入阶段能展示当前文档及子 Pipeline `job_id`、阶段、进度和错误。

**Step 2: Run test to verify it fails**

Run: `docker compose run --rm crawler python -m pytest crawler/tests/test_crawler_service.py -k observability -v`

Expected: FAIL，因为采集状态尚不返回 `events` 和 `pipeline` 上下文。

**Step 3: Write minimal implementation**

crawler 记录有限长度事件，轮询子 Pipeline 时把最新 `progress` 合并到采集任务；backend 只在状态发生变化时记录带 `crawl_run_id` 的日志，避免每次轮询刷屏。

**Step 4: Run test to verify it passes**

Run: `docker compose run --rm crawler python -m pytest crawler/tests/test_crawler_service.py -k observability -v`

Expected: PASS。

### Task 4: 前端展示实时过程与调试摘要

**Files:**
- Modify: `frontend/src/api/crawler.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/CrawlerModal.tsx`
- Modify: `frontend/src/components/PipelineModal.tsx`
- Modify: `frontend/src/components/CrawlerModal.test.tsx`
- Modify: `frontend/src/api/client.test.ts`
- Modify: `frontend/src/styles.css`

**Step 1: Write the failing test**

新增组件与客户端测试，要求展示任务 ID、当前阶段、百分比、当前文档/来源、最近事件和后端错误。

**Step 2: Run test to verify it fails**

Run: `docker compose run --rm frontend npm run test -- --run`

Expected: FAIL，因为 UI 尚未消费新字段。

**Step 3: Write minimal implementation**

扩展类型和轮询回调；两个弹窗均显示可复制的任务标识、阶段进度条、耗时与最近事件，终态保留调试摘要。

**Step 4: Run test to verify it passes**

Run: `docker compose run --rm frontend npm run test -- --run`

Expected: PASS。

### Task 5: Docker 演示验收

**Files:**
- Modify: `README.md`
- Modify: `docs/docker-runtime.md`

**Step 1:** 重建并启动 backend、crawler、frontend。

**Step 2:** 使用 `apt28_080` 的 `reviewed` 模式运行稳定 Pipeline，轮询并保存不同状态快照。

**Step 3:** 运行一次受控采集演示，验证前端状态与 `docker compose logs` 可用同一任务 ID 关联；若外部来源或 LLM 失败，保留真实错误作为降级验收证据。

**Step 4:** 运行完整后端、crawler、前端测试，以及前端 build 和 format:check。

**Step 5:** 检查 `git diff`，确认未提交 `.env`、密钥、运行档案或采集原始数据。
