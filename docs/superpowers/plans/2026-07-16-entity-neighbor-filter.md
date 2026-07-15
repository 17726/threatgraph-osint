# 实体一跳筛选实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前端实体搜索改为一跳关系筛选：选择实体后保留中心节点及其直接相邻节点，输入内容持续显示，清空输入后恢复当前组织图谱。

**Architecture:** 后端新增按实体标识查询一跳子图的接口，复用现有 GraphQueryService 的节点、关系和证据格式。前端 SearchBar 只负责搜索输入和选择，App 保存筛选状态并在选择/清空时切换图谱数据，不再提供“设为目标”按钮。

**Tech Stack:** FastAPI、SQLite BFS/关系查询、React、TypeScript、Vitest、pytest。

---

### Task 1: 后端提供实体一跳筛选接口

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/graph_query_service.py`
- Test: `backend/tests/test_graph_query_service.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 添加失败测试**

测试 `get_neighbors` 返回中心节点、所有一跳邻居和连接边；不存在实体返回空图。

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest backend/tests/test_graph_query_service.py -q
```

Expected: 新增用例因 `get_neighbors` 未实现而失败。

- [ ] **Step 3: 实现后端查询**

增加 `GET /api/v1/graph/neighbors?entity=<id或名称>`，接收实体名称或 ID，返回 `{nodes, edges, evidence}`。实体匹配复用名称、ID、别名的大小写不敏感匹配；结果只保留中心节点和与其直接相连的节点及边。

- [ ] **Step 4: 运行后端测试**

```powershell
python -m pytest backend/tests/test_graph_query_service.py backend/tests/test_api.py -q
```

Expected: PASS。

### Task 2: 前端搜索切换一跳图谱

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/SearchBar.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: 添加失败测试**

测试 `fetchNeighbors(entity)` 请求 `/graph/neighbors`，并覆盖返回 `{nodes, edges, evidence}` 的结构。

- [ ] **Step 2: 实现 API 客户端**

新增 `fetchNeighbors(entity: string)`。

- [ ] **Step 3: 调整 SearchBar 行为**

移除“设为目标”按钮；点击结果调用 `onSelect(node)`，保留 `query` 为所选实体名称；输入框被清空时调用 `onClear`。

- [ ] **Step 4: 调整 App 状态**

增加 `neighborGraph`/筛选实体状态：选择搜索结果后调用 `fetchNeighbors` 并替换当前展示图谱；清空输入后恢复当前 `graph`；搜索不修改顶部目标 `target`。

- [ ] **Step 5: 运行前端测试与构建**

```powershell
npm test -- --run
npm run build
```

Expected: PASS，构建成功。

### Task 3: 回归验证

**Files:**
- Modify: `backend/tests/test_graph_query_service.py`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: 运行全部后端测试**

```powershell
python -m pytest backend/tests/ -q
```

Expected: 现有测试全部通过。

- [ ] **Step 2: 检查交互结果**

验证搜索 `X-Agent` 后图谱包含 `X-Agent` 本身及一跳相邻节点；删除输入内容后恢复当前组织图谱；输入文本不会在选择后消失。

- [ ] **Step 3: 检查代码差异**

```powershell
git diff --check
```

Expected: 无输出。
