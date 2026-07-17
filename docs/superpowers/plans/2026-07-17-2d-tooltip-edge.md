# 2D 关系悬浮框修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 2D ECharts 关系悬浮框缺少关系类型和置信度的问题。

**Architecture:** 在 `buildGraphOption` 的关系适配层补齐 ECharts 需要的 `id`、`type` 和 `value` 展示字段，继续保留 `_raw` 供点击事件使用。通过 `graphOptions.test.ts` 验证关系数据映射和 tooltip formatter 输出，不修改 API 或页面详情逻辑。

**Tech Stack:** React、TypeScript、ECharts、Vitest、Prettier。

## Global Constraints

- 只修改前端图谱选项和对应测试，不修改后端 API、SQLite、数据契约或 `GraphEdge` 类型。
- 关系 `value` 使用 `Number(edge.confidence.toFixed(2))`，tooltip 正常置信度显示两位小数。
- 保留无效关系的“【系统推断】”标记和 `_raw` 点击回传行为。
- 不引入新依赖，不进行无关重构。

---

### Task 1: 固定 2D 关系 tooltip 回归行为

**Files:**
- Modify: `frontend/src/graphOptions.test.ts`
- Test: `frontend/src/graphOptions.test.ts`

**Interfaces:**
- Consumes: `buildGraphOption(payload: GraphPayload, opts?: BuildOptions)`。
- Produces: 对 `series[0].links[0]` 的字段映射和 tooltip formatter 输出的可执行断言。

- [ ] **Step 1: 添加关系映射和 tooltip 的失败测试**

在现有 `describe("3D 图谱数据适配", ...)` 后增加以下测试。通过 `unknown` 转换读取 ECharts option，避免把测试绑定到 ECharts 内部复杂类型；测试只验证当前适配层对外产生的字段。

```tsx
describe("2D 图谱关系 tooltip", () => {
  it("映射关系类型、置信度和稳定标识", () => {
    const option = graphOptions.buildGraphOption(payload) as {
      series: Array<{
        links?: Array<Record<string, unknown>>;
      }>;
    };
    const relation = option.series[0].links?.[0];

    expect(relation).toMatchObject({
      id: "rel:apt28:uses:x-agent",
      name: "使用",
      type: "USES",
      value: 0.91,
      _raw: payload.edges[0],
    });
  });

  it("悬浮关系时显示真实类型和置信度", () => {
    const option = graphOptions.buildGraphOption(payload) as {
      tooltip: {
        formatter: (params: unknown) => string;
      };
    };
    const relation = {
      name: "攻击目标",
      type: "TARGETS",
      value: 0.95,
      _raw: { validation_status: "valid" },
    };

    const tooltip = option.tooltip.formatter({ data: relation });

    expect(tooltip).toBe("攻击目标<br/>类型：TARGETS<br/>置信度：0.95");
  });
});
```

- [ ] **Step 2: 运行新增测试确认当前实现失败**

Run:

```bash
npm --prefix frontend run test -- --run src/graphOptions.test.ts
```

Expected: 新增的关系字段断言失败，当前关系数据没有 `id`、`type` 和 `value`；该失败证明测试覆盖了现有缺陷。

### Task 2: 补齐关系 ECharts 展示字段

**Files:**
- Modify: `frontend/src/graphOptions.ts:187-204`

**Interfaces:**
- Consumes: `payload.edges: GraphEdge[]`。
- Produces: 每条 ECharts 关系数据包含 `id`、`name`、`type`、`value` 和 `_raw`，点击事件仍通过 `_raw` 回传原始 `GraphEdge`。

- [ ] **Step 1: 修改关系映射为完整展示数据**

将 `payload.edges.map` 中的返回对象调整为以下结构，保留现有高亮和虚线逻辑：

```tsx
return {
  id: edge.id,
  source: edge.source,
  target: edge.target,
  name: edge.label,
  type: edge.type,
  value: Number(edge.confidence.toFixed(2)),
  lineStyle:
    highlightSet.size > 0 || isSearched
      ? { opacity: pathEdge ? 1 : 0.08 }
      : isInfer
        ? { opacity: 0.4, type: "dashed" as const, color: "#9ca3af" }
        : undefined,
  _raw: edge,
};
```

- [ ] **Step 2: 运行图谱选项测试确认通过**

Run:

```bash
npm --prefix frontend run test -- --run src/graphOptions.test.ts
```

Expected: `graphOptions.test.ts` 全部通过，新增关系映射和 tooltip 断言通过，现有 3D 数据适配断言不受影响。

### Task 3: 完整验证并检查差异

**Files:**
- Verify: `frontend/src/graphOptions.ts`
- Verify: `frontend/src/graphOptions.test.ts`

**Interfaces:**
- Consumes: Task 2 的实现和 Task 1 的回归测试。
- Produces: 前端测试、构建、格式检查和 Git 差异检查结果。

- [ ] **Step 1: 运行前端全量测试**

Run:

```bash
npm --prefix frontend run test
```

Expected: Vitest 进程成功退出，所有测试通过。

- [ ] **Step 2: 运行前端生产构建**

Run:

```bash
npm --prefix frontend run build
```

Expected: TypeScript 检查和 Vite 构建成功。

- [ ] **Step 3: 运行格式检查和差异检查**

Run:

```bash
npm --prefix frontend run format:check
```

Expected: Prettier 检查通过，`git diff --check` 无输出并成功退出。

- [ ] **Step 4: 检查最终变更范围**

Run:

```bash
git diff -- frontend/src/graphOptions.ts frontend/src/graphOptions.test.ts
```

Expected: 仅包含本次关系 tooltip 修复相关文件和既有设计/计划文档，不包含 `.env`、依赖锁文件或后端改动。
