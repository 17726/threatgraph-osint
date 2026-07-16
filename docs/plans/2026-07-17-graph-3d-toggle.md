# 2D/3D 图谱切换实施计划

**目标：** 在不改变后端图谱契约的前提下，为知识图谱页面增加可保留现有交互的 2D/3D 视图切换。

**架构：** 现有 ECharts 继续负责默认 2D 视图；新增独立的 React Force Graph 3D 组件，将同一份 `GraphPayload` 适配为 `nodes/links`。筛选、搜索、路径追踪和详情状态仍由 `App` 统一管理，3D 组件只负责渲染和将节点/关系点击回传给页面。

**技术栈：** React 19、TypeScript、ECharts、react-force-graph-3d、Three.js、Vitest。

---

### 任务 1：固定视图切换行为

**文件：**

- 修改：`frontend/src/App.test.tsx`
- 修改：`frontend/src/App.tsx`

1. 添加默认显示 2D、点击后显示 3D、再次切回 2D 的失败测试。
2. 运行 `npm --prefix frontend run test -- App.test.tsx`，确认测试因缺少切换功能失败。
3. 实现最小视图状态和可访问的切换按钮。
4. 重新运行测试并确认通过。

### 任务 2：适配并渲染 3D 图谱

**文件：**

- 新建：`frontend/src/components/Graph3D.tsx`
- 新建：`frontend/src/graphOptions.test.ts`
- 修改：`frontend/src/graphOptions.ts`
- 修改：`frontend/package.json`
- 修改：`frontend/package-lock.json`

1. 添加节点、关系数据适配以及点击回调的失败测试。
2. 安装 `react-force-graph-3d` 和 `three`。
3. 实现 3D 节点配色、大小、路径/搜索高亮、关系方向箭头和点击回调。
4. 运行组件测试，确认通过后整理共享颜色配置。

### 任务 3：接入页面和样式

**文件：**

- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/styles.css`

1. 将 3D 组件接入现有过滤后的图谱数据。
2. 复用节点详情、关系详情、路径高亮和搜索高亮状态。
3. 增加图谱工具栏、3D 白色画布以及响应式尺寸样式。

### 任务 4：完整验证

1. 运行 `npm --prefix frontend run test`。
2. 运行 `npm --prefix frontend run build`。
3. 运行 `npm --prefix frontend run format:check`。
4. 检查 `git diff --check`、当前分支和最终差异，确认没有修改后端或契约。
