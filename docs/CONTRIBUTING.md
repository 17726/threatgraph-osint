# 开发规范与 Git 流程

> 适用范围：ThreatGraph-OSINT 项目所有成员  
> 目标：降低并行开发冲突，让不熟悉 Git 的成员和 AI Agent 都按同一套流程工作

---

## 1. 核心原则

1. 禁止在 `main` 分支直接开发。
2. 每天开始开发前先拉取最新 `main`。
3. 每个任务单独切分支，完成后提交 MR / Pull Request。
4. MR / Pull Request 经过评审后才能合入 `main`。
5. 修改数据契约或 API 契约前，必须先和架构与接口组确认。
6. 不提交密钥、隐私信息、原始课程 PDF、未脱敏聊天记录和本地环境文件。

---

## 2. 分支命名规范

默认格式：

```text
feat/<task-name>
fix/<task-name>
```

第一个字段默认二选一：

| 字段   | 含义                                 |
| ------ | ------------------------------------ |
| `feat` | 新功能、文档新增、配置新增           |
| `fix`  | 修复问题、修复错误配置、修复文档错误 |

第二个字段是任务名，推荐使用英文小写和连字符：

```text
graph-search
report-api
api-contract
json-output
evaluation-script
```

推荐示例：

```text
feat/graph-search
feat/report-api
feat/api-contract
fix/json-output
fix/evaluation-script
```

不推荐示例：

```text
feature/graph-search
feat/图谱搜索
feat/graph_search
fix/ReportAPI
docs/api-contract
feat/frontend/graph-search
```

提醒：分支名尽量避免中文、空格、下划线和大写字母。当前阶段默认不加入组别字段，后续如果需要再统一调整。

---

## 3. 每日开发流程

每天开始开发前先更新本地 `main`：

```bash
git switch main
git pull --ff-only origin main
```

然后从最新 `main` 切出任务分支：

```bash
git switch -c feat/graph-search
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
git push -u origin feat/graph-search
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

前端页面改动建议附截图。后端接口改动建议贴接口返回示例。涉及 `docs/api-contract.md` 或 `docs/data-contract.md` 的改动，必须提醒架构与接口组评审。

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

不确定时先问组长或架构与接口组，不要直接强推。

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
docs/CONTRIBUTING.md
docs/team-workflow.md
```

再根据任务范围阅读：

```text
前端任务：docs/api-contract.md
后端任务：docs/api-contract.md + docs/data-contract.md
LLM 任务：docs/data-contract.md + docs/architecture.md
测试任务：docs/team-workflow.md + docs/references/course-requirements.md
架构任务：docs/architecture.md + docs/api-contract.md + docs/data-contract.md
```

提醒 Agent：

1. 不要在 `main` 上直接改。
2. 分支名默认使用 `feat/<task-name>` 或 `fix/<task-name>`，当前阶段默认不加入组别字段。
3. commit 标题和正文默认中文。
4. 只改当前任务需要的文件。
5. 修改契约前先说明影响范围。
