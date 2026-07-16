# 爬虫采集前端交互实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在“导入文档”右侧新增“采集情报”按钮及弹窗式采集交互演示，不调用后端采集接口。

**Architecture:** 新增独立 `CrawlerModal` 组件管理表单和模拟任务状态。`App.tsx` 只负责打开/关闭弹窗；来源选择使用固定 12 位 bitmask，弹窗显示十进制结果。开始后通过定时器展示采集、过滤、导入三个阶段，完成后通知用户刷新图谱。

**Tech Stack:** React 19、TypeScript、Vitest、Testing Library、现有 CSS/图标库。

## Global Constraints

- 采集按钮必须位于“导入文档”右侧。
- 点击后使用居中弹窗，不新增页面或路由。
- 当前版本只做交互演示，不请求 `/api/v1/crawl/runs`。
- 目标组织固定为 `APT28`、`Kimsuky`、`Lazarus`。
- 来源使用 12 个固定 bit，显示十进制 `sources`。
- 弹窗在移动端可用，不能破坏现有工具栏布局。

---

### Task 1: Add crawler modal tests

**Files:**
- Create: `frontend/src/components/CrawlerModal.test.tsx`

- [ ] **Step 1: Write failing tests**

覆盖按钮文案、默认目标、来源 bitmask、LLM 过滤开关、启动模拟任务后状态展示和关闭行为。

- [ ] **Step 2: Run focused tests**

```bash
npm --prefix frontend run test -- --run src/components/CrawlerModal.test.tsx
```

预期：因 `CrawlerModal` 尚不存在而失败。

### Task 2: Implement crawler modal and integrate toolbar

**Files:**
- Create: `frontend/src/components/CrawlerModal.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Implement form and bitmask behavior**

组件提供 `open`、`onClose`、`onSuccess` props，默认选择当前目标组织和第一个来源；来源变化即时计算 `sources`。

- [ ] **Step 2: Implement simulated progress**

点击开始后依次显示“正在发现来源”“正在清洗文档”“正在导入图谱”，使用可清理的 `setTimeout`，完成后显示模拟统计和刷新提示。

- [ ] **Step 3: Integrate beside import button**

在 `App.tsx` 导入文档按钮后紧邻添加采集按钮和 `CrawlerModal`，复用现有 `pipelineOpen` 的布局位置。

- [ ] **Step 4: Run focused tests**

```bash
npm --prefix frontend run test -- --run src/components/CrawlerModal.test.tsx
```

预期：新增测试全部通过。

### Task 3: Verify frontend preview

**Files:**
- Verify: `frontend/src/components/CrawlerModal.tsx`
- Verify: `frontend/src/components/CrawlerModal.test.tsx`
- Verify: `frontend/src/App.tsx`
- Verify: `frontend/src/styles.css`

- [ ] **Step 1: Run frontend test suite**

```bash
npm --prefix frontend run test -- --run
```

- [ ] **Step 2: Run formatting and production build**

```bash
npm --prefix frontend run format:check
npm --prefix frontend run build
```

- [ ] **Step 3: Start preview and check URL**

```bash
docker compose up -d frontend backend
```

检查 `http://localhost:5173` 返回 HTTP 200，并向用户提供该 URL。
