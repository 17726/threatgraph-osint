# 指导文件目录

本目录放面向具体小组的操作指南。这里的文档不替代正式契约，正式字段仍以
[`docs/data-contract.md`](../data-contract.md)、[`docs/api-contract.md`](../api-contract.md)
和 [`docs/schemas/`](../schemas/) 为准。

## 当前指南

| 文档                                                     | 适用对象                  | 说明                                                |
| -------------------------------------------------------- | ------------------------- | --------------------------------------------------- |
| [`s1-contract-onboarding.md`](s1-contract-onboarding.md) | data / llm / be / fe / qa | S1 阶段三份 JSON 契约的上手流程、字段填写和交付检查 |
| [`llm-extraction-and-evaluation.md`](llm-extraction-and-evaluation.md) | llm / qa | DeepSeek V4 真实抽取、候选校验、golden 评测和 SQLite 导入 |

## 使用方式

1. 新成员先读根目录 [`README.md`](../../README.md) 和 [`TODO.md`](../../TODO.md)。
2. 按自己的组别阅读本目录里的上手指南。
3. 真正提交样本、抽取结果或图谱快照前，再用 `docs/schemas/` 下的 schema 和
   `data/examples/` 下的样例核对字段。
