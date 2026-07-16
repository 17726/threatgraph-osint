# 爬虫审查问题修复设计

## 目标

修复 `feat/crawler` 审查发现的采集链路缺陷，保持现有三容器架构、SQLite 事实源和 live Pipeline 复用方式不变。

## 修复范围

### Crawler 状态与统计

- crawler 任务异常时返回 `status=failed`，并将 `progress.phase` 设置为 `failed`。
- 创建任务时根据来源 bitmask 初始化所有选中来源的零值 `source_results`。
- `items_found` 在每个 promoted Document 进入导入尝试时递增，即使后续导入失败也保留发现统计。
- 保持单篇失败继续处理、至少一篇 live Pipeline 成功才整体成功的现有语义。

### 过滤与编号

- 过滤脚本以非零退出码报告处理错误，使统一调度器跳过 promote。
- 过滤输出重编号时同步更新明确的 metadata ID 和路径字段。
- 不修改普通描述、note、正文、content hash 和采集运行 ID。

### 前端流水线

- 文档导入返回 `skipped` 时，仍使用 backend 返回的既有 `doc_id` 提交显式 Pipeline。
- 保留重复文档可重新运行流水线的行为，并补充回归测试。

## 测试策略

- 先为异常进度、零结果来源、导入失败发现统计、过滤错误退出码、过滤重编号 metadata 和 skipped 后继续 Pipeline 编写失败回归测试。
- 逐项运行相关测试确认先失败，再实现最小修复。
- 最终运行 backend 和 crawler 完整测试、frontend 完整测试、frontend build 以及 `git diff --check`。

## 非目标

- 不重构现有爬虫脚本，不改变来源 bitmask，不新增任务持久化。
- 不修改未跟踪的 `temp/` 或其他与审查问题无关的文件。
