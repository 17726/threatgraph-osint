# LLM 真实抽取与评测指南

本指南适用于 LLM 抽取与分析组和 QA 组。字段与关系约束仍以
`docs/prompts/extract-v1.md`、`docs/schemas/extraction-result.schema.json` 和
`docs/schemas/relationship-matrix.md` 为准。

## 1. 数据链路

```text
document.json
  -> DeepSeek V4 候选抽取
  -> extraction_result.json + candidate-audit.json
  -> schema / 关系矩阵 / 原文证据校验
  -> golden Precision / Recall / F1 评测
  -> 可选导入 SQLite 候选层和 canonical graph
```

LLM 不生成正式 `entity_id`、`relation_id`，也不直接写 `graph.json` 或 Neo4j。
模型返回后，runner 会逐项拒绝空证据、证据无法回到原文、非法类型组合或端点未声明的
候选；剩余候选才进入 `extraction_result.json`。所有被过滤、合并或去重的原始候选会写入
同一 run 的 `candidate-audit.json`。对照 golden 评测时，审计文件中的候选全部计为 false
positive，避免过滤步骤虚高模型指标；证据充分但事实判断错误的正式候选同样计为 false
positive。

API 请求采用紧凑草稿，模型只生成实体/关系语义字段。`run_id`、`chunk_id`、字符位置、候选
状态和校验错误由 runner 确定性补全，最终落盘文件仍必须通过完整 extraction-result schema。

## 2. 安全配置

复制 `.env.example` 为 `.env`，只填写本地密钥：

```bash
LLM_API_KEY=<your-key>
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_MAX_OUTPUT_TOKENS=32768
LLM_RELATION_REVIEW_PASSES=0
```

不要使用 `--api-key` 参数，也不要把密钥写进脚本、测试、日志或 PR 描述。密钥一旦出现在
聊天、截图或提交历史中，应在服务商控制台轮换。

`LLM_TRUST_ENV=false` 默认忽略本机 `HTTP_PROXY`、`HTTPS_PROXY` 和 `ALL_PROXY`，避免错误的
SOCKS 配置阻断请求。必须使用代理时改为 `true`，并确保运行环境安装相应代理依赖。

## 3. API 预检

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --preflight-only --json
```

预检只发出一个最小 JSON 请求，不保存密钥和模型内容。通过时返回实际响应模型和 token
用量；401、余额不足、模型不存在和网络错误都会以非零退出码失败。

长文档输出达到 `LLM_MAX_OUTPUT_TOKENS` 时会被明确判定为截断；纠错重试会在 65536
上限内翻倍输出预算，不会把残缺 JSON 写入候选层。提高该值时应同时记录运行成本和文档规模。

关系复核是可选实验能力：设为 `LLM_RELATION_REVIEW_PASSES=1` 后，只能在首轮已通过证据
校验的实体之间补关系，不能新增实体。当前默认关闭，因为它会增加调用成本，且现有小样本上
尚未证明稳定提升 F1；复核失败时保留首轮结果并在运行摘要中给出 warning。

## 4. 单篇抽取与评测

APT28：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --document data/documents/apt28/apt28_080.json \
  --golden data/evaluation/golden.en.apt28_080.json \
  --json
```

Kimsuky 和 Lazarus 分别替换为：

```text
data/documents/kimsuky/kimsuky_060.json
data/evaluation/golden.en.kimsuky_060.json

data/documents/lazarus/lazarus_091.json
data/evaluation/golden.en.lazarus_091.json
```

截至 2026-07-13，最新 `main` 的 Kimsuky golden 已通过门禁；Lazarus golden 仍缺少 chunk
`char_end`，runner 会在 API 调用前拒绝该输入，待 QA 补齐后再执行。

命令会写出两类运行工件：

```text
data/extracted/extract_<doc_id>_<prompt>_<timestamp>.json
data/extracted/extract_<doc_id>_<prompt>_<timestamp>.candidate-audit.json
data/evaluation/evaluation_result.<doc_id>.<model>.<prompt>.json
```

## 5. 独立评测

已有候选结果时，不再调用 API：

```bash
python scripts/evaluate_extraction_against_golden.py \
  --extraction-result data/extracted/<result>.json \
  --candidate-audit data/extracted/<run>.candidate-audit.json \
  --golden data/evaluation/golden.en.apt28_080.json \
  --document data/documents/apt28/apt28_080.json \
  --output data/evaluation/evaluation_result.apt28_080.json
```

实体按“同一 chunk、类型相同、标准化名称或别名相交”做最大基数、再最大匹配分数的一对一
匹配。关系按“同一 chunk、两端实体已匹配、关系类型完全相同”一对一匹配。证据必须能回到
`document.clean_text` 且落在 golden 所属 chunk 的字符范围内，但证据文本是否与 golden 使用
完全相同的句子不参与 F1，以免把正确事实因截取范围不同判错。

评测器显式拒绝重复 `chunk_id`，并在多文档 golden 中只选择当前
`extraction_result.doc_id` 的 chunks。独立评测不提供 `--candidate-audit` 时，输出只代表已通过
校验的候选质量，不得表述为原始模型端到端指标。

评测前会同时检查 golden 的 schema、关系方向/类型配对、端点实体和原文证据。golden
不满足当前关系矩阵时直接拒绝评测，不输出看似精确但标准答案本身无效的指标。

可使用 `--min-entity-f1` 和 `--min-relation-f1` 设置 CI 门槛；低于门槛时退出码为 2。

## 6. 导入正式图谱

只有候选结果通过校验后，才显式导入：

```bash
docker compose run --rm backend python scripts/run_llm_extraction.py \
  --document data/documents/apt28/apt28_080.json \
  --golden data/evaluation/golden.en.apt28_080.json \
  --import --export-graph --json
```

当前真实 runner 沿用 QA golden 的单文档单 chunk 约定。后端 `documents/import` 和统一切块
接口落地后，runner 应消费后端生成的 chunk，不在 LLM 组自行增加第二套切块算法。
