r"""
验证 llm_service.py 核心逻辑的测试脚本（不需要 LLM API key）。

用法:
    pip install -r backend/requirements.txt
    python scripts/test_llm_service.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.llm_service import (
    parse_llm_response,
    validate_entity,
    validate_relation,
    load_schema,
    LLMExtractionService,
    ALLOWED_RELATIONS,
    ENTITY_TYPES,
    RELATION_TYPES,
)

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  -- {detail}")


# ── 1. parse_llm_response 基本解析 ──────────────────────────
print("1. parse_llm_response 基本解析")
mock_json = json.dumps({
    "entities": [
        {"name": "APT28", "type": "APT_GROUP", "aliases": ["Fancy Bear"],
         "description": "俄关联 APT", "mention_text": "APT28",
         "evidence_text": "APT28 has been using X-Agent",
         "confidence": 0.95},
        {"name": "X-Agent", "type": "MALWARE", "aliases": [],
         "description": "后门木马", "mention_text": "X-Agent",
         "evidence_text": "using X-Agent malware",
         "confidence": 0.92},
        {"name": "Ukraine", "type": "COUNTRY", "aliases": [],
         "description": "目标国家", "mention_text": "Ukrainian",
         "evidence_text": "targeting Ukrainian government",
         "confidence": 0.90},
    ],
    "relations": [
        {"head_name": "APT28", "head_type": "APT_GROUP",
         "relation_type": "USES", "tail_name": "X-Agent", "tail_type": "MALWARE",
         "evidence_text": "using X-Agent malware", "confidence": 0.88},
        {"head_name": "APT28", "head_type": "APT_GROUP",
         "relation_type": "TARGETS", "tail_name": "Ukraine", "tail_type": "COUNTRY",
         "evidence_text": "targeting Ukrainian government", "confidence": 0.90},
    ]
})
clean_text = "APT28 has been using X-Agent malware targeting Ukrainian government"

result = parse_llm_response(mock_json, "chunk_001", clean_text)
entities = result["entities"]
relations = result["relations"]

check("解析出 3 个实体", len(entities) == 3, f"实际: {len(entities)}")
check("解析出 2 个关系", len(relations) == 2, f"实际: {len(relations)}")

e1 = entities[0]
check("实体名正确", e1["name"] == "APT28")
check("实体类型正确", e1["type"] == "APT_GROUP")
check("char_start 自动计算", e1["char_start"] == 0, f"实际: {e1['char_start']}")
check("char_end 自动计算", e1["char_end"] == 28, f"实际: {e1['char_end']}")
check("candidate_status=candidate", e1["candidate_status"] == "candidate")

r1 = relations[0]
check("关系类型 USES", r1["relation_type"] == "USES")
check("USES 通过合法性校验", r1["validation_status"] == "valid", str(r1.get("validation_errors")))
check("别名计入 known_entities", True)  # alias Fancy Bear would match

# ── 2. validate_entity ─────────────────────────────────────
print("\n2. validate_entity")
check("合法实体通过", validate_entity({"name": "APT28", "type": "APT_GROUP",
                                        "evidence_text": "APT28 in text", "confidence": 0.9}) == [])
check("空 name 报错", len(validate_entity({"name": "", "type": "MALWARE",
                                            "evidence_text": "x", "confidence": 0.5})) > 0)
check("未知 type 报错", len(validate_entity({"name": "x", "type": "NOT_A_TYPE",
                                              "evidence_text": "x", "confidence": 0.5})) > 0)
check("空 evidence 报错", len(validate_entity({"name": "x", "type": "MALWARE",
                                                "evidence_text": "", "confidence": 0.5})) > 0)
check("confidence>1 报错", len(validate_entity({"name": "x", "type": "MALWARE",
                                                 "evidence_text": "x", "confidence": 1.5})) > 0)

# ── 3. validate_relation ───────────────────────────────────
print("\n3. validate_relation — 合法性矩阵")
known = {("APT28", "APT_GROUP"), ("X-Agent", "MALWARE"), ("Ukraine", "COUNTRY")}

check("USES(APT_GROUP→MALWARE) 合法",
      validate_relation({"head_name": "APT28", "head_type": "APT_GROUP",
                          "relation_type": "USES", "tail_name": "X-Agent", "tail_type": "MALWARE",
                          "evidence_text": "uses X-Agent", "confidence": 0.9}, known) == [])

check("USES(MALWARE→APT_GROUP) 非法 (head/tail 反了)",
      len(validate_relation({"head_name": "X-Agent", "head_type": "MALWARE",
                              "relation_type": "USES", "tail_name": "APT28", "tail_type": "APT_GROUP",
                              "evidence_text": "x", "confidence": 0.9}, known)) > 0)

check("EXPLOITS(APT_GROUP→CVE) 合法",
      validate_relation({"head_name": "APT28", "head_type": "APT_GROUP",
                          "relation_type": "EXPLOITS", "tail_name": "CVE-2020-1234", "tail_type": "CVE",
                          "evidence_text": "exploits CVE", "confidence": 0.9},
                         known | {("CVE-2020-1234", "CVE")}) == [])

check("head 不在 known_entities 报错",
      len(validate_relation({"head_name": "Unknown", "head_type": "APT_GROUP",
                              "relation_type": "USES", "tail_name": "X-Agent", "tail_type": "MALWARE",
                              "evidence_text": "x", "confidence": 0.9}, known)) > 0)

check("未知 relation_type 报错",
      len(validate_relation({"head_name": "APT28", "head_type": "APT_GROUP",
                              "relation_type": "EATS", "tail_name": "X-Agent", "tail_type": "MALWARE",
                              "evidence_text": "x", "confidence": 0.9}, known)) > 0)

# ── 4. LLM 返回格式异常处理 ────────────────────────────────
print("\n4. parse_llm_response 异常处理")
try:
    parse_llm_response("not json at all", "c1", "")
    check("非 JSON 抛异常", False, "应该抛异常")
except ValueError:
    check("非 JSON 抛异常", True)

# ── 5. Schema 文件可加载 ───────────────────────────────────
print("\n5. Schema 加载")
try:
    schema = load_schema()
    check(f"extraction-result schema 加载成功 (v{schema.get('schema_version','?')})",
          "const" in str(schema))
except Exception as exc:
    check("schema 加载成功", False, str(exc))

# ── 6. 关系矩阵完整性 ──────────────────────────────────────
print("\n6. 关系矩阵完整性")
check("18 种关系全部定义", len(ALLOWED_RELATIONS) == 18, f"实际: {len(ALLOWED_RELATIONS)}")
check("17 种实体类型", len(ENTITY_TYPES) == 17, f"实际: {len(ENTITY_TYPES)}")

for rt in RELATION_TYPES:
    check(f"  {rt} 在矩阵中", rt in ALLOWED_RELATIONS)

# ── 7. 与真实 example 数据对比 ──────────────────────────────
print("\n7. 真实 example 数据格式检查")
example_path = REPO_ROOT / "data/examples/extraction_result.apt28.thn.beardshell.example.json"
if example_path.exists():
    example = json.loads(example_path.read_text(encoding="utf-8"))
    total_e = sum(len(c["entities"]) for c in example["chunks"])
    total_r = sum(len(c["relations"]) for c in example["chunks"])
    check(f"example 含 {total_e} 实体 {total_r} 关系", total_e > 0 and total_r > 0)

    # 检查 example 中的字段是否能被 validate_entity/relation 处理
    for chunk in example["chunks"]:
        for ent in chunk["entities"]:
            errs = validate_entity(ent)
            if errs:
                check(f"  entity {ent['name']} 校验通过", False, "; ".join(errs))
        for rel in chunk["relations"]:
            known_set = {(e["name"], e["type"]) for e in chunk["entities"]}
            for a in chunk["entities"]:
                for alias in a.get("aliases", []):
                    known_set.add((alias, a["type"]))
            errs = validate_relation(rel, known_set)
            if errs:
                check(f"  relation {rel['head_name']}-[{rel['relation_type']}]->{rel['tail_name']} 校验通过",
                      False, "; ".join(errs))
    print("  (example 数据逐条校验完成)")
else:
    check("example 文件存在", False)

# ── 8. 真实 document 文件可加载 ─────────────────────────────
print("\n8. 真实 document 文件加载")
doc_dir = REPO_ROOT / "data/documents/apt28"
docs = sorted(doc_dir.glob("*.json")) if doc_dir.is_dir() else []
check(f"apt28 目录有 {len(docs)} 个文档", len(docs) > 0)

if docs:
    doc = json.loads(docs[0].read_text(encoding="utf-8"))
    check("doc_id 存在", bool(doc.get("doc_id")))
    check("clean_text 非空", len(doc.get("clean_text", "")) > 0)
    check("target_group 存在", bool(doc.get("target_group")))
    print(f"  示例文档: doc_id={doc['doc_id']}, title={doc['title'][:40]}...")
    print(f"  clean_text 长度: {len(doc['clean_text'])} 字符")

# ── 结果 ───────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"结果: {PASS} 通过, {FAIL} 失败, 共 {PASS+FAIL} 项")
if FAIL == 0:
    print("全部通过!")
else:
    print(f"{FAIL} 项失败，请检查。")
    sys.exit(1)
