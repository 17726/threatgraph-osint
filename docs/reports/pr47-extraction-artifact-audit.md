# PR #47 抽取工件审核记录

## 1. 审核范围与结论

审核来源为 PR #47 原始提交 `e9d3f5b6` 的 `data/pipeline_extracted/*.json`，共 11 份。
审核使用当前主线的 Document、Extraction Schema、关系矩阵、证据原文/偏移校验和正式工件命名规则，
没有使用 #47 自带的宽松适配逻辑。

结论：

- 11 份 Extraction 均能与当前 `data/documents/<target_group>/<doc_id>.json` 对应，Document
  的 `content_hash` 一致。
- 11 份均通过 `validate_import_payload`，没有 Schema、实体/关系类型、关系端点、证据原文或偏移错误。
- 11 份的 `run_id` 均与 `doc_id`、模型、Prompt、Schema 和 `generated_at` 一致；改用
  `<run_id>.json` 后通过严格文件名校验。
- 11 份均未在 #47 中保留同 `run_id` 的 Candidate Audit。因此不能还原被过滤候选，不能用于
  raw/validated 口径评测，也不把它们声明为新的质量 Baseline。
- 其中 9 份非重复工件迁入 `data/extracted/` 并登记到审核清单，可用于 reviewed 导入和图谱重建；
  `kimsuky_001` 与 `lazarus_001` 已由 #58 锁定为审计溯源更完整的工件，本次不迁移重复版本。

## 2. 逐项结果

| doc_id | 实体 | 关系 | 当前契约 | Candidate Audit | 处理 |
| --- | ---: | ---: | --- | --- | --- |
| `apt28_002` | 22 | 10 | 通过 | 缺失 | 迁移，受限导入工件 |
| `apt28_003` | 8 | 2 | 通过 | 缺失 | 迁移，受限导入工件 |
| `apt28_004` | 23 | 5 | 通过 | 缺失 | 迁移，受限导入工件 |
| `apt28_005` | 13 | 5 | 通过 | 缺失 | 迁移，受限导入工件 |
| `kimsuky_001` | 15 | 1 | 通过 | 缺失 | 不迁移；#58 已选择带审计版本 |
| `kimsuky_002` | 7 | 2 | 通过 | 缺失 | 迁移，受限导入工件 |
| `kimsuky_003` | 28 | 2 | 通过 | 缺失 | 迁移，受限导入工件 |
| `lazarus_001` | 82 | 47 | 通过 | 缺失 | 不迁移；#58 已选择带审计版本 |
| `lazarus_003` | 17 | 13 | 通过 | 缺失 | 迁移，受限导入工件 |
| `lazarus_004` | 27 | 14 | 通过 | 缺失 | 迁移，受限导入工件 |
| `lazarus_009` | 12 | 4 | 通过 | 缺失 | 迁移，受限导入工件 |

## 3. 使用边界

1. 迁移文件仍是候选层输入，不是 canonical 事实源；导入后由 SQLite 保存正式实体、关系和证据。
2. 这些文件不会替换 `config/course-demo.json` 中由 #58 明确锁定的三组织主演示样本。
3. 缺失 Candidate Audit 的事实必须保留，不能补写空审计文件冒充“没有被过滤候选”。
4. 后续若要将某次运行升级为评测 Baseline，必须重新取得同 `run_id` 的真实 Candidate Audit，
   或重新执行 live 抽取并完成独立语义评审。
