# 爬虫采集 LLM 配置门禁设计

## 1. 目标

采集情报任务完成后会固定复用 backend 的 `live` Pipeline，因此没有有效 LLM 配置时不允许启动采集任务。

本次门禁只做配置存在性校验，不发起真实 LLM 连通性探测。

## 2. 有效配置

以下三个环境变量去除首尾空白后都必须非空：

```text
LLM_MODEL
LLM_BASE_URL
LLM_API_KEY
```

任意一项缺失或为空，都视为无有效 LLM 配置。

## 3. Backend 门禁

`GET /api/v1/health` 返回：

```json
{
  "llm": "configured"
}
```

或：

```json
{
  "llm": "not_configured"
}
```

`POST /api/v1/crawl/runs` 在创建任务前执行同一配置检查。无有效配置时：

- 不创建 backend 内存任务；
- 不调用 crawler；
- 返回 HTTP `503`；
- 错误码为 `ERR_LLM_NOT_CONFIGURED`；
- 错误消息为 `无有效 LLM 配置`。

## 4. Frontend 行为

“采集情报”按钮始终显示，不因配置缺失而隐藏。

frontend 启动或目标组织页面加载时读取 backend health：

- `llm=configured`：按钮可用；
- `llm=not_configured`：按钮保持显示但 `disabled=true`；
- 按钮旁或弹窗入口显示“需要有效 LLM 配置”；
- 不向 crawler 发起请求。

即使 frontend health 请求失败，backend 仍是最终门禁；frontend 不得仅依赖本地环境变量判断配置有效性。

## 5. 复用边界

门禁不复制 LLM 配置读取逻辑。backend 使用统一的配置检查函数，health 接口和 crawl API 共用该函数；crawler 仍只负责执行任务和调用 backend，不能绕过 backend 门禁。

采集任务的完整终点保持为：

```text
promote Document
-> /documents/import
-> /pipeline/run(extraction_mode=live)
-> /pipeline/status/{job_id}
-> LLM 抽取、校验、归一化和建图
```

## 6. 测试

- 三项配置均非空时 health 返回 `configured`；
- 任意一项为空时 health 返回 `not_configured`；
- 无配置时 crawl API 返回 HTTP 503、指定错误码且 crawler 不被调用；
- 有配置时 crawl API 保持现有任务创建行为；
- frontend 无配置时按钮仍存在且 disabled；
- frontend 有配置时按钮可用；
- 现有 backend、crawler 和 frontend 回归测试继续通过。
