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
data/examples/document.apt28.thn.beardshell.example.json
data/examples/reference.apt28.mitre.example.json
data/examples/extraction_result.apt28.thn.beardshell.example.json
data/examples/graph.apt28.thn.beardshell.example.json
data/examples/golden.apt28.thn.beardshell.example.json
```

真实 P0 文档放在：

```text
data/documents/<target_group>/*.json
```

`data/examples/` 是契约样例，不承载批量数据交付；`data/documents/` 才是后端导入真实清洗文档的默认目录。

当前 APT28 样例分成两类来源：

1. The Hacker News 的 `APT28 Uses Signal Chat to Deploy BEARDSHELL Malware and COVENANT in Ukraine` 选自 `data/documents/apt28/apt28_049.json`，给 data 组、llm 组、be 组和 qa 组作为完整证据链样例。
2. MITRE ATT&CK 的 APT28 页面是知识库参考样例，给 arch / qa / be 做标准名、别名、MITRE 编号和 golden 对齐使用。

The Hacker News 字段口径如下：

1. `source_type` 使用 `news`，表示公开安全新闻来源。
2. `target_group` 使用标准名 `APT28`，`UAC-0001` 进入实体 `aliases`。
3. 仓库样例的 `clean_text` 来自已入库 cleaned document；`content_hash` 固定为 `sha256(clean_text 按 UTF-8 编码后的字节)`，可追溯性依赖 `source_url`、`published_at`、`retrieved_at`、`doc_id`、`chunk_id` 和 `evidence`。
4. MITRE 页面使用 `source_type = knowledge_base`，不要和厂商报告混成同一个 `document.json`。

## 当前硬性规则

1. `document.json` 必须包含来源、时间、语言、清洗正文 `clean_text`、目标组织和 `content_hash`；真实文档默认放在 `data/documents/<target_group>/`。
2. `extraction_result.json` 只表示 LLM 候选结果，不能包含最终 `entity_id` 或 `relation_id`。
3. `graph.json` 只能由 SQLite canonical graph 导出，不能直接由 LLM 生成。
4. 所有实体和关系都必须能追溯到 `evidence_ids`。
5. 关系类型必须先通过 `relationship-matrix.md` 的最小合法性检查。
6. `RELATED_TO` 只能作为兜底关系，不能作为常规抽取结果滥用。

## 今日交付口径

data 组先按 `document.apt28.thn.beardshell.example.json` 改出第一份 APT28 真实文档。

llm 组先按 `extraction_result.apt28.thn.beardshell.example.json` 手写或生成候选结果。第一版必须保证 JSON 合法、字段完整、证据文本能回到 `clean_text`。

be 组按 `graph.apt28.thn.beardshell.example.json` 的格式导出 `data/graph/graph.json`，并按 `docs/api-contract.md` 返回 `/api/v1/graph` 的轻量图谱视图，同时补齐 `/api/v1/graph/path` 的 SQLite BFS 兜底。

如果后续需要对 `/api/v1/graph` 做机器校验，应新增独立的 `graph-view.schema.json`，不要复用完整 GraphSnapshot 的 `graph.schema.json`。

qa 组按 `golden.apt28.thn.beardshell.example.json` 维护第一版人工标准答案，用来记录 LLM 错误样例。
