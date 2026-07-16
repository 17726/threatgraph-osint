# 三容器爬虫流水线设计

## 1. 目标与约束

最终运行三个应用容器：

```text
frontend、backend、crawler
```

目标是让用户通过 frontend 选择目标组织、采集数量和数据源，由 backend 创建一次采集任务，crawler 执行三个爬虫并通过 HTTP 把标准 Document 导入 backend，最终由 backend 写入 SQLite 并生成 chunks。

本方案约束如下：

1. 浏览器只能访问 frontend，不能直接访问 backend 或 crawler。
2. 所有容器之间只通过 HTTP 通信。
3. backend 与 crawler 不共享文件目录，不共享 SQLite 文件，不直接读取对方文件。
4. 同一时间只运行一个浏览器和一个采集任务，不考虑并行采集。
5. SQLite 是唯一事实源。
6. crawler 内部允许使用自己的临时文件，但任务结束后必须清理 `cleaned`、`cleaned_filtered` 和 `documents`。
7. crawler 和 promote 不负责正式查重，查重完全由 backend 的 Document 导入接口执行。

## 2. 总体架构

```text
┌──────────────────────────────┐
│ Browser                      │
│ 只能访问 frontend             │
└──────────────┬───────────────┘
               │ HTTP
               ▼
┌──────────────────────────────┐
│ frontend                     │
│ React + Vite                 │
│ 组织选择 / 数量 / 来源 / 状态 │
└──────────────┬───────────────┘
               │ HTTP
               ▼
┌──────────────────────────────┐
│ backend                      │
│ FastAPI + SQLite             │
│ 任务管理 / 编号 / 导入 / chunks│
└──────────────┬───────────────┘
               │ HTTP
               ▼
┌──────────────────────────────┐
│ crawler                      │
│ crawler API + crawler scripts│
│ 采集 / 过滤 / promote / 导入  │
└──────────────┬───────────────┘
               │ HTTP JSON
               └──────────────► backend /api/v1/documents/import
```

容器访问关系：

```text
frontend -> backend
backend -> crawler
crawler -> backend
```

禁止以下链路：

```text
Browser -> backend
Browser -> crawler
frontend -> crawler
crawler -> SQLite
crawler -> backend data volume
backend -> crawler data volume
```

frontend 对外提供页面和前端资源；实际 API 请求通过 frontend 所在部署环境的代理或网关转发到 backend。浏览器不直接建立到 backend 或 crawler 的访问路径。

## 3. 业务参数

frontend 只提交以下业务参数：

```json
{
  "keyword": "APT28",
  "limit": 2,
  "sources": 1033,
  "filter": false
}
```

`keyword` 同时表示：

```text
目标组织
网页搜索关键词
临时目录名称来源
正式 doc_id 前缀来源
```

当前只允许三个值：

```text
APT28
Kimsuky
Lazarus
```

不再同时传 `target_group` 和 `keyword`，避免在当前固定场景下产生两个可能不一致的组织字段。

`limit` 必须是正整数，语义为每个启用来源最多采集的文章数量。

`filter` 为可选布尔值：

```text
false：cleaned -> promote
true：cleaned -> filter -> cleaned_filtered -> promote
```

## 4. sources 整数 bitmask

frontend 的数据源复选框转换为十进制整数 `sources`。backend 和 crawler 将其作为 bitmask 处理，不使用逗号字符串。

当前固定 12 位布局：

```text
bit 0  -> crawler_v1.qianxin
bit 1  -> crawler_v1.thehackernews
bit 2  -> crawler_v1.unit42
bit 3  -> crawler_v1.freebuf

bit 4  -> crawler_supplementary.chainalysis
bit 5  -> crawler_supplementary.trmlabs
bit 6  -> crawler_supplementary.microsoft
bit 7  -> crawler_supplementary.securelist

bit 8  -> crawler_supplementary_v2.crowdstrike
bit 9  -> crawler_supplementary_v2.groupib
bit 10 -> crawler_supplementary_v2.ofac
bit 11 -> crawler_supplementary_v2.fbi
```

全选值：

```text
4095 = (1 << 12) - 1
```

示例：

```text
1033 = 0b010000001001
```

表示：

```text
crawler_v1：qianxin、freebuf
crawler_supplementary：不调用
crawler_supplementary_v2：ofac
```

调度器拆分为：

```text
crawler_v1 局部 mask = sources 的低 4 位
crawler_supplementary 局部 mask = 右移 4 位后的低 4 位
crawler_supplementary_v2 局部 mask = 再右移 4 位后的低 4 位
```

每个子爬虫内部维护固定来源顺序，局部 mask 的最低位对应第一个来源。局部 mask 为零时，主调度器不调用对应子爬虫。

参数校验：

```text
sources = 0：拒绝
sources < 0：拒绝
sources 非十进制整数：拒绝
sources > 4095：拒绝
```

## 5. crawl_run_id

frontend 不生成运行 ID。backend 在创建任务时生成唯一的 `crawl_run_id`，并在后续所有 HTTP 请求中复用。

示例：

```text
crawl_20260716_001
```

`crawl_run_id` 用于：

1. 区分不同采集任务。
2. frontend 刷新后继续查询任务状态。
3. backend 与 crawler 关联同一次任务。
4. 记录采集统计、错误和时间。
5. 在 Document metadata 中追踪采集来源。

`crawl_run_id` 不是文档身份，不随 `doc_id` 重写而变化。

## 6. HTTP 接口

### 6.1 frontend -> backend 创建任务

```text
POST /api/v1/crawl/runs
```

请求：

```json
{
  "keyword": "APT28",
  "limit": 2,
  "sources": 1033,
  "filter": false
}
```

backend 执行：

```text
1. 校验 keyword、limit、sources、filter。
2. 检查是否已有 pending/running 采集任务。
3. 查询 SQLite 中该 keyword 对应组织的最大正式编号。
4. 计算 start_number = max_number + 1。
5. 生成 crawl_run_id。
6. 创建 pending 任务。
7. 异步调用 crawler。
8. 返回 crawl_run_id。
```

成功响应：

```json
{
  "success": true,
  "data": {
    "crawl_run_id": "crawl_20260716_001",
    "status": "pending"
  }
}
```

已有任务运行时返回 HTTP 409，避免同一时间启动多个采集任务。

### 6.2 frontend -> backend 查询任务

```text
GET /api/v1/crawl/runs/{crawl_run_id}
```

运行中响应：

```json
{
  "success": true,
  "data": {
    "crawl_run_id": "crawl_20260716_001",
    "keyword": "APT28",
    "status": "running",
    "items_found": 0,
    "items_promoted": 0,
    "items_imported": 0,
    "items_skipped": 0,
    "items_failed": 0,
    "document_ids": []
  }
}
```

完成响应：

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
  }
}
```

### 6.3 backend -> crawler 创建任务

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

`start_number` 必须由 backend 传入。crawler 只负责将它继续传给 `run_all_crawlers.py` 和 promote。若独立运行 `run_all_crawlers.py` 或 promote，`start-number` 默认值为 `1`。

crawler 接收任务后返回：

```json
{
  "crawl_run_id": "crawl_20260716_001",
  "status": "accepted"
}
```

### 6.4 crawler -> backend 导入 Document

```text
POST http://backend:8000/api/v1/documents/import
```

crawler 逐个发送 promote 生成的完整 Document JSON。backend 继续使用当前 Document 契约校验请求。

导入成功：

```json
{
  "success": true,
  "data": {
    "doc_id": "apt28_108",
    "status": "imported",
    "chunks": 8
  }
}
```

重复文档：

```json
{
  "success": true,
  "data": {
    "doc_id": "apt28_032",
    "status": "skipped",
    "message": "文档已存在"
  }
}
```

## 7. 编号与 promote

### 7.1 临时文档

三个爬虫输出到 crawler 容器内部的：

```text
data/cleaned/<keyword>/*.json
```

临时 `doc_id` 不代表正式身份，可以使用：

```text
apt28_001
apt28_002
```

过滤输出到：

```text
data/cleaned_filtered/<keyword>/*.json
```

### 7.2 promote 输入和参数

promote 不接收 `--target-group`，扫描整个输入目录：

```bash
python scripts/promote_cleaned_documents.py \
  --input data/cleaned \
  --output data/documents \
  --start-number 108
```

过滤模式使用：

```bash
python scripts/promote_cleaned_documents.py \
  --input data/cleaned_filtered \
  --output data/documents \
  --start-number 108
```

`--start-number` 默认为 `1`。

### 7.3 promote 的职责

promote 只负责：

1. 读取 cleaned 或 cleaned_filtered 中的标准 Document。
2. 按 `start_number` 生成正式编号。
3. 修改 JSON 内部 `doc_id`。
4. 修改文件名，使文件名与 `doc_id` 一致。
5. 修改 metadata 中明确的 ID 或路径字段。
6. 写入 crawler 容器内部的 `documents/`。

promote 不负责：

```text
backend SQLite 查重
source_url 查重
content_hash 查重
读取 backend 文件
写入 backend SQLite
```

### 7.4 metadata 字段替换

promote 只更新明确的 ID/路径字段，不扫描普通描述文本。

需要同步更新的字段包括：

```text
doc_id
document_id
legacy_doc_id
source_path
cleaned_path
document_path
```

示例：

输入：

```json
{
  "doc_id": "apt28_001",
  "metadata": {
    "legacy_doc_id": "apt28_001",
    "source_path": "data/cleaned/apt28/apt28_001.json",
    "note": "来自 apt28_001 的采集"
  }
}
```

输出：

```json
{
  "doc_id": "apt28_108",
  "metadata": {
    "legacy_doc_id": "apt28_108",
    "source_path": "data/documents/apt28/apt28_108.json",
    "note": "来自 apt28_001 的采集"
  }
}
```

以下字段不修改：

```text
content_hash
clean_text
crawl_run_id
普通 note/description 字符串
URL 查询参数
```

## 8. 查重边界

### crawler/promote

crawler 和 promote 不进行正式查重。它们可以生成与历史文档相同的 `source_url` 或 `content_hash`，只负责输出和提交。

### backend

backend 的 `/api/v1/documents/import` 是唯一正式查重边界。当前实际查重条件为：

```sql
WHERE doc_id = ? OR content_hash = ?
```

因此：

```text
doc_id 重复 -> skipped
content_hash 重复 -> skipped
```

当前不新增 `source_url` 查重规则。若以后需要按 URL 管理版本，应另行设计文档版本契约，不混入本次三容器拆分。

## 9. crawler 任务内部流程

```text
1. 创建 crawler_run_id 对应的临时工作区。
2. 执行 run_all_crawlers.py。
3. run_all_crawlers.py 将 start-number 继续传给 promote。
4. 未过滤时 promote 读取 cleaned。
5. 过滤时先生成 cleaned_filtered，再由 promote 读取 cleaned_filtered。
6. promote 修改 doc_id、文件名和明确 metadata 字段。
7. crawler 读取 documents 中的 JSON。
8. crawler 逐个 HTTP 调用 backend /api/v1/documents/import。
9. crawler 汇总 found/promoted/imported/skipped/failed 统计。
10. crawler 在 finally 中清空 cleaned、cleaned_filtered、documents。
11. crawler 返回 crawl_run_id 和统计结果。
```

清理必须覆盖：

```text
采集失败
过滤失败
promote 失败
backend 导入失败
任务正常完成
```

## 10. 任务状态与错误处理

状态：

```text
pending
running
succeeded
failed
```

统计字段：

```text
items_found：网页候选数量
items_promoted：promote 生成正式 JSON 的数量
items_imported：backend 返回 imported 的数量
items_skipped：backend 返回 skipped 的数量
items_failed：采集、promote 或 HTTP 导入失败数量
```

错误规则：

1. frontend 参数非法：backend 返回 HTTP 400。
2. 已有 pending/running 任务：backend 返回 HTTP 409。
3. crawler 不可用：backend 将任务标记为 failed。
4. 单篇 Document 导入失败：crawler 记录该篇失败并继续处理其他文档；如果全部导入失败，任务最终为 failed。
5. crawler 进程或 HTTP 服务失败：backend 将任务标记为 failed。
6. 任意结果都必须执行临时工作区清理。

## 11. Docker 网络

Compose 中运行：

```text
frontend
backend
crawler
```

内部地址：

```text
backend -> http://crawler:8100
crawler -> http://backend:8000
```

crawler 不需要向宿主机暴露端口，只在 Compose 网络中使用 `expose`。frontend 也不应把 crawler 地址暴露给浏览器。

容器不共享：

```text
data volume
SQLite 文件
cleaned 文件
documents 文件
```

crawler 的临时目录只在 crawler 容器内部存在，任务结束后清理。

## 12. 验收标准

### Frontend

1. 可以在 APT28、Kimsuky、Lazarus 中单选一个关键词。
2. 可以输入正整数 limit。
3. 可以通过复选框选择数据源并生成整数 sources。
4. 可以提交任务并获得 crawl_run_id。
5. 可以轮询并展示 pending/running/succeeded/failed。
6. 浏览器无法直接访问 crawler。

### Backend

1. 能校验 frontend 请求。
2. 能生成 crawl_run_id。
3. 能查询并传递 start_number。
4. 能调用 crawler HTTP 接口。
5. 能接收 crawler 的 Document 导入请求。
6. 能按 doc_id/content_hash 查重。
7. 能写 SQLite 并自动生成 chunks。

### Crawler

1. 能接收 backend 的 HTTP 任务。
2. 能将 sources 整数传给 `run_all_crawlers.py`。
3. 能将 start_number 传给 `run_all_crawlers.py` 和 promote。
4. promote 默认 start-number 为 1。
5. promote 修改 JSON 内部 doc_id、文件名和明确 metadata ID/路径字段。
6. crawler 能逐篇调用 backend `/api/v1/documents/import`。
7. 任务结束后清理三个临时目录。
8. 不直接读写 backend 文件或 SQLite。

### 端到端

```text
用户选择 APT28
输入 limit=2
选择来源并生成 sources=1033
frontend -> backend
backend -> crawler
crawler 采集并 promote
crawler -> backend 导入
backend 写 SQLite 和 chunks
frontend 轮询得到最终统计
```
