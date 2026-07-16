# 爬虫采集 LLM 配置门禁实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留“采集情报”按钮的前提下，无有效 LLM 配置时禁用前端入口，并由 backend 拒绝采集任务创建。

**Architecture:** backend 通过统一配置函数检查 `LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY` 三项环境变量；health 接口暴露 `configured/not_configured`；frontend 加载 health 状态后控制按钮 disabled；crawl API 在创建任务前再次校验并返回 `503 ERR_LLM_NOT_CONFIGURED`。不做真实连通性探测。

**Tech Stack:** FastAPI、Python 3.13、SQLite、React 19、TypeScript、Vitest、pytest、Docker Compose。

## Global Constraints

- 三项配置去除首尾空白后必须全部非空：`LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`。
- 无有效配置时按钮始终显示但 `disabled=true`，不能隐藏。
- 无有效配置时 backend 不创建任务、不调用 crawler，返回 HTTP `503`、错误码 `ERR_LLM_NOT_CONFIGURED`、消息 `无有效 LLM 配置`。
- 配置门禁只检查字符串存在性，不发起 LLM 连通性探测。
- crawler 采集后的 Pipeline 固定使用 `extraction_mode=live`。
- 不修改 `temp/`，不提交 `.env` 或 API Key。

---

### Task 1: 提取统一 LLM 配置状态函数

**Files:**
- Create: `backend/app/core/llm_config.py`
- Modify: `backend/app/services/demo_store.py`
- Test: `backend/tests/test_llm_config.py`

**Interfaces:**
- `get_llm_config_status(environ: Mapping[str, str] | None = None) -> str`，返回 `configured` 或 `not_configured`。
- `has_valid_llm_config(environ: Mapping[str, str] | None = None) -> bool`。
- `missing_llm_config(environ: Mapping[str, str] | None = None) -> list[str]`。

- [ ] **Step 1: Write failing tests**

覆盖三项全非空返回 `configured`；任一缺失、空字符串或仅空白返回 `not_configured`；缺失字段按稳定顺序返回 `LLM_MODEL`、`LLM_BASE_URL`、`LLM_API_KEY`。

- [ ] **Step 2: Run tests and verify failure**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_llm_config.py -q
```

Expected: FAIL because `backend.app.core.llm_config` does not exist。

- [ ] **Step 3: Implement minimal configuration helpers**

使用 `os.environ` 默认输入，逐项执行 `str(value or "").strip()`，不得把默认 API URL 或默认 model 视为有效配置。

- [ ] **Step 4: Update health component status**

修改 `DemoStore.health()`，使用统一 helper 返回 LLM 状态，不再固定返回 `not_configured`。

- [ ] **Step 5: Run focused tests**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_llm_config.py backend/tests/test_api.py -q
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/llm_config.py backend/app/services/demo_store.py backend/tests/test_llm_config.py
git commit -m "feat: 统一 LLM 配置状态检查"
```

### Task 2: 增加 backend 采集 API 配置门禁

**Files:**
- Modify: `backend/app/services/crawl_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_crawl_api.py`
- Modify: `backend/tests/test_crawl_service.py`

**Interfaces:**
- `CrawlService.ensure_llm_configured() -> None`，无效配置抛出专用异常或 `ValueError`。
- `POST /api/v1/crawl/runs` 无效配置返回 HTTP `503`、`ERR_LLM_NOT_CONFIGURED`、`无有效 LLM 配置`。

- [ ] **Step 1: Write failing tests**

增加测试：清空三个环境变量后调用 crawl API，断言状态码 503、错误码和消息；mock crawler POST，断言未被调用；设置三项变量后原有创建任务测试继续使用正常流程。

- [ ] **Step 2: Run tests and verify failure**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_crawl_api.py -q
```

Expected: FAIL because当前 crawl API 未执行 LLM 配置门禁。

- [ ] **Step 3: Implement backend guard**

在 `CrawlService.submit()` 的参数校验后、活动任务检查前调用统一配置 helper。新增异常类型 `LLMNotConfiguredError` 或等价稳定判断；main route 捕获后返回：

```python
JSONResponse(
    status_code=503,
    content=error_response("ERR_LLM_NOT_CONFIGURED", "无有效 LLM 配置"),
)
```

保证 guard 发生在生成 run ID、写入内存和启动线程之前。

- [ ] **Step 4: Run focused backend tests**

```bash
docker compose run --rm backend python -m pytest backend/tests/test_crawl_api.py backend/tests/test_crawl_service.py backend/tests/test_llm_config.py -q
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/crawl_service.py backend/app/main.py backend/tests/test_crawl_api.py backend/tests/test_crawl_service.py
git commit -m "feat: 禁止无 LLM 配置启动采集"
```

### Task 3: Frontend health 状态和 disabled 入口

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/CrawlerModal.tsx`
- Modify: `frontend/src/components/CrawlerModal.test.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- `fetchHealth(): Promise<{ status: string; components: { llm: "configured" | "not_configured" | string } }>`。
- `App` 将 `llmConfigured` 传给 `CrawlerModal`。
- `CrawlerModalProps` 增加 `llmConfigured: boolean`。

- [ ] **Step 1: Write failing frontend tests**

覆盖：`llmConfigured=false` 时按钮仍存在、`disabled=true`，按钮或附近显示“需要有效 LLM 配置”；`llmConfigured=true` 时按钮可用；弹窗内部“开始采集”按钮也 disabled。保持现有采集参数和真实任务测试有效。

- [ ] **Step 2: Run tests and verify failure**

```bash
docker compose run --rm frontend npm run test -- --run src/components/CrawlerModal.test.tsx src/App.test.tsx
```

Expected: FAIL because当前 App/CrawlerModal 没有 health 状态和 disabled 门禁。

- [ ] **Step 3: Implement health API client**

在 `client.ts` 中使用现有 `getJson`，新增：

```typescript
export type HealthPayload = {
  status: string;
  components: { llm: string };
};

export function fetchHealth(): Promise<HealthPayload> {
  return getJson<HealthPayload>("/health");
}
```

- [ ] **Step 4: Load health in App and keep button visible**

App 初始 `llmConfigured=false`，加载 health 成功后按 `components.llm === "configured"` 更新；请求失败时保持 false。工具栏继续渲染“采集情报”按钮，增加 `disabled={!llmConfigured}` 和必要提示文案，不能条件删除按钮。

- [ ] **Step 5: Guard CrawlerModal**

弹窗接收 `llmConfigured`；无效时显示“需要有效 LLM 配置”，开始按钮 disabled，不调用 create API。直接打开 modal 的测试也覆盖该状态。

- [ ] **Step 6: Run frontend tests and build**

```bash
docker compose run --rm frontend npm run test -- --run
docker compose run --rm frontend npm run build
```

Expected: PASS and build succeeds。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/App.tsx frontend/src/components/CrawlerModal.tsx frontend/src/components/CrawlerModal.test.tsx frontend/src/App.test.tsx
git commit -m "feat: 无 LLM 配置时禁用采集入口"
```

### Task 4: 文档、Compose 验收和最终回归

**Files:**
- Modify: `docs/api-contract.md`
- Modify: `README.md`
- Modify: `TODO.md`
- Test: `backend/tests/test_crawl_llm_gate.py`

- [ ] **Step 1: Add API gate contract test**

使用 TestClient 验证 `/health` 在无配置时返回 `not_configured`，在全配置时返回 `configured`；验证 crawl API 无配置时返回 503 且 crawler mock 未调用。

- [ ] **Step 2: Update API documentation**

记录三项配置非空规则、health 状态、503 错误码和 frontend 按钮“显示但 disabled”的行为。

- [ ] **Step 3: Update README and TODO**

说明采集功能固定依赖 live Pipeline，启动采集前必须配置 `.env`；无配置时按钮不会隐藏，只会禁用。

- [ ] **Step 4: Run full verification**

```bash
docker compose run --rm backend python -m pytest backend/tests -q
docker compose run --rm crawler python -m pytest crawler/tests -q
docker compose run --rm frontend npm run test -- --run
docker compose run --rm frontend npm run build
docker compose config --quiet
```

Expected: backend/crawler/frontend 全部通过，构建成功，Compose 配置有效。

- [ ] **Step 5: Check diff and commit**

```bash
git diff --check
git status --short --branch
```

确认 `temp/` 未加入提交后：

```bash
git add docs/api-contract.md README.md TODO.md backend/tests/test_crawl_llm_gate.py
git commit -m "docs: 完善采集 LLM 配置门禁说明"
```

## Self-Review

- Spec coverage: 配置判定、health 状态、backend 503 门禁、crawler 不启动、frontend 按钮保持显示且 disabled、测试和文档均有对应任务。
- No placeholders: 本计划不依赖 TBD、TODO 或未定义的实现步骤。
- Type consistency: backend 使用 `configured/not_configured`，frontend 仅将 `components.llm === "configured"` 映射为可用；crawl API 错误码固定为 `ERR_LLM_NOT_CONFIGURED`。
