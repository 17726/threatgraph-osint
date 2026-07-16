# 三容器爬虫 API 对接设计

## 1. 目标与范围

本次工作将已有的爬虫脚本和前端采集交互接入为可运行的三容器 HTTP 流水线：

```text
浏览器 -> frontend
浏览器 -> backend:8000/api/v1/*
backend -> crawler:8100/api/v1/*
crawler -> backend:8000/api/v1/documents/import
```

开发阶段允许浏览器直接请求宿主机暴露的 backend API；crawler 只加入 Compose 内部网络，不映射宿主机端口，浏览器不能直接访问 crawler。

本次范围包括：

- backend 采集任务创建和状态查询 API；
- crawler HTTP 服务、异步执行和状态查询 API；
- backend 轮询 crawler 状态；
- crawler 逐篇调用 backend 文档导入 API；
- `start_number` 在 backend、crawler、调度脚本和 promote 之间传递；
- promote 的正式编号和 metadata 路径字段更新；
- crawler 临时目录清理；
- frontend 从本地模拟切换为真实任务创建和轮询；
- Compose 服务启动、内部地址和测试配置。

本次不包括：

- 采集任务历史查询和持久化；
- 多任务并行调度；
- 定时采集、checkpoint 和复杂增量策略；
- crawler 直接访问 SQLite 或 backend 文件；
- 浏览器直接访问 crawler；
- 新增 source_url 查重规则。

## 2. 任务模型

frontend 只提交以下业务参数：

```json
{
  "keyword": "APT28",
  "limit": 2,
  "sources": 1033,
  "filter": false
}
```

参数规则：

- `keyword` 只能是 `APT28`、`Kimsuky` 或 `Lazarus`；
- `limit` 必须是正整数；
- `sources` 是十进制整数 bitmask，范围为 `1` 到 `4095`；
- `filter` 是布尔值，缺省时按 `false` 处理；
- frontend 不生成 `crawl_run_id`；
- backend 生成并在本次任务的所有请求中复用 `crawl_run_id`。

任务状态只保存在 backend 进程内存中，当前不新增 SQLite 表。backend 重启后任务记录消失，当前运行中的任务不做恢复。该取舍符合单浏览器、单任务和暂无历史采集查询的开发阶段需求。

状态流转为：

```text
pending -> running -> succeeded
                  -> failed
```

最终状态采用部分成功规则：至少有一篇文档成功导入时任务为 `succeeded`；没有任何文档成功导入时任务为 `failed`。采集器、过滤器、promote 或单篇导入错误记录到统计和错误字段，单篇导入失败后继续处理其他文档。

## 3. Backend API

### 3.1 创建采集任务

```text
POST /api/v1/crawl/runs
```

请求体使用上节任务模型。backend 执行以下步骤：

1. 校验业务参数；
2. 检查是否已有 `pending` 或 `running` 任务，有则返回 HTTP 409；
3. 查询 SQLite 中该目标组织当前最大正式文档编号；
4. 计算 `start_number = max_number + 1`，无历史文档时为 `1`；
5. 生成唯一 `crawl_run_id`；
6. 创建内存任务并置为 `pending`；
7. 向 crawler 创建任务；
8. 启动 backend 后台轮询 crawler 状态；
9. 返回任务 ID 和 `pending` 状态。

成功响应：

```json
{
  "success": true,
  "data": {
    "crawl_run_id": "crawl_20260716_001",
    "status": "pending"
  },
  "timestamp": "2026-07-16T00:00:00+08:00"
}
```

参数错误返回 HTTP 400 和 `ERR_VALIDATION`；已有运行任务返回 HTTP 409；crawler 创建请求失败时任务置为 `failed`。

### 3.2 查询采集任务

```text
GET /api/v1/crawl/runs/{crawl_run_id}
```

返回任务参数、状态、统计、已导入文档 ID、清理结果和错误信息：

```json
{
  "success": true,
  "data": {
    "crawl_run_id": "crawl_20260716_001",
    "keyword": "APT28",
    "status": "succeeded",
    "items_found": 4,
    "items_promoted": 2,
    "items_imported": 1,
    "items_skipped": 1,
    "items_failed": 0,
    "document_ids": ["apt28_108"],
    "workspace_cleaned": true,
    "error_message": null
  },
  "timestamp": "2026-07-16T00:00:00+08:00"
}
```

未知任务返回 HTTP 404。backend 轮询 crawler 时将 crawler 的最终状态和统计同步到此响应；frontend 只查询 backend，不访问 crawler。

## 4. Backend 与 Crawler HTTP 链路

backend 创建 crawler 任务：

```text
POST http://crawler:8100/api/v1/crawl/runs
```

请求：

```json
{
  "crawl_run_id": "crawl_20260716_001",
  "keyword": "APT28",
  "limit": 2,
  "sources": 1033,
  "filter": false,
  "start_number": 108
}
```

crawler 立即返回：

```json
{
  "crawl_run_id": "crawl_20260716_001",
  "status": "accepted"
}
```

backend 通过以下接口轮询 crawler：

```text
GET http://crawler:8100/api/v1/crawl/runs/{crawl_run_id}
```

crawler 状态响应包含任务状态和统计字段。backend 轮询间隔使用固定的短间隔，收到 `succeeded` 或 `failed` 后停止轮询。crawler 不提供浏览器访问入口。

crawler 逐篇导入 Document：

```text
POST http://backend:8000/api/v1/documents/import
```

backend 现有文档契约校验、`doc_id OR content_hash` 查重、SQLite 写入和 chunks 生成逻辑保持不变。crawler 不在本地执行正式查重。

## 5. Crawler 内部流程

每个 crawler 任务在 crawler 容器自己的临时目录中执行：

1. 创建以 `crawl_run_id` 隔离的工作区；
2. 执行 `run_all_crawlers.py`，传递 `keyword`、`limit`、`sources`、`filter` 和 `start_number`；
3. 未开启过滤时从 `cleaned` promote，开启过滤时先生成 `cleaned_filtered` 再 promote；
4. promote 按 `start_number` 生成正式 `doc_id`；
5. crawler 读取 promote 生成的 JSON；
6. 逐篇调用 backend 文档导入接口；
7. 汇总发现、promote、导入、跳过和失败数量；
8. 在 `finally` 中清理 `cleaned`、`cleaned_filtered` 和 `documents`；
9. 发布最终状态供 backend 轮询。

采集、过滤、promote、HTTP 导入或清理发生错误时，任务必须保留可查询的错误信息。单篇 Document 导入错误不阻断后续文档。

## 6. Promote 与调度器变更

`run_all_crawlers.py` 增加：

```text
--start-number INTEGER
```

默认值为 `1`，并将该值传递给 promote。

`promote_cleaned_documents.py` 增加：

```text
--start-number INTEGER
```

promote 扫描输入目录下的全部 JSON 文档，不依赖 backend 文件或 SQLite，不执行 source URL、content hash 或本地正式文档查重。

每篇文档必须同步更新：

- JSON 顶层 `doc_id`；
- 输出文件名；
- metadata 中明确的 `doc_id`、`document_id`、`legacy_doc_id`、`source_path`、`cleaned_path` 和 `document_path` 字段。

以下内容不替换：

- `content_hash`；
- `clean_text`；
- `crawl_run_id`；
- 普通 `note`、`description` 文本；
- URL 查询参数。

## 7. Frontend 交互

开发阶段 frontend 继续通过 `VITE_API_BASE_URL=http://localhost:8000/api/v1` 直接访问 backend，浏览器不获得 crawler 地址。

`CrawlerModal` 的本地定时模拟替换为真实调用：

1. 点击开始后调用 backend 创建任务接口；
2. 保存响应中的 `crawl_run_id`；
3. 按固定间隔轮询 backend 状态接口；
4. 根据真实状态展示发现、清洗、导入和统计结果；
5. `succeeded` 时调用 `onSuccess()` 刷新图谱；
6. `failed` 时展示错误信息和已完成统计；
7. 任务运行期间禁用参数输入和关闭操作。

## 8. Compose 运行边界

backend 增加：

```text
CRAWLER_BASE_URL=http://crawler:8100
```

crawler 增加：

```text
BACKEND_BASE_URL=http://backend:8000
```

crawler 服务使用 `expose: 8100`，不使用宿主机 `ports` 映射。crawler 只挂载自身代码、脚本和自身运行时临时目录，不挂载 backend、SQLite 或项目级 `data` 目录。backend 继续挂载自己的 SQLite 数据目录。

## 9. 测试与验收

### Backend

- 校验 `keyword`、`limit`、`sources`、`filter`；
- 运行任务冲突返回 409；
- 正确生成 `start_number`；
- 正确创建 crawler 任务；
- 正确轮询并同步 crawler 状态；
- crawler 不可用时任务失败；
- 未知任务返回 404。

### Crawler

- HTTP 创建和查询接口；
- 参数传递到调度脚本；
- `start_number` 传递到 promote；
- 逐篇导入和统计 `imported/skipped/failed`；
- 单篇失败后继续；
- 成功、失败和异常路径都清理临时目录；
- 不读写 backend 文件或 SQLite。

### Scripts

- `--start-number` 默认值和显式值；
- 全目录扫描；
- doc ID、文件名和 metadata 字段更新；
- 不执行本地正式查重。

### Frontend

- 创建任务请求；
- 成功轮询和真实统计展示；
- 失败轮询和错误展示；
- 运行期间禁用控件；
- 完成后刷新图谱。

### 容器链路

使用独立测试和 Compose 启动验证以下流程：

```text
frontend -> backend 创建任务
backend -> crawler 创建并轮询任务
crawler -> backend 导入 Document
backend -> SQLite 写入并生成 chunks
frontend -> backend 查询最终状态
```
