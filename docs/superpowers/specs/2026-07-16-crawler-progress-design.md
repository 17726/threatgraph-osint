# 采集任务真实进度设计

## 目标

将“采集情报”页面从硬编码的 `1/3`、`3/3` 改为展示 crawler 实际执行进度，覆盖采集、验证和导入/Live 建图三个阶段；同时恢复任务状态的宽松成功语义：至少一篇文档完成 Live Pipeline 即可将任务标记为 `succeeded`。

## 范围

- crawler 在任务状态中维护当前阶段、阶段计数、目标组织和当前来源。
- crawler 的采集、过滤、promote、导入和 Live Pipeline 边界更新进度。
- backend 原样转发 `progress` 字段。
- frontend 使用轮询状态渲染真实阶段进度和完成摘要。
- 保留现有总量统计字段和三容器调用链。

不包含：并行化来源采集、重新设计 crawler API、持久化采集任务进度到 SQLite、改变来源选择或 `limit` 语义。

## 状态契约

采集状态增加可选字段：

```json
{
  "progress": {
    "phase": "collecting",
    "current": 3,
    "total": 10,
    "target": "APT28",
    "source": "FreeBuf",
    "message": "正在采集"
  }
}
```

字段定义：

- `phase`：`collecting`、`validating`、`importing`、`completed`、`failed`。
- `current`：当前阶段已处理数量，从 `0` 开始，完成一项后递增。
- `total`：当前阶段总量；采集阶段为选中来源数乘以 `limit`，验证和导入阶段为实际进入该阶段的文档数。
- `target`：目标组织，例如 `APT28`。
- `source`：当前来源；验证和导入阶段没有单一来源时为 `null`。
- `message`：简体中文阶段文案。

旧客户端或异常状态缺少 `progress` 时，frontend 显示通用“任务正在执行”，不得假定 `3/3`。

## 阶段行为

### 采集

统一入口根据全局来源掩码计算选中来源数，初始化：

```text
phase=collecting
current=0
total=selected_source_count * limit
```

每个 crawler 成功写出一篇 Document 后递增 `current`，并写入当前来源。某来源没有结果、404 或单篇失败时不虚增进度，继续后续来源。

### 验证

启用过滤时，过滤脚本开始处理合并目录中的实际文件后切换：

```text
phase=validating
current=0
total=number_of_merged_documents
```

每个文件完成相关性判断、丢弃或清洗后递增 `current`。没有启用过滤时直接将验证阶段视为完成，进入导入阶段。

### 导入和 Live 建图

promote 完成后，crawler 按最终 `data/documents` 文件数初始化：

```text
phase=importing
current=0
total=promoted_document_count
```

每篇文档完成 import 和对应 Live Pipeline 轮询后递增 `current`。总量统计分别保持：

- `items_found`：实际发现并进入 import 的文档数。
- `items_promoted`：promote 生成的文档数。
- `items_imported`：backend 接受的新文档数。
- `items_pipeline_succeeded`：Live Pipeline 成功数。
- `items_pipeline_failed`：Live Pipeline 失败数。

### 终态

- 至少一篇 Live Pipeline 成功且 crawler 主流程未退出失败：`succeeded`。
- crawler 脚本退出失败：`failed`。
- 没有任何 Live Pipeline 成功：`failed`。
- `succeeded` 时 `progress.phase=completed`；`failed` 时 `progress.phase=failed`。

未达到每个来源 `limit` 不再单独导致整次任务失败；缺失来源通过 `source_results` 和最终摘要暴露。

## 前端展示

运行中显示：

```text
1/10 正在采集 目标：APT28 来源：奇安信
```

验证阶段显示：

```text
1/10 正在验证 目标：APT28
```

导入阶段显示：

```text
1/10 正在导入 目标：APT28
```

进度条百分比为 `current / total`，当 `total=0` 时显示 0%，避免除零。完成后显示：

```text
采集任务完成
发现 x 篇 · 清洗 y 篇 · 导入 z 篇
Live 建图成功 m 篇 · 失败 n 篇
```

## 测试策略

- crawler 单元测试验证三阶段状态初始化和递增、来源没有结果时不虚增、宽松终态判定。
- backend 测试验证 `progress` 原样转发和默认空值。
- frontend 测试验证采集、验证、导入三种文案和百分比，并验证缺少 `progress` 时的降级文案。
- 运行 crawler/backend/frontend 现有测试、frontend build 和 format check。
