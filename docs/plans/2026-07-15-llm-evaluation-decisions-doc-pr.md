# LLM 标注、实验与评测决策文档 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 2026-07-15 已确认的 Golden 全文标注原则、当前 Experiment 现状、版本职责和待二审评测指标整理成可单独评审的文档 PR。

**Architecture:** 本 PR 只更新文档，不修改 JSON Schema、评测器、运行目录或数据文件。文档必须区分“仓库当前实现”“负责人已确认的下一步规则”“仍待评审的提案”，避免把尚未落地的 Experiment Manifest、Golden v2 和多作用域指标描述成现有能力。

**Tech Stack:** Markdown、Git、GitHub Pull Request、PowerShell 文档检查。

---

## 0. 执行边界

本计划直接在当前工作区的 `docs/llm/evaluation-decisions` 分支执行，不创建 worktree；项目负责人此前已明确要求直接使用现有工作区。

本 PR 必须完成：

1. 解释 Dataset、Run、Evaluation Run、Experiment、Baseline、Iteration 的关系，停止使用未定义的 `Track`、`Treaty` 或“演变组”。
2. 记录当前 6 篇 Golden 的真实结构：每篇一份 Golden、一个覆盖全文的 v1 单 chunk 外壳。
3. 冻结“人工按整篇 Document 标全，算法切块不得反向改变 Golden”的原则。
4. 区分“全文已审阅但按标注政策排除”和“存在未审阅范围”；后者不能作为正式 Baseline。
5. 说明当前仓库没有独立 Experiment 环境，也没有清理旧 `data/extracted/`、`data/evaluation/`。
6. 单独编写评测指标二审稿，给出 TP/FP/FN、Raw、Validated、Rejected、Duplicate、Parse Failure、Empty 和切块消融的计算例子。
7. 说明版本号人工递增、Run ID 自动生成；Git Commit 不触发版本自增。
8. 将可复现性暂时收窄为记录要求，不设置强一致性或性能门槛。
9. 列出对前端、Neo4j、报告、查询和 LLM 同步调研的影响范围。

本 PR 明确不完成：

1. 不修改 Golden Schema 或迁移 6 篇 Golden。
2. 不修改现有评测算法，也不重算历史指标。
3. 不新增 `data/runs/`、`data/experiments/` 或 Manifest。
4. 不清理、移动或重命名历史 Extraction/Evaluation 文件。
5. 不实现 Provider Raw Response、Run Bundle、自动版本递增或不可变写入。
6. 不修改前端、SQLite、Neo4j、报告或查询代码。

## Task 1：记录事实核验结果

**Files:**

- Inspect: `data/golden/*.json`
- Inspect: `data/documents/**/*.json`
- Inspect: `data/extracted/*`
- Inspect: `data/evaluation/*`
- Inspect: `backend/app/services/extraction_evaluator.py`
- Inspect: merge commit `359e3bc` for PR #27

**Step 1：核对 Golden 全文范围**

对六份 Golden 比较 `chunks[0].char_start/char_end` 和对应 `document.clean_text` 长度。

Expected：六份均为单文档、单 chunk、`[0, clean_text.length)`。

**Step 2：核对 Experiment 当前实现**

检查目录、runner 和文档术语。

Expected：当前 runner 仍将结果平铺到 `data/extracted/` 与 `data/evaluation/`；没有 Experiment 目录、Manifest、提升命令或 `Track/Treaty` 对象。

**Step 3：核对 PR #27**

检查 `359e3bc^1..359e3bc^2`。

Expected：PR #27 最初由张楚贤引入 `LLMExtractionService`、runner 和测试；合入前其分支又包含 PR #28 的评测闭环改动。

## Task 2：编写阶段决策文档

**Files:**

- Create: `docs/decisions/2026-07-15-llm-golden-experiment-decisions.md`

**Step 1：写术语和当前目录**

明确 Dataset 是文档/Golden 选择清单，Experiment 是围绕一个问题组织的若干 Run 与 Evaluation Run；Baseline 是经审核的 Experiment 引用。列出当前实际目录和仅供后续讨论的目标目录。

**Step 2：写 Golden 与切块决策**

明确人工读完整篇 Document，并在当前本体与标注政策范围内标全；Golden 不由人工按算法切块。v1 `chunks[0]` 只是全文容器，未来算法切块必须映射回全文坐标后评测。

**Step 3：写版本、运行和归档规则**

明确 Prompt/Schema/Golden 版本人工递增，Run ID 每次自动生成，Commit 不自动改变版本；普通运行留本地，只有有实验价值的记录经 PR 进入 Git。

**Step 4：写已确认、当前实现、待定和影响范围**

将四种状态分栏，避免未来同学把计划当现状。

## Task 3：编写评测指标二审稿

**Files:**

- Create: `docs/reviews/2026-07-15-llm-evaluation-metrics-review.md`

**Step 1：定义计分对象和作用域**

区分 Provider Response、Raw Emission、Raw Semantic、Validated Candidate、Accepted Graph 和 Candidate Audit。

**Step 2：定义匹配与指标**

写清实体、关系端到端、条件关系、证据、格式、拒绝、重复和切块指标；不报告没有 TN 定义的 FPR。

**Step 3：加入最小真值表示例**

至少覆盖正确候选被拒绝、幻觉被拒绝、重复候选、解析失败、Golden 为空和预测为空。

**Step 4：写二审问题**

把需要 QA、LLM、架构组确认的问题集中放在文末；当前不设置 F1 门槛和可复现强约束。

## Task 4：同步现有入口文档

**Files:**

- Modify: `docs/guides/golden-annotation-reference.md`
- Modify: `docs/README.md`
- Modify: `docs/plans/2026-07-14-llm-extraction-evaluation-architecture-closure.md`

**Step 1：修正 Golden 手册中的人工切块表述**

将“按后端 chunks 逐块人工标注”改为“整篇审阅，v1 用全文单 chunk 兼容 Schema”；删除“关系两端不在同一算法 chunk 就不标”的要求。

**Step 2：增加文档索引**

在 `docs/README.md` 增加阶段决策和指标二审稿入口。

**Step 3：标记旧总体计划的状态**

在总体计划顶部引用本次决策文档，说明可复现强门槛、Golden 迁移和 Experiment 目录仍待后续 PR，不是现状。

## Task 5：验证并发布文档 PR

**Files:**

- Verify: all files changed by this branch

**Step 1：检查 Markdown 差异**

```powershell
git diff --check
git status --short
```

Expected：无空白错误，只有计划内 Markdown 文件。

**Step 2：检查引用路径和敏感信息**

检查新增文档中的仓库相对路径均存在；检查 API Key、鉴权头和未脱敏聊天内容模式。

Expected：所有静态路径有效，无真实凭据或聊天原文。

**Step 3：提交并推送**

```powershell
git add docs/plans/2026-07-15-llm-evaluation-decisions-doc-pr.md docs/decisions/2026-07-15-llm-golden-experiment-decisions.md docs/reviews/2026-07-15-llm-evaluation-metrics-review.md docs/guides/golden-annotation-reference.md docs/README.md docs/plans/2026-07-14-llm-extraction-evaluation-architecture-closure.md
git commit -m "docs: 明确 LLM 全文标注与评测决策"
git push -u origin docs/llm/evaluation-decisions
```

**Step 4：创建 Draft PR**

PR 正文必须说明：仅文档、无代码行为变化；请 czt0221、QA 和 LLM 组重点二审评测指标与跨段关系证据表达。
