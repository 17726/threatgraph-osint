# 关系图谱展示深度与快速布局实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为关系图谱增加 1–20 的实时展示深度输入，并让主图谱与邻居图谱请求携带深度，同时快速停止力导向布局。

**Architecture:** 复用后端已有 `depth` 查询参数，仅修改前端 API 客户端和 `App` 状态/交互。有效深度由页面维护，主图谱与当前邻居图谱分别按当前深度重新请求；图谱数据更新后通过 ECharts 实例停止 force 模拟。

**Tech Stack:** React 19、TypeScript、ECharts、Vitest、Testing Library。

---

### Task 1: 扩展图谱请求参数

**Files:**
- Modify: `frontend/src/api/client.ts:28-32`
- Modify: `frontend/src/api/client.ts:69-76`
- Test: `frontend/src/api/client.test.ts`

- [ ] 为 `fetchGraph` 增加 `depth: number` 参数，并将其编码到 `/graph` 查询字符串。
- [ ] 为 `fetchNeighbors` 增加 `depth: number` 参数，同时保留 `AbortSignal`。
- [ ] 更新客户端测试，断言两个请求都携带 `depth`。

### Task 2: 增加页面深度状态与实时刷新

**Files:**
- Modify: `frontend/src/App.tsx:28-103,208-226,361-375`
- Test: `frontend/src/App.test.tsx`

- [ ] 增加默认深度 2、输入值和输入提示状态。
- [ ] 主图谱请求使用当前有效深度。
- [ ] 节点邻居请求使用当前有效深度；深度变化时重新请求当前选中节点，否则重新请求主图谱。
- [ ] 输入数字时将值限制到 1–20；空值/非数字显示提示并阻止请求。
- [ ] 在“关系图谱”标题右侧渲染数字输入框及提示文本。
- [ ] 使用请求取消或序号校验，避免快速输入时旧响应覆盖新响应。
- [ ] 增加组件测试覆盖默认值、边界值和深度变化请求。

### Task 3: 加快 force 布局停止

**Files:**
- Modify: `frontend/src/App.tsx:172-206`
- Modify: `frontend/src/graphOptions.ts:59-70`

- [ ] 在图谱选项中缩短 force 布局迭代配置，保持漫游和拖拽。
- [ ] 在 ECharts 图谱数据更新后调用 `graphForceStop`，使新图快速固定。
- [ ] 确保图表实例仍由 `onChartReady` 保存并支持现有点击/图例事件。

### Task 4: 验证

**Files:**
- Review: `frontend/src/App.tsx`
- Review: `frontend/src/api/client.ts`
- Review: `frontend/src/graphOptions.ts`

- [ ] 运行 `npm --prefix frontend run test -- --run`。
- [ ] 运行 `npm --prefix frontend run build`。
- [ ] 运行 `npm --prefix frontend run format:check`；若项目无该脚本，记录原因。
- [ ] 检查 `git diff`，确认只包含需求相关修改及设计/计划文档。
