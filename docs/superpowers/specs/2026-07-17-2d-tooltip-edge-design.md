# 2D 图谱关系悬浮框修复设计

日期：2026-07-17
分支：`fix/fe/2d-tooltip-overflow`

## 1. 问题与根因

2D ECharts 图谱悬浮到关系边时，当前显示类似以下内容：

```text
攻击目标
类型：关系
置信度：-
```

但点击同一条关系后，右侧详情能够正确显示关系类型 `TARGETS`、置信度 `0.95` 和证据，说明 API 数据与页面详情数据没有丢失。

根因位于 `frontend/src/graphOptions.ts` 的 ECharts 数据适配：

- 节点数据将节点类型映射为 `type`，将节点置信度映射为 `value`。
- 关系数据目前只映射 `source`、`target`、`name`、样式字段和 `_raw`。
- tooltip formatter 对节点和关系统一读取 `data.type` 与 `data.value`。
- 关系数据缺少这两个展示字段后，类型回退为“关系”，置信度回退为“-”。

右侧关系详情直接读取 `_raw` 中的原始 `GraphEdge`，因此不会暴露该适配缺口。

## 2. 设计目标与非目标

### 目标

- 让 2D 关系悬浮框展示原始关系类型和置信度。
- 保持节点悬浮框、关系点击、节点点击、筛选、高亮和 3D 图谱行为不变。
- 通过单元测试固定节点和关系的 tooltip 展示数据契约。
- 对置信度展示保持稳定格式，正常数值显示两位小数。

### 非目标

- 不修改后端 API、SQLite、图谱数据契约或 `GraphEdge` 类型。
- 不重构 ECharts tooltip 为多套组件。
- 不改变右侧关系详情的内容和布局。
- 不处理与本问题无关的 3D tooltip 或全屏布局问题。

## 3. 方案

在 `buildGraphOption` 的关系映射中补充 ECharts 展示字段：

```text
id:     edge.id
type:   edge.type
value:  Number(edge.confidence.toFixed(2))
name:   edge.label
_raw:   edge
```

这样节点和关系都遵循同一套 tooltip 展示字段：

- `name`：节点名称或关系显示标签。
- `type`：节点实体类型或关系类型。
- `value`：节点或关系置信度。
- `_raw`：用于点击事件回传和关系有效性标签判断的原始对象。

关系的 `id` 同时补齐，避免 ECharts 在关系重绘、事件参数或同标签关系场景中依赖隐式标识。

tooltip formatter 保留当前统一结构，并将置信度格式化为两位小数；没有可用数值时仍显示 `-`。该格式化仅影响悬浮框，不改变原始 `GraphEdge.confidence`。

## 4. 数据流与交互

```text
GraphPayload.edges
        │
        ▼
buildGraphOption
        │  映射 type/value/id/name/_raw
        ▼
ECharts graph.series.links
        │
        ├── tooltip formatter → 关系标签、类型、置信度
        └── click handler → _raw → App.selectedEdge → 右侧关系详情
```

关系悬浮框预期显示：

```text
攻击目标
类型：TARGETS
置信度：0.95
```

若关系为无效校验状态，仍在名称前显示“【系统推断】”；该已有行为不变。

## 5. 测试设计

在 `frontend/src/graphOptions.test.ts` 增加 2D 图谱选项测试：

- 从返回的 ECharts option 中取得关系数据，验证关系包含正确的 `id`、`name`、`type`、`value` 和 `_raw`。
- 调用 tooltip formatter 模拟关系悬浮参数，验证输出包含关系标签、`TARGETS` 和 `0.95`，且不包含错误的“类型：关系”或“置信度：-”。
- 保留现有 3D 数据适配测试，确认原始 payload 未被修改。

验证命令：

```bash
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run format:check
git diff --check
```

若本机缺少前端依赖，先按仓库已有锁文件安装依赖，不修改依赖版本；无法安装或运行时在最终结果中明确说明。

## 6. 验收标准

- 2D 图谱悬浮关系时显示真实关系类型，例如 `TARGETS`。
- 2D 图谱悬浮关系时显示真实置信度，例如 `0.95`。
- 无效关系仍显示“【系统推断】”标记。
- 点击关系后右侧详情仍显示原有关系字段和证据。
- 节点悬浮内容不回归。
- 前端测试、构建、格式检查和 diff 检查通过。
- 本次变更只涉及前端图谱选项、对应测试和本设计文档。
