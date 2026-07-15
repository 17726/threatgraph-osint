# PR #47 分阶段迁移与修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 PR #47 中混合提交的功能拆成可独立评审、验证和合入的小 PR，在保留 yzq 原始代码作者身份的同时，由维护者对不合理实现逐阶段修复。

**Architecture:** 所有功能 PR 都从当时最新的 `origin/main` 创建，按“迁移原实现 → 记录评审结论 → 单独修复 → 验证 → 合入 main”的顺序串行执行。SQLite 继续作为运行时唯一事实源；P0 先完成严格文档导入、SQLite 查询和可复现流水线，Neo4j 只在真实集成验证通过后作为 P1 投影合入，自动调度和导入后自动触发暂缓。

**Tech Stack:** Git/GitHub、Python 3.13、FastAPI、SQLite、pytest、React 19、TypeScript、Vitest、Docker Compose、Neo4j 5 Community。

---

## 1. 固定审查范围

原始来源：

- PR：`#47 feat: 实现后端流水线处理与前端图谱功能`
- 原始功能提交：`e9d3f5b6efdb4e202334e9968e2ddcee428e058f`
- 原 PR 最终 head：`d667f40aee83a5c13e435f70ec626a389534b386`
- 原 PR 规模：51 个文件，新增 9436 行，删除 166 行

原 PR 的后端 168 个测试通过，前端 10 个测试和构建通过，但格式检查失败。测试通过只能证明现有测试覆盖的行为自洽，不能替代契约、阶段优先级、并发语义和数据边界评审。

## 2. 总体评审结论

| 功能域 | 原方案判断 | 处理决定 |
| --- | --- | --- |
| 文档导入和字段持久化 | 内容哈希去重、完整保存文档元数据是合理方向；把 `text/raw_text/content` 静默升级为 `clean_text`、覆盖调用方提交的哈希不合理 | 保留去重和完整字段持久化；坚持严格 `document.schema.json`，旧格式走显式转换工具 |
| SQLite 图查询 | 从 `DemoStore` 拆出查询服务合理；当前实现可能返回端点缺失的边，目标模糊匹配会误命中，时间和 limit 语义不完整 | 重写过滤闭包、精确匹配、区间和限制语义，增加一跳子图显式接口 |
| Pipeline 任务 | 统一入口和持久化状态合理；原实现把一个复合离线流程伪装成多个独立步骤，且存在重复调度、进程重启遗留任务和异常吞噬风险 | 先实现真实、可复现的 P0 复合任务，再单独增加可靠后台执行；不伪造步骤状态 |
| 导入后自动触发 | 默认触发会产生不可预期的 LLM 成本，并与当前“显式运行、可复现”原则冲突 | 默认不触发，暂缓到 P2 |
| 进程内调度器 | 属于路线图 P2；原集合去重会让同一进程中的失败任务永远不再重试 | 不迁移，另行设计重试和租约后再评估 |
| Neo4j 投影 | SQLite → Neo4j 投影方向正确；当前全量重建会删除整个数据库，缺少应用命名空间、状态/错误字段和真实集成验证 | 作为最后一个 P1 PR 重做，未达到门槛则暂缓 |
| 前端实体一跳筛选 | 用户价值明确；当前实现复用 `target` 模糊语义、移除搜索高亮且存在无障碍和请求竞态问题 | 等后端显式 neighbors API 稳定后单独迁移 |
| 报告生成按钮 | 最新 main 已有实现；原 PR 合并冲突后重复渲染按钮 | 不迁移 |
| `data/pipeline_*` | `pipeline_documents` 与正式 Document 重复；11 份 Extraction 命名不符合正式规则且都缺 Candidate Audit，但候选内容可单独审核 | 不迁移运行时目录；按当前契约审核后，将 9 份非重复合法 Extraction 以正式 `run_id` 文件名迁入 `data/extracted`，限制见审核报告 |
| 原设计/计划文档 | 能说明原作者思路，但内容与实现、当前路线均有漂移 | 由本文吸收有效结论，不迁移旧 `docs/superpowers/*` |

## 3. 提交身份与 PR 规则

每个功能 PR 使用以下固定结构：

1. 从最新 `origin/main` 创建新分支，不让功能 PR 互相堆叠。
2. 机械迁移或 rebase 式冲突适配提交保留 yzq Author、原 AuthorDate，维护者作为 Committer。
3. 设计修复、补充测试和当前 main 适配使用维护者 Author/Committer。
4. 只有双方真正共同完成同一个提交时才添加 `Co-authored-by`。
5. PR 由维护者账号创建，PR 正文列出来源 PR、迁移提交、修复提交、取舍和验证结果。
6. 使用普通 merge 保留独立提交，不使用 squash。
7. 功能 PR 合入后删除远端功能分支，再从更新后的 main 开始下一阶段。

迁移提交前读取原作者身份：

```powershell
$sourceCommit = "e9d3f5b6efdb4e202334e9968e2ddcee428e058f"
$sourceAuthor = git show -s --format='%an <%ae>' $sourceCommit
$sourceAuthorDate = git show -s --format='%aI' $sourceCommit
```

迁移提交：

```powershell
git commit --author="$sourceAuthor" --date="$sourceAuthorDate" `
  -m "feat: 迁移具体功能" `
  -m "迁移自 PR #47 原始提交 e9d3f5b6，保留原始作者身份。"
```

修复提交：

```powershell
git commit -m "fix: 修复具体设计问题"
```

合入前审计：

```powershell
git log --format='%h author=%an <%ae> | committer=%cn <%ce>' origin/main..HEAD
git diff --check origin/main...HEAD
```

---

### Task 1: PR A — 严格文档导入与幂等去重

**Files:**

- Modify: `docs/schemas/document.schema.json`
- Modify: `docs/api-contract.md`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/demo_store.py`
- Modify: `backend/app/db/schema.py`
- Test: `backend/tests/test_api.py`
- Test: `backend/tests/test_demo_store.py`
- Test: `backend/tests/test_document_contract.py`

**保留的原始贡献：** `collection_item_id` 契约、完整文档字段持久化、按 `doc_id/content_hash` 幂等返回、切块元数据。

**拒绝的原始实现：** 不新增宽松 `document_adapter.py`，不接受 `raw_text` 直接成为 `clean_text`，不覆盖错误的调用方 `content_hash`，不恢复自动 demo seed。

**Step 1: 写失败测试**

```python
def test_import_rejects_raw_text_without_clean_text():
    response = client.post("/api/v1/documents/import", json={"doc_id": "legacy", "raw_text": "正文"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ERR_VALIDATION"


def test_duplicate_content_returns_original_doc_id(store, valid_document):
    assert store.import_document(valid_document)["status"] == "imported"
    result = store.import_document({**valid_document, "doc_id": "another-id"})
    assert result["status"] == "skipped"
    assert result["doc_id"] == valid_document["doc_id"]
```

**Step 2: 验证测试先失败**

Run:

```powershell
docker compose run --rm backend python -m pytest `
  backend/tests/test_api.py `
  backend/tests/test_demo_store.py `
  backend/tests/test_document_contract.py -v
```

Expected: 新增测试因 API 未做严格校验、导入未按内容哈希去重而失败。

**Step 3: 迁移 yzq 的独立改动并提交**

只迁移完整字段写入、重复内容查询、事务化导入和对应测试。提交 Author 使用 yzq，Committer 使用维护者。

**Step 4: 修复契约边界**

- API 在写库前调用 `require_valid_document`。
- `DemoStore.import_document` 不生成或修正不合约的哈希。
- `BEGIN IMMEDIATE` 串行化查重与插入，避免两个并发请求同时通过查重。
- 增加普通 `content_hash` 查询索引；不在无法证明历史数据无重复时直接增加唯一索引。
- 使用统一错误响应，不把内部 SQLite 错误直接返回给调用方。

**Step 5: 运行验证并提交维护者修复**

Run:

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
git diff --check origin/main...HEAD
```

Expected: 后端全量测试通过，diff check 无输出。

---

### Task 2: PR B — SQLite 图查询闭包与一跳子图 API

**Files:**

- Create: `backend/app/services/graph_query_service.py`
- Modify: `backend/app/main.py`
- Modify: `docs/api-contract.md`
- Test: `backend/tests/test_graph_query_service.py`
- Test: `backend/tests/test_api.py`

**保留的原始贡献：** 查询服务分层、类型/关系/标签/证据来源过滤、SQLite BFS、证据裁剪。

**必须修复：**

- 目标只按规范化后的完整 ID、完整名称或完整别名匹配，不能使用双向 substring。
- 返回的每条边必须同时拥有可见 source 和 target；不能出现悬空边。
- 一跳实体筛选使用显式 `/api/v1/graph/neighbors`，不滥用组织 `target` 参数。
- 默认 `depth=2` 保持 API 契约兼容。
- 时间窗口使用区间相交语义；未知日期的保留规则写入契约。
- `limit` 必须保留中心节点并保证图闭包，不能简单截断排序后的节点数组。

**Step 1: 写失败测试**

```python
def test_entity_type_filter_never_returns_orphan_edges(service):
    result = service.get_graph(entity_types=["APT_GROUP"])
    visible = {node["id"] for node in result["nodes"]}
    assert all(edge["source"] in visible and edge["target"] in visible for edge in result["edges"])


def test_target_matching_does_not_confuse_apt2_with_apt28(service):
    result = service.get_graph(target="APT2", depth=1)
    assert "apt_group:apt28" not in {node["id"] for node in result["nodes"]}
```

**Step 2: 验证测试先失败**

Run:

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_graph_query_service.py -v
```

Expected: 服务不存在，或迁移原实现后图闭包/精确匹配测试失败。

**Step 3: 迁移 yzq 查询服务并提交**

迁移原服务主体、序列化和测试夹具，Author 使用 yzq。

**Step 4: 由维护者修复查询语义**

先确定可见节点集合，再按端点闭包裁剪边和证据；neighbors 查询只返回中心节点、直接邻居、连接边和相关证据。

**Step 5: 全量验证**

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
```

Expected: 后端全量测试通过。

---

### Task 3: PR C — 可复现的 P0 Pipeline 任务

**Files:**

- Modify: `backend/app/db/schema.py`
- Create: `backend/app/services/pipeline_service.py`
- Modify: `backend/app/main.py`
- Modify: `docs/api-contract.md`
- Test: `backend/tests/test_pipeline_service.py`
- Test: `backend/tests/test_api.py`

**保留的原始贡献：** 持久化 job/status、可注入执行器、明确失败信息、按文档或目标组织运行。

**拒绝的原始实现：** 不把 `OfflineExtractionPipeline.run()` 内一次完成的工作伪装成 6 个已独立执行的步骤；不让 `_invoke_step` 吞掉业务函数自身抛出的 `TypeError` 后再次调用；不允许既没有 `doc_id` 也没有 `target_group` 的任务进入后台后才失败。

**Step 1: 写任务状态与原子 claim 测试**

```python
def test_job_can_only_be_claimed_once(service):
    job = service.create_job(doc_id="apt28_049")
    assert service.claim(job["job_id"]) is True
    assert service.claim(job["job_id"]) is False


def test_pipeline_reports_one_real_composite_operation(service):
    result = service.run_sync(doc_id="apt28_049")
    assert result["operation"] == "extract_and_build"
    assert result["status"] == "succeeded"
```

**Step 2: 运行测试确认失败**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_pipeline_service.py -v
```

**Step 3: 迁移 job schema 和原服务骨架**

迁移 `pipeline_jobs`、状态序列化和注入式测试框架，Author 使用 yzq。

**Step 4: 维护者修复执行模型**

- P0 先暴露一个真实复合操作 `extract_and_build`，内部复用现有离线流水线。
- 创建任务时校验作用域，使用稳定 request key 避免活动任务重复。
- 执行前用条件 UPDATE 原子 claim `pending -> running`。
- 应用启动时把上次进程遗留的 `running` 标记为中断失败，不伪装恢复。
- 所有中间事实仍写 SQLite；运行时临时文件写临时目录，不新增 `data/pipeline_*` Git 路径。

**Step 5: 验证**

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
```

---

### Task 4: PR D — 后台执行、状态轮询和前端导入

**Files:**

- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/PipelineModal.tsx`
- Test: `backend/tests/test_pipeline_service.py`
- Test: `backend/tests/test_api.py`
- Test: `frontend/src/api/client.test.ts`

**Step 1: 为重复提交、关闭和轮询写失败测试**

测试两个请求只能调度一次、关闭服务会等待或明确取消在途任务、前端识别 failed/timeout/aborted。

**Step 2: 迁移 yzq 的后台提交和轮询代码**

迁移 ThreadPool/轮询主体和对应测试，Author 使用 yzq。

**Step 3: 修复生命周期与前端契约**

- 只有成功创建并 claim 的新 job 才提交执行器。
- 默认不在文档导入后自动运行 LLM；用户显式点击后调用 Pipeline API。
- 前端解析标准 JSON 后先导入，再显式提交 doc_id；重复文档仍可手动重新运行。
- 使用 `AbortController` 停止已关闭弹窗的轮询。
- 读取统一错误响应，不只显示 HTTP 状态码。
- 用 `extraction_mode=reviewed|live` 替代含义不清且未生效的 `use_cache`；`reviewed` 只使用已审核结果，`live` 才调用外部模型。
- `reviewed` 任务记录 `import_extraction_and_build`，`live` 任务记录 `extract_and_build`，避免把导入既有结果误称为现场抽取。
- `live` 只允许单个 `doc_id`，禁止按目标组织误触发批量 LLM 调用。
- 不重复添加当前 main 已有的报告生成按钮。

**Step 4: 前后端验证**

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
docker compose run --rm --no-deps frontend npm run test
docker compose run --rm --no-deps frontend npm run build
```

---

### Task 5: PR E — 前端实体一跳筛选

**Files:**

- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/SearchBar.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/api/client.test.ts`

**Step 1: 写 API 和交互失败测试**

验证 `fetchNeighbors` 调用显式 neighbors API；清空输入恢复组织图谱；快速连续选择只接受最后一次响应。

**Step 2: 迁移 yzq 的 SearchBar 和 App 状态**

Author 使用 yzq，不迁移重复报告按钮。

**Step 3: 维护者修复交互**

- 保留搜索结果高亮或明确改为中心节点视觉状态。
- 搜索结果使用 button/键盘可操作元素。
- 目标组织切换时清除不再适用的一跳筛选。
- 使用请求序号或 AbortController 防止旧响应覆盖新选择。
- 时间筛选继续使用 `first_seen <= selected_year` 的既有产品语义，除非契约另行变更。

**Step 4: 验证**

```powershell
docker compose run --rm --no-deps frontend npm run test
docker compose run --rm --no-deps frontend npm run build
```

---

### Task 6: PR F — Neo4j 可重建投影（P1 条件合入）

**Files:**

- Modify: `backend/requirements.txt`
- Modify: `backend/app/db/schema.py`
- Create: `backend/app/services/neo4j_service.py`
- Modify: `backend/app/main.py`
- Modify: `docs/api-contract.md`
- Test: `backend/tests/test_neo4j_service.py`
- Test: `backend/tests/test_api.py`

**Step 1: 先写安全和恢复测试**

必须覆盖：应用命名空间外节点不会被 rebuild 删除、同步失败不推进水位、状态记录错误、首次同步可处理已有 canonical 数据、关系端点缺失时可重试。

**Step 2: 迁移 yzq 的投影和增量同步主体**

Author 使用 yzq。

**Step 3: 维护者完成安全修复**

- rebuild 只删除本应用标签/关系，不执行无范围的 `MATCH (n) DETACH DELETE n`。
- 创建应用实体唯一约束和必要索引。
- `sync_state` 保存 status、error、last_success_at 和 watermark。
- 首次使用必须全量 rebuild，不能假设历史 canonical 写入已产生 outbox。
- evidence 作为属性引用或有明确边的节点，不创建无连接的孤立 Evidence 节点。
- 实现 `GET /neo4j/status` 和 `POST /neo4j/sync`。
- Neo4j 失败只影响增强能力，SQLite 图谱和报告保持可用。

**Step 4: mock 和真实集成验证**

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
docker compose up -d neo4j
docker compose run --rm backend python -m pytest backend/tests/test_neo4j_service.py -v
```

只有真实 Neo4j 容器下完成 rebuild、增量同步、清空后恢复和路径查询，才合入该 P1 PR；否则保留分支并明确暂缓。

---

### Task 7: 不迁移项与原 PR 收尾

**Files:**

- Modify: `docs/plans/2026-07-16-pr47-staged-integration.md`
- GitHub: PR #47

**Step 1: 明确不迁移内容**

- `backend/app/services/scheduler_service.py`
- `backend/tests/test_scheduler_service.py`
- `data/pipeline_documents/*`
- `data/pipeline_extracted/*` 原目录及重复版本；9 份通过当前契约的非重复 Extraction 已按
  `docs/reports/pr47-extraction-artifact-audit.md` 选择性迁入正式目录，但不作为评测 Baseline
- `docs/superpowers/*`
- 重复的 ReportPanel 按钮
- 恢复 demo seed 的冲突修复

**Step 2: 完成最终回归**

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
docker compose run --rm --no-deps frontend npm run test
docker compose run --rm --no-deps frontend npm run build
docker compose run --rm --no-deps frontend npm run format:check
```

如果格式检查仍有 main 基线问题，必须区分既有问题和本系列 PR 新增问题；任何新改文件都必须通过 Prettier。

**Step 3: 审计提交身份**

```powershell
git log --format='%h author=%an <%ae> | committer=%cn <%ce>' <系列起点>..main
```

确认迁移提交的 Author 映射到 `yzq38`，维护者修复提交归维护者，真正共同提交才包含 `Co-authored-by`。

**Step 4: 关闭原 PR #47**

在 PR #47 留下替代 PR 清单、合入 SHA、不迁移项和原因，然后以“已由分阶段 PR 取代”关闭，不直接合并原大 PR。
