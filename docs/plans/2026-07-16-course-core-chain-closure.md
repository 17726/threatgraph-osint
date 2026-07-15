# 课程核心链路收口 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在课程验收前优先跑通“三类来源采集与预处理 → LLM 实体/关系抽取 → 校验归一化 → 行为与 MITRE 分析 → SQLite 图谱查询与可视化 → 三组织结构化报告”的可复现闭环，并把评测收缩为不阻塞主链路的最小开发集结果。

**Architecture:** 复用现有 crawler、标准 Document、LLM Extraction、OfflineExtractionPipeline、SQLite canonical graph、FastAPI 和 React，不引入新的事实源或重型调度平台。课程演示采用三篇已存在且有审核抽取结果的主样本完成三组织闭环，另用一篇社媒/论坛样本证明第三类来源的自动预处理；在线 LLM 和在线采集保留显式入口，同时准备仓库内审核工件作为答辩降级路径。

**Tech Stack:** Python 3.13、FastAPI、SQLite、pytest、React 19、TypeScript、Vitest、Docker Compose、OpenAI-compatible LLM API。

---

## 1. 课程验收边界

课程要求以 `docs/references/course-requirements.md` 为准，P0 必须覆盖：

```text
三类来源自动采集与预处理
→ 中英文标准 Document
→ LLM NER / RE
→ 校验、归一化和证据绑定
→ 行为模式、MITRE ATT&CK 和受约束推理
→ SQLite canonical graph
→ 多维查询、路径追踪和前端可视化
→ 结构化智能报告
```

以下能力不再阻塞课程 P0：

- 完整 Raw Semantic / Validated Candidate 新评测器；
- Dataset/Experiment Manifest 平台和 promote 命令；
- Golden v2 多证据 span；
- 切块消融与统计显著性检验；
- 自动 catalog、CI 自动生成工件；
- Neo4j 投影、GraphRAG、STIX/MISP/OpenCTI 兼容。

PR #36 的多文档 Golden 文件名方案保存在
`docs/superpowers/plans/2026-07-14-multi-document-golden-filename.md`，仅作为历史方案；当前正式方向仍是“一篇 Document 对应一份 Golden，多文档由 Dataset/Experiment Manifest 编组”。

## 2. 当前基线与事实

截至 2026-07-16 的 `main`（`d88d229`，已合入 PR #55）：

- 标准文档 297 篇：APT28 104、Kimsuky 86、Lazarus 107；
- 中文 165 篇、英文 132 篇；
- `news` 191 篇、`vendor_report` 72 篇、`social_forum` 34 篇；
- 三个组织各有中英文 Golden，共 6 篇；
- 已有真实 LLM 抽取、Candidate Audit、SQLite 导入、归一化、图查询、路径查询和报告服务；
- PR #55 已对齐前后端 Pipeline JSON 契约，并打通标准 Document 导入、`reviewed/live` 抽取、后台任务、状态轮询、离线归一建图与前端刷新；
- 但真实运行 `apt28_080` 的 `reviewed` 模式会误选 `*-candidate-audit.json` 并因 Schema 不匹配失败；同一 `doc_id` 的多模型结果也缺少显式审核选择；
- Pipeline 仍不包含按 URL/关键词采集、采集后 LLM 相关性过滤及两者的统一进度；
- 离线流水线已能按 `USES/TARGETS` 关系生成基础行为模式和简报，但真实 MITRE 映射、分析 API 边界与五章节报告仍未完成三组织验收；
- 当前默认演示库未经三组织固定样本重建，不能用其空表推断代码未实现；必须通过独立验收库判断产物是否齐备；
- 最新基线为后端 148 个测试通过（1 条既有 Starlette 弃用警告），前端 6 个测试通过。

## 3. 固定演示样本

三组织主链路使用已有审核工件，不在演示现场依赖付费 API：

| 目标组织 | Document | Extraction | 语言 | 作用 |
| --- | --- | --- | --- | --- |
| APT28 | `data/documents/apt28/apt28_080.json` | `data/extracted/extract-apt28_080-deepseek-v4-flash-1.0-1.0-20260714075123666577-c463deb3.json` | en | 英文厂商报告、APT 行为与工具链 |
| Kimsuky | `data/documents/kimsuky/kimsuky_001.json` | `data/extracted/extract-kimsuky_001-deepseek-v4-flash-1.0-1.0-20260714080134257073-c920384d.json` | zh | 中文公开情报、技术和时间实体 |
| Lazarus | `data/documents/lazarus/lazarus_001.json` | `data/extracted/extract-lazarus_001-deepseek-v4-flash-1.0-1.0-20260714080135364375-538cfcc0.json` | zh | 事件、时间、行为模式和关系网络 |

第三类来源演示使用一篇现有 `social_forum` 文档，例如
`data/documents/apt28/suqi625_apt28_093.json`。它用于证明社媒/论坛数据的批量转换、清洗、去重和标准化，不要求在课程 P0 对全部社媒文档调用付费 LLM。

## 4. P0 完成定义

一次课程演示必须能够产生以下可见结果：

1. 展示安全来源、新闻来源和社媒/论坛来源的采集或批量适配命令及标准 Document 输出。
2. 展示中英文 Document 的 Schema、清洗元数据和内容哈希。
3. 对三组织主样本导入审核 Extraction，候选、正式实体、关系和证据进入 SQLite。
4. 前端按组织展示真实图谱、实体/关系证据、过滤和一条路径查询。
5. 至少生成证据可追溯的行为模式；从明确技术名称生成 MITRE ATT&CK 映射。
6. 三个组织都生成画像、行为、关系网络、时间线、威胁评估五类报告章节。
7. 在线 LLM 或采集失败时，可以使用仓库内审核工件完成同一后半链路。
8. 展示六篇开发集的基础实体/关系评测结果，并明确不主张泛化能力。

---

### Task 1: 纠正路线和进度文档

**Files:**
- Modify: `TODO.md`
- Modify: `docs/stage-roadmap.md`
- Modify: `README.md`

**Step 1: 更新优先级定义**

把三类来源、三目标组织、MITRE/行为分析和结构化报告明确列为课程验收 P0；把完整评测平台、切块消融、Neo4j 和自动 catalog 降为 P1/P2。

**Step 2: 按代码事实更新进度**

将已经实现的文档导入、SQLite 图查询、路径 API 和手动 Pipeline 标为“基础实现已完成，真实三组织集成待验收”，不能简单勾选为完整闭环。

**Step 3: 增加可核对的验收表**

在 `TODO.md` 增加以下状态：

```text
未开始 / 代码已实现 / 已有数据 / 已集成验证 / 已准备答辩材料
```

**Step 4: 检查文档差异**

Run:

```powershell
git diff --check
git diff -- TODO.md docs/stage-roadmap.md README.md
```

Expected: 无尾随空格；P0/P1 定义与课程要求一致。

**Step 5: Commit**

```powershell
git add TODO.md docs/stage-roadmap.md README.md
git commit -m "docs: 重排课程核心链路优先级"
```

---

### Task 2: 锁定已合入 Pipeline 能力并做演示验收

**Files:**
- Create: `config/course-demo.json`
- Modify: `backend/app/services/pipeline_service.py`
- Modify: `backend/tests/test_pipeline_service.py`
- Modify: `frontend/src/api/client.test.ts`
- Modify: `docs/demo-flow.md`
- Reference: `docs/api-contract.md`

**Step 1: 确认 PR #55 不再重复实现**

以 `docs/api-contract.md` 为准锁定以下语义：

- `POST /api/v1/pipeline/run` 使用 JSON，`doc_id` 和 `target_group` 必须二选一；
- `reviewed` 只导入已审核工件，`live` 才授权外部 LLM 调用；
- 创建任务返回 HTTP 202，前端轮询到 `succeeded/failed`；
- `use_cache` 已废弃，不能恢复含义模糊的布尔开关。

**Step 2: 补一个固定样本 reviewed 集成测试**

当前默认定位器使用 `*{doc_id}*.json` 并取排序第一项，会把 `*-candidate-audit.json` 误当成 extraction_result；同一文档存在多个模型结果时也没有审核选择依据。先用真实固定样本锁定这个失败：

```python
def test_reviewed_pipeline_builds_fixed_apt28_sample(tmp_path):
    service = PipelineService(tmp_path / "course-demo.db")
    result = service.run_sync(
        doc_id="apt28_080",
        extraction_mode="reviewed",
    )
    assert result["status"] == "succeeded"
    summary = result["result"]["summaries"][0]
    assert summary["canonical_entities"] > 0
    assert summary["canonical_relations"] > 0
    service.close()
```

测试必须使用临时 SQLite，不依赖默认演示库，且断言任务状态、真实操作名与非零归一产物。

**Step 3: 用显式清单解析审核工件**

`config/course-demo.json` 显式记录第 3 节三对 Document/Extraction。Pipeline 定位器按以下规则工作：

1. 固定演示 `doc_id` 必须使用清单中的精确路径；
2. 其他文档先排除 `*-candidate-audit.json`，再对候选执行 extraction_result Schema 校验；
3. 合法候选不是唯一时明确失败并列出 `run_id`，不用字典序或文件时间猜测“已审核”版本。

**Step 4: 复核前端契约回归**

现有 `frontend/src/api/client.test.ts` 已覆盖文档导入、`reviewed/live` 请求和状态查询。只补固定样本所需的端到端断言，不重写 `PipelineModal` 和请求客户端。

**Step 5: 运行回归并记录基线**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_pipeline_service.py backend/tests/test_api.py -v
docker compose run --rm --no-deps frontend npm run test -- --run
```

Expected: 不配置 API Key 时 `reviewed` 固定样本仍成功；`live` 只做授权边界测试，不在 CI 调用外部服务。

**Step 6: 更新演示文档并提交**

```powershell
git add config/course-demo.json backend/app/services/pipeline_service.py backend/tests/test_pipeline_service.py frontend/src/api/client.test.ts docs/demo-flow.md
git commit -m "fix: 锁定已审核抽取工件"
```

---

### Task 3: 固化三类来源采集与预处理验收

**Files:**
- Create: `scripts/verify_course_source_coverage.py`
- Create: `backend/tests/test_course_source_coverage.py`
- Modify: `scripts/crawler_v1.py`
- Modify: `backend/tests/test_crawler_v1_document_contract.py`
- Create: `docs/guides/course-demo.md`

**Step 1: 写来源覆盖失败测试**

```python
def test_course_sources_cover_three_classes_and_two_languages(tmp_path):
    summary = summarize_documents(tmp_path)
    assert set(summary["source_types"]) >= {"vendor_report", "news", "social_forum"}
    assert set(summary["languages"]) >= {"zh", "en"}
```

同时测试每份 Document 的 `content_hash` 与 `clean_text` 一致、`source_url/source_name/source_type` 非空、重复 URL 和重复正文会被报告。

**Step 2: 实现只读覆盖检查器**

检查器只读取 `data/documents`，输出 JSON 摘要，不写 SQLite，不生成第二事实源：

```powershell
python scripts/verify_course_source_coverage.py --input data/documents --json
```

Expected: 输出三目标、三来源类型、中英文数量以及错误列表；存在错误时返回非零退出码。

**Step 3: 给 crawler 增加显式来源选择**

增加 `--sources qianxin,thehackernews,unit42,freebuf`，默认仍运行全部；课程演示可以只运行一个安全来源和一个新闻来源，避免现场等待四个站点。

**Step 4: 写三类来源操作说明**

`docs/guides/course-demo.md` 明确：

- Unit 42/奇安信作为网络安全来源；
- The Hacker News/FreeBuf 作为新闻来源；
- SuQi625 Reddit 数据通过 `convert_suqi625_dataset.py` 批量转换为社媒/论坛标准 Document；
- 社媒路径是公开数据集适配，不宣称为实时 Reddit API 爬虫；
- 三类输入都经过清洗、去重、结构化和 Schema 校验。

**Step 5: 验证并提交**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_course_source_coverage.py backend/tests/test_crawler_v1_document_contract.py backend/tests/test_convert_raw_documents.py backend/tests/test_convert_suqi625_dataset.py -v
docker compose run --rm backend python scripts/verify_course_source_coverage.py --input data/documents --json
git add scripts/verify_course_source_coverage.py scripts/crawler_v1.py backend/tests/test_course_source_coverage.py backend/tests/test_crawler_v1_document_contract.py docs/guides/course-demo.md
git commit -m "feat: 固化三类来源采集验收"
```

---

### Task 4: 在已有规则分析上补齐 MITRE 映射

**Files:**
- Create: `backend/app/services/mitre_catalog.py`
- Modify: `backend/app/services/offline_extraction_pipeline.py`
- Modify: `backend/app/services/demo_store.py`
- Test: `backend/tests/test_offline_extraction_pipeline.py`
- Test: `backend/tests/test_demo_store.py`

**Step 1: 锁定已有行为规则，再写 MITRE 失败测试**

```python
def test_pipeline_builds_evidence_backed_mitre_mapping(pipeline, apt28_fixture):
    summary = pipeline.run(*apt28_fixture)
    assert summary.behavior_patterns >= 1
    with pipeline.connect() as connection:
        mapping = connection.execute(
            "SELECT technique_id, evidence_ids_json FROM mitre_mappings WHERE target_group = 'APT28'"
        ).fetchone()
    assert mapping["technique_id"] == "T1566"
    assert json.loads(mapping["evidence_ids_json"])
```

**Step 2: 建立最小受审 ATT&CK 映射表**

只覆盖当前主样本明确出现的技术，不做模糊相似匹配：

```python
TECHNIQUE_MAP = {
    "钓鱼邮件": ("T1566", "Phishing", "Initial Access"),
    "钓鱼攻击": ("T1566", "Phishing", "Initial Access"),
    "钓鱼页面": ("T1566.002", "Spearphishing Link", "Initial Access"),
    "userinitmprlogonscript": ("T1037.001", "Logon Script (Windows)", "Persistence"),
    "进程注入": ("T1055", "Process Injection", "Defense Evasion"),
}
```

任何新映射必须先增加测试和来源说明，不允许运行时用字符串包含关系猜测 Technique ID。

PR #55 已通过 `OfflineExtractionPipeline.build_rule_analysis` 从 `USES/TARGETS` 关系生成基础行为模式，本任务不重写该逻辑。

**Step 3: 增量扩展规则分析**

在现有 `USES`、`TARGETS` 模式之外：

- 从与目标组织有证据关系的 `TECHNIQUE`、`BEHAVIOR_PATTERN`、`EVENT` 构建行为模式；
- `mitre_mappings.evidence_ids_json` 必须来自原关系或实体证据；
- 先删除目标组织旧派生结果，再在同一事务重建；
- 不把分析推断写回 canonical `relations`。

**Step 4: 增加三组织夹具断言**

三组织都至少生成一个行为模式；包含已知 Technique 的组织至少生成一个 MITRE 映射。没有已知映射时返回空列表，不伪造 Technique ID。

**Step 5: 验证并提交**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_offline_extraction_pipeline.py backend/tests/test_demo_store.py -v
git add backend/app/services/mitre_catalog.py backend/app/services/offline_extraction_pipeline.py backend/app/services/demo_store.py backend/tests/test_offline_extraction_pipeline.py backend/tests/test_demo_store.py
git commit -m "feat: 生成可追溯行为与 MITRE 映射"
```

---

### Task 5: 移除分析 API 占位返回

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/demo_store.py`
- Modify: `docs/api-contract.md`
- Test: `backend/tests/test_api.py`

**Step 1: 写失败测试**

```python
def test_threat_assessment_is_not_hard_coded(client, seeded_store):
    response = client.get("/api/v1/analysis/APT28/threat-assessment")
    assert response.status_code == 200
    assert response.json()["data"]["evidence_ids"]


def test_inferences_are_filtered_by_target_group(client, seeded_store):
    data = client.get("/api/v1/analysis/APT28/inferences").json()["data"]
    assert all(item["target_group"] == "APT28" for item in data["inferences"])
```

**Step 2: 从 SQLite 返回真实结果**

- `behavior`、`mitre`、`inferences` 在 SQL 层按 `target_group` 过滤；
- `threat-assessment` 返回 `threat_assessments` 最新记录；
- 没有数据时返回空对象或明确 `not_generated`，不返回固定 `HIGH/82`；
- `/analysis/{target_group}/run` 调用真实分析重建服务并返回计数。

**Step 3: 验证并提交**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_api.py backend/tests/test_demo_store.py -v
git add backend/app/main.py backend/app/services/demo_store.py backend/tests/test_api.py docs/api-contract.md
git commit -m "fix: 移除行为分析占位响应"
```

---

### Task 6: 验收并补齐三组织结构化报告

**Files:**
- Modify: `backend/app/services/report_generator.py`
- Modify: `backend/app/services/llm_report_service.py`
- Modify: `backend/app/services/demo_store.py`
- Modify: `scripts/generate_reports.py`
- Test: `backend/tests/test_demo_store.py`
- Create: `backend/tests/test_generate_reports.py`

**Step 1: 写规则降级失败测试**

现有 `report_generator.py`、`LLMReportService` 和 `DemoStore.generate_report` 已能生成并持久化五类章节；本任务不再新建第二套报告管线，只修复规则强制模式、证据引用和三组织验收中暴露的问题。

```python
def test_force_rule_never_calls_llm(seeded_three_target_db, monkeypatch):
    monkeypatch.setattr(LLMReportService, "generate", lambda *_: (_ for _ in ()).throw(AssertionError("不得调用")))
    result = generate_reports(seeded_three_target_db, force_rule=True)
    assert all(item["status"] == "generated" for item in result)
```

**Step 2: 修复 `--rule`**

把 `force_rule` 传入报告生成服务；规则模式直接调用 fallback，不先尝试 LLM。

**Step 3: 强制五类章节与证据边界**

每个报告必须包含：

```text
profile
behavior_patterns
network
timeline
threat_assessment
```

章节引用事实时必须写入 `evidence_ids` 或 `graph_refs`；LLM 输出引用未知 ID 时拒绝该引用并降级，不允许把模型自由文本当作事实。

**Step 4: 增加三组织报告测试**

对三组织演示库运行规则报告，断言每个目标都有 5 个章节、非空 Markdown 和生成时间；在线 LLM 报告只做可选集成验证。

**Step 5: 验证并提交**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_generate_reports.py backend/tests/test_demo_store.py -v
git add backend/app/services/report_generator.py backend/app/services/llm_report_service.py backend/app/services/demo_store.py scripts/generate_reports.py backend/tests/test_generate_reports.py backend/tests/test_demo_store.py
git commit -m "feat: 完成三组织结构化报告"
```

---

### Task 7: 增加一键课程演示入口

**Files:**
- Create: `scripts/run_course_demo.py`
- Create: `backend/tests/test_run_course_demo.py`
- Modify: `config/course-demo.json`
- Modify: `docs/guides/course-demo.md`
- Modify: `README.md`

**Step 1: 写三组织端到端失败测试**

```python
def test_course_demo_builds_three_targets(tmp_path):
    summary = run_course_demo(db_path=tmp_path / "demo.db", output_dir=tmp_path / "output")
    assert summary["targets"] == ["APT28", "Kimsuky", "Lazarus"]
    assert summary["documents"] == 3
    assert summary["entities"] > 0
    assert summary["relations"] > 0
    assert summary["evidence"] > 0
    assert summary["reports"] == 3
```

**Step 2: 实现显式演示清单**

脚本只读取 `config/course-demo.json` 中第 3 节固定的三对 Document/Extraction；不使用宽 Glob 选择“最新”工件，避免误读 Candidate Audit 或历史文件。

**Step 3: 实现演示命令**

```powershell
docker compose run --rm backend python scripts/run_course_demo.py `
  --db data/course_demo.db `
  --graph-output data/graph/course-demo.graph.json `
  --reports-output data/reports/course-demo `
  --rule-reports `
  --json
```

脚本顺序固定为：初始化空库、导入三篇文档及审核 Extraction、归一化、构建行为分析、生成报告、导出 graph.json、输出摘要。

**Step 4: 验证幂等与失败边界**

- 重复执行不会重复增加实体和关系；
- 缺失任何固定工件时立即失败并指出路径；
- 不存在 API Key 时规则报告仍可完成；
- 不覆盖默认 `data/threatgraph_osint.db`。

**Step 5: 验证并提交**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_run_course_demo.py -v
docker compose run --rm backend python scripts/run_course_demo.py --db /tmp/course-demo.db --graph-output /tmp/course-demo.graph.json --reports-output /tmp/course-demo-reports --rule-reports --json
git add scripts/run_course_demo.py backend/tests/test_run_course_demo.py config/course-demo.json docs/guides/course-demo.md README.md
git commit -m "feat: 添加三组织课程演示入口"
```

---

### Task 8: 让前端展示真实分析和报告

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/AnalysisPage.tsx`
- Modify: `frontend/src/components/ReportPanel.tsx`
- Test: `frontend/src/api/client.test.ts`

**Step 1: 写空数据和真实数据测试**

扩充 API 测试，覆盖行为模式、MITRE、推断、结构化报告和请求失败；页面不得用静默 `.catch(() => {})` 把请求错误伪装成“暂无数据”。组件交互通过生产构建和 `docs/guides/course-demo.md` 中的浏览器验收步骤验证，不为本次 P0 临时引入新的前端测试框架。

**Step 2: 显示数据状态**

页面明确区分：

```text
证据事实
规则派生分析
LLM 推断候选
暂无数据
请求失败
```

**Step 3: 验证三目标切换**

APT28、Kimsuky、Lazarus 切换时重新请求 graph、analysis、report，并清除上一个目标的旧状态。

**Step 4: 验证并提交**

```powershell
docker compose run --rm --no-deps frontend npm run test -- --run
docker compose run --rm --no-deps frontend npm run build
git add frontend/src/api/client.ts frontend/src/api/client.test.ts frontend/src/pages/AnalysisPage.tsx frontend/src/components/ReportPanel.tsx
git commit -m "feat: 展示真实行为分析与报告"
```

---

### Task 9: 保留最小课程评测

**Files:**
- Create: `scripts/summarize_course_evaluation.py`
- Create: `backend/tests/test_summarize_course_evaluation.py`
- Create: `backend/app/services/evaluation_summary_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`
- Modify: `docs/reports/llm-extraction-baseline.md`
- Modify: `frontend/src/pages/EvaluationPage.tsx`
- Delete: `frontend/src/data/mockEval.ts`

**Step 1: 写聚合测试**

聚合器只读取明确传入的 Evaluation JSON，按文档汇总 TP/FP/FN，不重新解释旧文件：

```python
def test_summary_labels_dataset_as_development(evaluation_files):
    result = summarize(evaluation_files)
    assert result["dataset_role"] == "development"
    assert result["claims"] == "exploratory"
```

**Step 2: 固定最小展示字段**

只展示实体 P/R/F1、关系端到端 P/R/F1、运行成功/失败数和逐文档结果。旧评测口径必须标记为 `legacy_candidate_audit_scope`，不得声称已实现 PR #42 的 Raw/Validated 新契约。

**Step 3: 增加只读评测摘要 API**

`GET /api/v1/evaluation/summary` 通过 `EvaluationSummaryService` 读取明确配置的课程摘要文件；找不到文件时返回 `not_generated`，不扫描任意 JSON，不修改评测工件。

**Step 4: 前端移除硬编码 Mock**

Evaluation 页面只读取 `/api/v1/evaluation/summary`；没有结果时显示“尚未生成”，不展示虚构百分比。

**Step 5: 验证并提交**

```powershell
docker compose run --rm backend python -m pytest backend/tests/test_summarize_course_evaluation.py backend/tests/test_api.py -v
docker compose run --rm --no-deps frontend npm run test -- --run
git add scripts/summarize_course_evaluation.py backend/tests/test_summarize_course_evaluation.py backend/app/services/evaluation_summary_service.py backend/app/main.py backend/tests/test_api.py docs/reports/llm-extraction-baseline.md frontend/src/pages/EvaluationPage.tsx frontend/src/data/mockEval.ts
git commit -m "feat: 收敛课程开发集评测展示"
```

---

### Task 10: 准备答辩材料和验收记录

**Files:**
- Create: `docs/reports/course-acceptance-record.md`
- Create: `docs/guides/course-demo-script.md`
- Modify: `TODO.md`

**Step 1: 记录验收矩阵**

逐项映射课程要求、实现入口、演示动作、截图/录像时间点和已知限制。

**Step 2: 写 20 分钟演示脚本**

建议时间：

```text
2 分钟：课程目标与架构
3 分钟：三类来源采集、清洗和中英文数据
4 分钟：LLM NER/RE、Candidate Audit 和证据
4 分钟：图谱、多维查询和路径追踪
3 分钟：行为、MITRE 和推断边界
2 分钟：三组织结构化报告
1 分钟：开发集评测
1 分钟：开源项目对比、创新和限制
```

**Step 3: 记录降级路径**

在线采集或 LLM 不可用时，使用固定审核工件运行 `run_course_demo.py`；不得把缓存演示说成现场实时采集。

**Step 4: 更新 TODO**

只有实际执行并留下验证证据的项目才能标为完成；代码存在但未演示的项目标为“代码已实现，待集成验收”。

**Step 5: Commit**

```powershell
git add docs/reports/course-acceptance-record.md docs/guides/course-demo-script.md TODO.md
git commit -m "docs: 添加课程验收与演示脚本"
```

---

### Task 11: 最终全量验证

**Files:**
- Verify: `backend/`
- Verify: `frontend/`
- Verify: `scripts/`
- Verify: `docs/`
- Verify: `data/documents/`
- Verify: fixed demo artifacts from section 3

**Step 1: 后端全量测试**

```powershell
docker compose run --rm backend python -m pytest backend/tests -v
```

Expected: 0 failed。

**Step 2: 前端测试、构建和格式检查**

```powershell
docker compose run --rm --no-deps frontend npm run test -- --run
docker compose run --rm --no-deps frontend npm run build
docker compose run --rm --no-deps frontend npm run format:check
```

Expected: 0 failed；包体积 warning 可以记录，但不阻塞 P0。

**Step 3: 三类来源覆盖检查**

```powershell
docker compose run --rm backend python scripts/verify_course_source_coverage.py --input data/documents --json
```

Expected: 三组织、三来源类型、中文和英文均有非零数量，0 个 Schema/哈希错误。

**Step 4: 三组织离线演示**

```powershell
docker compose run --rm backend python scripts/run_course_demo.py --db /tmp/course-demo.db --graph-output /tmp/course-demo.graph.json --reports-output /tmp/course-demo-reports --rule-reports --json
```

Expected: 3 个目标组织、3 篇主文档、非零实体/关系/证据/行为记录、3 份五章节报告。

**Step 5: 文档和 Git 检查**

```powershell
git diff --check origin/main...HEAD
git status --short
git log --format='%h author=%an <%ae> | committer=%cn <%ce>' origin/main..HEAD
```

Expected: 无空白错误、无未提交文件、作者和共同作者归属符合团队约定。

## 5. 实施顺序与停止规则

严格按以下顺序推进：

```text
Task 1 路线纠偏
→ Task 2 已合入 Pipeline 验收
→ Task 3 三类来源验收
→ Task 4-6 MITRE、分析 API、报告收口
→ Task 7-8 三组织演示与前端
→ Task 9 最小评测
→ Task 10-11 答辩材料与全量验证
```

如果课程时间不足，先停止 Task 9 的新代码，直接使用现有评测 JSON 和报告中的局限说明；不得牺牲三类来源、三组织图谱、行为/MITRE 或结构化报告来建设更完整的评测平台。
