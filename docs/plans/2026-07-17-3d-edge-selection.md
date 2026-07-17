# 3D 关系选择与全屏详情 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 3D 图谱中的关系点击具有持续高亮反馈，并确保全屏状态下关系详情可见且可关闭。

**Architecture:** 保留 `react-force-graph-3d` 现有 `onLinkClick` 数据链路，在 `App` 中新增独立的 3D 关系聚焦状态，并由 `buildGraph3DData` 统一计算选中边、端点和无关元素的样式。将关系详情内容提取为复用组件；普通模式继续放在右侧栏，全屏模式则渲染到图谱面板内部的抽屉中，避免 Fullscreen API 隐藏面板外的兄弟节点。

**Tech Stack:** React 19、TypeScript、react-force-graph-3d、Vitest、Testing Library、Playwright CLI。

---

### Task 1: 增加 3D 关系聚焦数据状态

**Files:**

- Modify: `frontend/src/graphOptions.test.ts`
- Modify: `frontend/src/graphOptions.ts`

**Step 1: Write the failing test**

新增 `focusEdgeId` 用例，断言选中关系为橙色、宽度增大并显示粒子；两端节点保留类型色，无关节点和关系变暗。

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- graphOptions.test.ts`

Expected: FAIL，因为 `BuildOptions` 和 `buildGraph3DData` 尚未处理 `focusEdgeId`。

**Step 3: Write minimal implementation**

在三维数据适配层查找选中关系，将其端点加入可见聚焦集合，并让选中关系复用橙色强调样式。

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- graphOptions.test.ts`

Expected: PASS。

### Task 2: 接通 3D 点击关系状态与清除行为

**Files:**

- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Graph3D.tsx`

**Step 1: Write the failing test**

扩展 3D 关系点击用例，断言点击后关系数据变为强调样式，点击空白画布后恢复；节点点击与关系点击会互相清除聚焦状态。

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- App.test.tsx`

Expected: FAIL，因为当前 `onLinkClick` 只更新右侧详情，没有传递关系聚焦标识。

**Step 3: Write minimal implementation**

在 `App` 中维护 `focused3DEdgeId`，为 3D 关系点击建立独立回调，并将状态传给 `Graph3D`；空白点击、节点点击和详情关闭时清除关系聚焦。

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- App.test.tsx`

Expected: PASS。

### Task 3: 让全屏关系详情位于 Fullscreen 子树内

**Files:**

- Create: `frontend/src/components/GraphEdgeDetail.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Step 1: Write the failing test**

断言全屏状态点击 3D 关系后，关系详情渲染在图谱面板内部的全屏抽屉中，并可通过关闭按钮清除详情和聚焦。

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- App.test.tsx`

Expected: FAIL，因为当前关系详情只位于图谱面板外的 `side-panel`，进入 Fullscreen API 后不可见。

**Step 3: Write minimal implementation**

提取 `GraphEdgeDetail`；普通模式继续渲染到右侧栏，全屏模式渲染到 `graphPanelRef` 所在面板内部，并使用绝对定位抽屉样式覆盖在画布右侧。

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- App.test.tsx`

Expected: PASS。

### Task 4: 完整验证

**Files:**

- Modify: `docs/plans/2026-07-17-3d-edge-selection.md`

**Step 1:** 运行 `npm --prefix frontend run test`。

**Step 2:** 运行 `npm --prefix frontend run build`。

**Step 3:** 对本次改动文件运行 Prettier 检查，并运行 `git diff --check`。

**Step 4:** 用 Playwright 复测筛选后的简化 3D 图：hover 关系、点击关系高亮、全屏详情可见、空白清除。

**Step 5:** 使用中文 Conventional Commit 提交、推送并创建草稿 PR。
