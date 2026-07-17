# 单条攻击链叙事实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将智能报告第六章节改为按时间合并的单条攻击链叙事，不再展示结构化路径分解表，并约束 LLM 只能使用图谱中已有数据。

**Architecture:** 后端从关系表按时间和目标组织聚合 `EXPLOITS`、`USES`、`TARGETS` 关系，生成可供 LLM 核验的攻击事件摘要；LLM prompt 明确禁止编造未知信息。规则降级模式使用同一聚合结果生成叙事文本。前端只渲染第六章节 markdown，移除结构化攻击链表格和专用字段类型。

**Tech Stack:** FastAPI、SQLite、Python、React、TypeScript、Vitest/Pytest。

---

### Task 1: 固化单条攻击链聚合行为

**Files:**
- Modify: `backend/app/services/llm_report_service.py`
- Test: `backend/tests/test_llm_report_service.py`

- [ ] **Step 1: 写失败测试**

增加测试数据：同一组织在同一时间存在 `EXPLOITS`、多个 `USES`、多个 `TARGETS` 关系，断言 `_build_prompt("APT28")` 中同一时间只生成一组聚合事件，并包含漏洞、工具和目标名称。

```python
def test_attack_chain_prompt_groups_relations_by_time(tmp_path):
    # 创建与生产库一致的最小 entities/relations/evidence 表
    # 插入 APT28、CVE、BEARDSHELL、COVENANT、乌克兰政府机构
    # 插入同一 first_seen 的 EXPLOITS/USES/TARGETS 关系
    prompt = LLMReportService(db_path=tmp_path / "graph.db")._build_prompt("APT28")
    assert "2025-06-24" in prompt
    assert "CVE-2021-44026" in prompt
    assert "BEARDSHELL、COVENANT" in prompt or "COVENANT、BEARDSHELL" in prompt
    assert "乌克兰政府机构" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_llm_report_service.py::test_attack_chain_prompt_groups_relations_by_time -q`

Expected: FAIL，因为当前 prompt 仍按关系逐条传递，未提供按时间聚合的事件文本。

- [ ] **Step 3: 实现最小聚合函数**

在 `llm_report_service.py` 增加单一职责函数：按 `(first_seen or last_seen or "未知", source_name)` 分组，只将关系类型分别归入漏洞、工具/恶意软件、技术、目标和其他关系；输出格式为：

```text
- 2025-06-24：APT28 利用 CVE-2021-44026，使用 BEARDSHELL、COVENANT，针对乌克兰政府机构发起活动。
```

所有空集合写“未知”，不从实体名称推断未出现的关系。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest backend/tests/test_llm_report_service.py::test_attack_chain_prompt_groups_relations_by_time -q`

Expected: PASS。

### Task 2: 加强 LLM 约束并修正降级分支

**Files:**
- Modify: `backend/app/services/llm_report_service.py`
- Modify: `backend/app/services/report_generator.py`
- Test: `backend/tests/test_llm_report_service.py`

- [ ] **Step 1: 写失败测试**

增加断言，要求 prompt 包含以下约束：只能引用图谱数据、未知字段必须写“未知”、不能把推断写成事实、不能补造时间/漏洞/工具/目标；同时测试 `_parse_sections` 仍返回 6 个章节。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest backend/tests/test_llm_report_service.py -q`

Expected: 新增约束断言失败。

- [ ] **Step 3: 修改 prompt 和异常处理**

将 `attack_chain` prompt 改为只要求生成单条时间合并叙事，不再要求表格；补充证据边界约束。保留 LLM 失败降级，但确保 `result = _fallback_generate(...)` 在异常分支中先创建，再设置 `_llm_generated = False`。同时保留当前诊断日志直到用户确认问题已解决。

- [ ] **Step 4: 实现规则降级单条叙事**

在 `report_generator.py` 用同一聚合逻辑生成第六章节 markdown：每个时间事件一行，格式为 `时间：APT 组织利用漏洞，使用工具，针对目标发起活动。`，不生成结构化表格，不设置 `attack_chains` 表格数据。

- [ ] **Step 5: 运行后端测试**

Run: `python -m pytest backend/tests/test_llm_report_service.py backend/tests/test_api.py -q`

Expected: 全部通过。

### Task 3: 前端仅保留攻击链叙事

**Files:**
- Modify: `frontend/src/components/ReportPanel.tsx`
- Modify: `frontend/src/types.ts`
- Test: `frontend/src/App.test.tsx` 或新增 `frontend/src/components/ReportPanel.test.tsx`

- [ ] **Step 1: 写失败测试**

渲染含 `attack_chain` 章节的报告，断言正文可见，且不会出现“结构化路径分解”“阶段/关系”“工具/恶意软件”等表格标题。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm --prefix frontend run test -- --run`

Expected: 当前攻击链表格仍被渲染时断言失败或测试无法通过。

- [ ] **Step 3: 删除表格渲染逻辑**

从 `ReportPanel.tsx` 删除 `AttackChainTable`、对应 import 和 `current.section_type === "attack_chain"` 的表格分支；保留章节图标和 markdown 正文渲染。`ReportSection.graph_refs` 恢复为兼容现有数据的 `Record<string, unknown>`，不再依赖 `AttackChainStep`。

- [ ] **Step 4: 运行前端构建与测试**

Run: `npm --prefix frontend run build`

Expected: TypeScript 编译和 Vite 构建通过。测试如受 Windows 中文路径 worker 超时影响，单独运行新增测试并记录全量测试限制。

### Task 4: 清理旧报告并验证实际生成链路

**Files:**
- Modify: `backend/app/services/llm_report_service.py`（仅在验证完成后移除本次调试 instrumentation）
- Delete: `debug-report-llm-fallback.md`（用户确认修复后）
- Runtime: SQLite 中 APT28 旧报告缓存

- [ ] **Step 1: 运行静态检查和专项测试**

Run: `python -m py_compile backend/app/services/llm_report_service.py backend/app/services/report_generator.py`

Run: `python -m pytest backend/tests/test_llm_report_service.py backend/tests/test_api.py -q`

Run: `npm --prefix frontend run build`

- [ ] **Step 2: 清理 APT28 旧缓存**

```powershell
python -c "import sqlite3; c=sqlite3.connect('data/threatgraph_osint.db'); c.execute(\"DELETE FROM report_sections WHERE report_id LIKE '%apt28%'\"); c.execute(\"DELETE FROM reports WHERE lower(target_group)='apt28'\"); c.commit(); c.close()"
```

- [ ] **Step 3: 使用 8000 端口重新启动服务并生成报告**

```powershell
$env:LLM_API_KEY="新API Key"
$env:LLM_BASE_URL="https://api.deepseek.com"
$env:LLM_MODEL="deepseek-v4-flash"
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

确认响应第六章节只包含时间合并叙事，不包含结构化路径表。

- [ ] **Step 4: 记录验证结论**

检查报告中每个时间事件是否只使用图谱已有关系，并确认无漏洞/工具/目标时显示“未知”。
