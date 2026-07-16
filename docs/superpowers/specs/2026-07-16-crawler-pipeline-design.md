# 爬虫统一流水线设计

## 目标

统一三个爬虫入口和标准文档提升流程，使用户可以通过一个调度器完成采集、可选相关性过滤和文档提升：

```text
crawler_v1.py
crawler_supplementary.py
crawler_supplementary_v2.py
        -> data/cleaned/<target_group>/
        -> 可选 filter_by_relevance.py
        -> data/cleaned_filtered/<target_group>/
        -> promote_cleaned_documents.py
        -> data/documents/<target_group>/
```

`convert_raw_documents.py` 和 `convert_suqi625_dataset.py` 继续作为历史数据迁移工具，不参与新的统一运行入口。

## 统一命令行接口

`scripts/run_all_crawlers.py` 只暴露以下参数：

```text
--keyword   必填，目标组织或搜索关键词
--limit     每个来源最多采集条数，必须为正整数
--filter    可选开关，启用 LLM 相关性过滤和末尾清洗
--sources   必填，逗号分隔的来源名或 all
```

示例：

```bash
python scripts/run_all_crawlers.py --keyword APT28 --limit 2 --sources all
python scripts/run_all_crawlers.py --keyword Lazarus --limit 5 --sources chainalysis,ofac --filter
```

来源名统一转为小写，未知来源直接报错，不静默忽略。

## 来源归属

调度器维护唯一来源归属表：

```text
crawler_v1:
  qianxin, thehackernews, unit42, freebuf

crawler_supplementary:
  chainalysis, trmlabs, microsoft, securelist

crawler_supplementary_v2:
  crowdstrike, groupib, ofac, fbi
```

调度器根据 `--sources` 将来源分组传给对应脚本。某个脚本没有任何匹配来源时不调用。每个脚本一次调用可接收逗号分隔的多个来源；`all` 只在该脚本获得其完整来源集合时使用。

三个爬虫均输出到：

```text
data/cleaned/<target_group>/
```

其中 `crawler_v1.py` 增加 `--source`，并将原有固定调用改为来源注册表选择；其他两个补充脚本将 `--source` 从单个来源扩展为逗号分隔列表。

## 过滤流程

当未提供 `--filter` 时：

```text
data/cleaned -> promote_cleaned_documents.py -> data/documents
```

当提供 `--filter` 时：

```text
data/cleaned -> filter_by_relevance.py -> data/cleaned_filtered
data/cleaned_filtered -> promote_cleaned_documents.py -> data/documents
```

过滤器按当前 `--keyword` 推导目标组织目录，并继续从 `LLM_API_KEY` 或 `DEEPSEEK_API_KEY` 读取密钥。中间目录文档尚未进入正式链路，过滤器可以重新编号临时文件；正式 `doc_id` 由 promote 阶段重新分配。

## 文档提升

新增 `scripts/promote_cleaned_documents.py`，输入目录可配置，默认：

```text
--input  data/cleaned
--output data/documents
```

提升规则：

1. 读取输入目录下目标组织 JSON 文档。
2. 校验 Document 必填字段和 `schema_version`。
3. 校验 `clean_text` 非空、`content_hash` 为 SHA-256 格式且与正文一致。
4. 按 `source_url` 和 `content_hash` 与正式输出目录已有文档去重。
5. 按目标组织扫描正式目录中的最大序号。
6. 新文档从最大序号加一开始分配正式 `doc_id`。
7. 同步更新 JSON 内的 `doc_id`，文件名使用相同 ID。
8. 不删除、不修改输入中间文件。
9. 输出处理、跳过和错误统计。

## 错误处理

- `--sources` 为空、来源未知、`--limit` 非正整数：调度器启动前失败。
- 单个爬虫子进程返回非零：停止后续爬虫、过滤和 promote，并返回相同错误码。
- 没有匹配来源的爬虫：跳过，不视为错误。
- 过滤器未配置 API Key：过滤模式失败，不进入 promote。
- promote 遇到非法文档：记录错误并以非零状态结束，避免把非法文档写入正式目录。

## 测试范围

新增或调整测试覆盖：

- `crawler_v1.py` 的来源选择、`all` 和 `data/cleaned` 输出目录。
- 两个 supplementary 脚本的逗号分隔来源选择。
- 调度器来源归属分组、无匹配脚本跳过和四个 CLI 参数。
- 过滤开关对应的输入目录选择。
- promote 的最大序号递增、正式 `doc_id` 重写、URL/内容哈希去重和契约校验。

不测试真实外部网站请求；站点解析逻辑继续由已有脚本负责。
