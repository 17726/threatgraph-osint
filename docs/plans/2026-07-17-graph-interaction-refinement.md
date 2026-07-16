# 图谱交互优化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 2D 图谱平移后边缘区域无法继续拖拽或缩放的问题，并为 2D/3D 提供一致、清晰的类型标签筛选和 3D 点击聚焦效果。

**Architecture:** 继续由 `App` 维护跨视图的筛选和详情状态，用独立 React 标签栏替代 ECharts 内置 legend，避免图例内部状态与 React 状态互相覆盖。2D 显式启用全画布漫游命中；3D 使用独立的点击聚焦节点状态，并在数据适配层计算主体、相邻节点和关系的明暗样式。

**Tech Stack:** React 19、TypeScript、ECharts 6、react-force-graph-3d、Vitest、Playwright CLI。

---

### Task 1: 修复 2D 全画布拖拽与缩放

**Files:**

- Modify: `frontend/src/graphOptions.ts`
- Test: `frontend/src/graphOptions.test.ts`

**Step 1: Write the failing test**

在 `buildGraphOption` 的 graph series 上断言 `roam: true` 且 `roamTrigger: "global"`，保证平移后的空白画布仍然接受拖拽和滚轮。

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- graphOptions.test.ts`

Expected: FAIL，因为现有 graph series 没有 `roamTrigger`。

**Step 3: Write minimal implementation**

为 ECharts graph series 增加 `roamTrigger: "global"`，不增加额外几何边界或隐藏缩放限制。

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- graphOptions.test.ts`

Expected: PASS。

### Task 2: 统一 2D/3D 类型标签筛选

**Files:**

- Create: `frontend/src/components/GraphLegend.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/graphOptions.ts`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

**Step 1: Write the failing tests**

断言 2D 和 3D 都显示同一组类型按钮；点击类型后按钮进入选中态并筛选图谱；点击“全部”一次即可清除；切换视图时筛选状态保持一致。

**Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- App.test.tsx`

Expected: FAIL，因为当前标签只存在于 ECharts 内部，3D 无标签栏且没有“全部”入口。

**Step 3: Write minimal implementation**

新增受控的 `GraphLegend`，由 `App` 提供类别、当前值和更新回调；从 ECharts option 移除内置 legend 及 `legendselectchanged` 状态同步。

**Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend run test -- App.test.tsx`

Expected: PASS。

### Task 3: 增加 3D 点击聚焦

**Files:**

- Modify: `frontend/src/components/Graph3D.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/graphOptions.ts`
- Test: `frontend/src/graphOptions.test.ts`
- Test: `frontend/src/App.test.tsx`

**Step 1: Write the failing tests**

断言点击 3D 节点后，主体为强调色、相邻节点保持类型色、无关节点和关系变暗；点击画布空白处清除聚焦；2D 节点选择不会自动成为 3D 聚焦状态。

**Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- App.test.tsx graphOptions.test.ts`

Expected: FAIL，因为当前 3D 点击只打开详情，没有独立聚焦状态。

**Step 3: Write minimal implementation**

在 `App` 中维护 3D 聚焦节点，向 `Graph3D` 传入 `focusNodeId` 和空白点击回调；数据适配层计算聚焦邻接集合；3D 打开详情时不再用整幅遮罩覆盖图谱。

**Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend run test -- App.test.tsx graphOptions.test.ts`

Expected: PASS。

### Task 4: 完整验证并更新 PR

**Files:**

- Modify: `docs/plans/2026-07-17-graph-interaction-refinement.md`

**Step 1:** 运行 `npm --prefix frontend run test`。

**Step 2:** 运行 `npm --prefix frontend run build`。

**Step 3:** 对本次改动文件运行 Prettier 检查，并运行 `git diff --check`。

**Step 4:** 用 Playwright 在真实数据下验证：2D 连续边缘拖拽与缩放、2D/3D 标签筛选、3D 点击聚焦与清除。

**Step 5:** 使用中文 Conventional Commit 提交并推送到 `feat/fe/graph-3d-toggle`，确认 PR #74 自动更新。
