# Schema 与样例说明

> 适用阶段：Step 1 真实样本文档闭环  
> 当前版本：`schema_version = "1.0"`  
> 冻结原则：字段变更必须先同步 `arch / be / fe / llm`，不能由某一组单独改。

## 文件用途

```text
docs/schemas/document.schema.json
  data 组提交真实样本文档时使用

docs/schemas/extraction-result.schema.json
  llm 组提交候选抽取结果时使用

docs/schemas/graph.schema.json
  be 导出 graph.json、fe 接入图谱时使用

docs/schemas/relationship-matrix.md
  arch / be 校验关系类型是否合法时使用
```

配套样例放在：

```text
data/examples/document.apt28.example.json
data/examples/extraction_result.apt28.example.json
data/examples/graph.apt28.example.json
data/examples/golden.apt28.example.json
```

## 当前硬性规则

1. `document.json` 必须包含来源、时间、语言、正文、目标组织和 `content_hash`。
2. `extraction_result.json` 只表示 LLM 候选结果，不能包含最终 `entity_id` 或 `relation_id`。
3. `graph.json` 只能由 SQLite canonical graph 导出，不能直接由 LLM 生成。
4. 所有实体和关系都必须能追溯到 `evidence_ids`。
5. 关系类型必须先通过 `relationship-matrix.md` 的最小合法性检查。
6. `RELATED_TO` 只能作为兜底关系，不能作为常规抽取结果滥用。

## 今日交付口径

data 组先按 `document.apt28.example.json` 改出第一份 APT28 真实文档。

llm 组先按 `extraction_result.apt28.example.json` 手写或生成候选结果。第一版只要求 JSON 合法、字段完整，不要求准确率完美。

be 组按 `graph.apt28.example.json` 的格式返回 `/api/v1/graph`，并补齐 `/api/v1/graph/path` 的 SQLite BFS 兜底。

qa 组按 `golden.apt28.example.json` 维护第一版人工标准答案，用来记录 LLM 错误样例。
