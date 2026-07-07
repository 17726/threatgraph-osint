# 开发规范与 Git 流程

> 适用范围：ThreatGraph-OSINT 项目所有成员  
> 目标：降低并行开发冲突，让不熟悉 Git 的成员和 AI Agent 都按同一套流程工作

---

## 1. 核心原则

1. 禁止在 `main` 分支直接开发。
2. 每天开始开发前先拉取最新 `main`。
3. 每个任务单独切分支，完成后提交 MR / Pull Request。
4. MR / Pull Request 经过评审后才能合入 `main`。
5. 修改数据契约或 API 契约前，必须先和架构与数据规范组确认。
6. 不提交密钥、隐私信息、原始课程 PDF、未脱敏聊天记录和本地环境文件。

---

## 2. 分支命名规范

推荐格式：

```text
<type>/<group>/<task-name>
```

也允许任务较小时省略组别字段：

```text
<type>/<task-name>
```

第一个字段表示变更类型：

| 字段       | 含义                                 |
| ---------- | ------------------------------------ |
| `feat`     | 新功能、文档新增、配置新增           |
| `fix`      | 修复问题、修复错误配置、修复文档错误 |
| `docs`     | 文档修改                             |
| `test`     | 测试、评测、质量门禁                 |
| `refactor` | 重构                                 |
| `chore`    | 配置、依赖、杂项                     |

第二个字段可选，用于标记负责小组，方便观察每组进度和工作内容：

| 组别缩写 | 含义                   |
| -------- | ---------------------- |
| `arch`   | 架构与数据规范组       |
| `data`   | 数据与样本组           |
| `llm`    | LLM 抽取与分析组       |
| `fe`     | 图谱与前端组           |
| `qa`     | 报告答辩与测试组       |

后端不是单独小组，不设置独立组别缩写。涉及 FastAPI、SQLite、pipeline、归一化、导出等后端横向工作时，优先使用牵头或业务归属小组的缩写。例如架构组牵头的后端骨架用 `arch`，数据导入接口可用 `data`，抽取接口可用 `llm`。

最后一个字段是任务名，推荐使用英文小写和连字符：

```text
graph-search
report-api
api-contract
json-output
evaluation-script
```

推荐示例：

```text
feat/arch/schema-v1
feat/data/apt28-sample
feat/llm/json-output
feat/fe/graph-search
test/qa/golden-eval
feat/graph-search
fix/report-api
```

不推荐示例：

```text
feature/graph-search
feat/图谱搜索
feat/graph_search
fix/ReportAPI
feat/backend/graph-search
feat/be/report-api
```

提醒：分支名尽量避免中文、空格、下划线和大写字母。组别字段是推荐项，不是强制项；如果使用组别字段，必须使用上面的五个正式缩写。

---

## 3. 每日开发流程

每天开始开发前先更新本地 `main`：

```bash
git switch main
git pull --ff-only origin main
```

然后从最新 `main` 切出任务分支：

```bash
git switch -c feat/arch/schema-v1
```

开发过程中随时查看状态：

```bash
git status
```

提交前只加入和本次任务有关的文件：

```bash
git add <file1> <file2>
git commit -m "feat: 添加图谱搜索页面"
```

推送分支：

```bash
git push -u origin feat/arch/schema-v1
```

最后到 GitHub 创建 MR / Pull Request，目标分支选择 `main`。

---

## 4. MR / Pull Request 要求

每个 MR / Pull Request 至少说明：

```text
1. 本次改了什么
2. 为什么要改
3. 怎么验证
4. 是否影响 API 契约或数据契约
```

前端页面改动建议附截图。后端接口改动建议贴接口返回示例。涉及 `docs/api-contract.md` 或 `docs/data-contract.md` 的改动，必须提醒架构与数据规范组评审。

合入要求：

1. 不允许直接推送到 `main`。
2. 至少经过一次评审。
3. 本地或 CI 验证通过。
4. 解决明显冲突后再合入。

---

## 5. Commit 规范

提交信息采用 Conventional Commits 的轻量版本：

```text
<type>: <中文说明>
```

类型使用英文，冒号后的标题默认中文：

| 类型       | 用途                 | 示例                              |
| ---------- | -------------------- | --------------------------------- |
| `feat`     | 新功能               | `feat: 添加图谱搜索接口`          |
| `fix`      | 缺陷修复             | `fix: 修复报告详情缺少证据的问题` |
| `docs`     | 文档修改             | `docs: 补充分支命名规范`          |
| `style`    | 格式化或样式调整     | `style: 格式化前端代码`           |
| `refactor` | 重构                 | `refactor: 重构图谱数据转换逻辑`  |
| `test`     | 测试相关             | `test: 添加报告接口测试`          |
| `chore`    | 工具、配置、依赖维护 | `chore: 添加 Prettier 配置`       |

如果需要写 commit body，正文默认中文。正文建议说明：

```text
1. 修改原因
2. 影响范围
3. 验证方式
```

不要使用含糊提交信息：

```text
update
fix bug
改一下
wip
```

---

## 6. Force Push 规则

Force Push 会改写远端历史，初学者默认不要使用。

必须满足以下条件才允许使用：

1. 当前分支不是 `main`。
2. 当前分支只有你或你的 Agent 在开发。
3. 已确认没有其他人基于这个分支继续开发。
4. 已确认远端分支没有他人的新提交。

如果必须使用，优先使用：

```bash
git push --force-with-lease
```

不要使用：

```bash
git push --force
```

不确定时先问组长或架构与数据规范组，不要直接强推。

---

## 7. 格式化与验证

前端统一使用 Prettier 做格式化：

```bash
npm --prefix frontend run format
npm --prefix frontend run format:check
```

前端测试和构建：

```bash
npm --prefix frontend run test
npm --prefix frontend run build
```

后端测试：

```bash
docker compose run --rm backend python -m pytest backend/tests -v
```

如果本机没有 Docker，也可以在后端依赖安装完成后运行：

```bash
python -m pytest backend/tests -v
```

提交 MR / Pull Request 前，至少运行和本次改动相关的验证命令。无法运行时，在 MR / Pull Request 说明里写清楚原因。

---

## 8. AI Agent 使用提醒

使用 AI Agent 开发时，先要求 Agent 阅读：

```text
AGENTS.md
README.md
TODO.md
docs/development-guidelines.md
docs/team-workflow.md
```

再根据任务范围阅读：

```text
fe 任务：docs/api-contract.md
be 任务：docs/api-contract.md + docs/data-contract.md + docs/team-workflow.md
llm 任务：docs/data-contract.md + docs/architecture.md
qa 任务：docs/team-workflow.md + docs/references/course-requirements.md
arch 任务：docs/architecture.md + docs/api-contract.md + docs/data-contract.md
```

提醒 Agent：

1. 不要在 `main` 上直接改。
2. 分支名推荐使用 `<type>/<group>/<task-name>`，也允许省略组别字段使用 `<type>/<task-name>`。
3. 组别字段只使用 `arch`、`data`、`llm`、`fe`、`qa`。
4. commit 标题和正文默认中文。
5. 只改当前任务需要的文件。
6. 修改契约前先说明影响范围。
