# AGENTS.md

本文件用于约束所有 AI Agent 在本仓库内的行为。适用范围为整个仓库。

## 基本要求

1. 永远使用中文回答。
2. 代码注释、提交标题和提交正文默认使用中文。
3. 修改前先阅读 `README.md`、`TODO.md` 以及和当前任务相关的 `docs/*` 文档。
4. 不要擅自扩大任务范围，不做无关重构，不覆盖他人未提交改动。
5. 不提交 `.env`、API Key、未脱敏聊天记录、私有链接、课程原始 PDF 或个人隐私信息。

## 分支规则

禁止直接在 `main` 分支开发。开始改文件前，必须确认当前分支不是 `main`。

分支名推荐使用下面结构：

```text
<type>/<group>/<task-name>
```

也允许任务较小时省略组别字段：

```text
<type>/<task-name>
```

命名规范：

1. 第一个字段使用 `feat`、`fix`、`docs`、`test`、`refactor` 或 `chore` 等类型。
2. 第二个字段是可选组别缩写，只允许使用 `arch`、`data`、`llm`、`fe`、`qa`。
3. 最后一个字段是任务名，推荐使用英文小写和连字符，例如 `graph-search`。
4. 分支名避免使用中文、空格、下划线和大写字母。
5. 后端不是单独小组，不使用独立 `be` 组别；后端横向工作按牵头或业务归属小组选择组别缩写。

组别缩写：

```text
arch：架构与数据规范组
data：数据与样本组
llm：LLM 抽取与分析组
fe：图谱与前端组
qa：报告答辩与测试组
```

示例：

```text
feat/arch/schema-v1
feat/data/apt28-sample
feat/llm/json-output
feat/fe/graph-search
test/qa/golden-eval
feat/graph-search
fix/report-api
```

## Git 流程

开始开发前：

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/arch/schema-v1
```

完成开发后：

```bash
git status
git add <files>
git commit -m "feat: 添加具体功能说明"
git push -u origin feat/arch/schema-v1
```

然后在 GitHub 上创建 MR / Pull Request，经过评审后才能合入 `main`。

## Commit 规范

提交信息使用 Conventional Commits 的轻量格式：

```text
<type>: <中文说明>
```

常用类型：

| 类型       | 用途                         |
| ---------- | ---------------------------- |
| `feat`     | 新功能                       |
| `fix`      | 缺陷修复                     |
| `docs`     | 文档修改                     |
| `style`    | 格式化或样式调整，不改变逻辑 |
| `refactor` | 重构，不改变外部行为         |
| `test`     | 测试相关                     |
| `chore`    | 工具、配置、依赖等维护       |

示例：

```text
feat: 添加图谱搜索接口
fix: 修复报告详情缺少证据的问题
docs: 补充开发流程规范
style: 格式化前端代码
test: 添加报告接口测试
chore: 添加 Prettier 配置
```

如果需要提交正文，正文默认使用中文，说明变更原因、影响范围和验证方式。

## Force Push 规则

1. 严禁对 `main` 分支 Force Push。
2. 只有确认当前分支没有其他开发者共同开发时，才允许 Force Push。
3. 必须优先使用 `git push --force-with-lease`，不要使用普通 `--force`。
4. Force Push 前必须检查远端分支是否包含他人新提交。

## 项目约束

1. SQLite 是唯一事实源。
2. `graph.json` 只作为导出格式、前端 mock、演示兜底和 Neo4j 同步输入。
3. Neo4j 是增强能力，不作为事实源。
4. LLM 原始输出不能直接写入 Neo4j。
5. 前端只调用 FastAPI，不直接读取 SQLite、`graph.json` 或 Neo4j。
6. API 字段以 `docs/api-contract.md` 为准。
7. 数据字段以 `docs/data-contract.md` 为准。
8. 跨组字段变更必须先更新契约文档并提醒架构与数据规范组评审。
9. 后端是横向工作流，不是单独小组；修改后端代码时必须遵守对应业务边界和契约。

## 验证要求

根据改动范围运行对应命令：

```bash
docker compose run --rm backend python -m pytest backend/tests -v
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run format:check
```

无法运行验证时，必须在回复或 MR 说明中写明原因。