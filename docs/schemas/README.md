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
  be 导出 data/graph/graph.json 快照时使用；/api/v1/graph 响应以 docs/api-contract.md 为准

docs/schemas/relationship-matrix.md
  arch / be 校验关系类型是否合法时使用
```

配套样例放在：

```text
data/examples/document.apt28.securelist.example.json
data/examples/reference.apt28.mitre.example.json
data/examples/extraction_result.apt28.securelist.example.json
data/examples/graph.apt28.securelist.example.json
data/examples/golden.apt28.example.json
```

真实 P0 文档放在：

```text
data/documents/<target_group>/*.json
```

`data/examples/` 是契约样例，不承载批量数据交付；`data/documents/` 才是后端导入真实清洗文档的默认目录。

当前 APT28 样例分成两类来源：

1. Securelist 的 `Masha and these Bears` 是真实文章样例，给 data 组清洗正文、给 llm 组抽取候选结果、给 be 组归一化和导出图谱使用。
2. MITRE ATT&CK 的 APT28 页面是知识库参考样例，给 arch / qa / be 做标准名、别名、MITRE 编号和 golden 对齐使用。

Securelist 字段口径如下：

1. `source_type` 使用 `vendor_report`，表示安全厂商发布的威胁情报文章。
2. `target_group` 使用标准名 `APT28`，`Sofacy`、`Fancy Bear`、`Tsar Team` 进入实体 `aliases`。
3. 仓库样例的 `clean_text` 只保留人工清洗后的短文本，不放完整网页原文；`content_hash` 固定为 `sha256(clean_text 按 UTF-8 编码后的字节)`，可追溯性依赖 `source_url`、`published_at`、`retrieved_at`、`doc_id`、`chunk_id` 和 `evidence`。
4. MITRE 页面使用 `source_type = knowledge_base`，不要和厂商报告混成同一个 `document.json`。

## 当前硬性规则

1. `document.json` 必须包含来源、时间、语言、清洗正文 `clean_text`、目标组织和 `content_hash`；真实文档默认放在 `data/documents/<target_group>/`。
2. `extraction_result.json` 只表示 LLM 候选结果，不能包含最终 `entity_id` 或 `relation_id`。
3. `graph.json` 只能由 SQLite canonical graph 导出，不能直接由 LLM 生成。
4. 所有实体和关系都必须能追溯到 `evidence_ids`。
5. 关系类型必须先通过 `relationship-matrix.md` 的最小合法性检查。
6. `RELATED_TO` 只能作为兜底关系，不能作为常规抽取结果滥用。

## 今日交付口径

data 组先按 `document.apt28.securelist.example.json` 改出第一份 APT28 真实文档。

llm 组先按 `extraction_result.apt28.securelist.example.json` 手写或生成候选结果。第一版只要求 JSON 合法、字段完整，不要求准确率完美。

be 组按 `graph.apt28.securelist.example.json` 的格式导出 `data/graph/graph.json`，并按 `docs/api-contract.md` 返回 `/api/v1/graph` 的轻量图谱视图，同时补齐 `/api/v1/graph/path` 的 SQLite BFS 兜底。

如果后续需要对 `/api/v1/graph` 做机器校验，应新增独立的 `graph-view.schema.json`，不要复用完整 GraphSnapshot 的 `graph.schema.json`。

qa 组按 `golden.apt28.example.json` 维护第一版人工标准答案，用来记录 LLM 错误样例。
