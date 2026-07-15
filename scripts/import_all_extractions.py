"""将已完成的抽取结果导入 SQLite 正式图谱。

用法: python scripts/import_all_extractions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.demo_store import DEFAULT_DB_PATH
from backend.app.services.offline_extraction_pipeline import OfflineExtractionPipeline
from scripts.export_graph_json import DEFAULT_OUTPUT_PATH, export_graph_json

# 6 组已完成的抽取结果
EXTRACTION_RUNS = [
    {
        "document": "data/documents/apt28/apt28_080.json",
        "result": "data/extracted/extract_apt28_080_extract-v1_20260714T163726412208.json",
    },
    {
        "document": "data/documents/kimsuky/kimsuky_060.json",
        "result": "data/extracted/extract_kimsuky_060_extract-v1_20260714T163842839422.json",
    },
    {
        "document": "data/documents/lazarus/lazarus_091.json",
        "result": "data/extracted/extract_lazarus_091_extract-v1_20260714T163916553583.json",
    },
    {
        "document": "data/documents/apt28/apt28_001.json",
        "result": "data/extracted/extract_apt28_001_extract-v1_20260714T164000284656.json",
    },
    {
        "document": "data/documents/kimsuky/kimsuky_001.json",
        "result": "data/extracted/extract_kimsuky_001_extract-v1_20260714T164031740094.json",
    },
    {
        "document": "data/documents/lazarus/lazarus_001.json",
        "result": "data/extracted/extract_lazarus_001_extract-v1_20260714T164111452509.json",
    },
]

pipeline = OfflineExtractionPipeline(DEFAULT_DB_PATH)

for i, run in enumerate(EXTRACTION_RUNS, 1):
    doc_path = Path(run["document"])
    result_path = Path(run["result"])
    print(f"[{i}/6] 导入: {doc_path.name} ...")
    summary = pipeline.run(str(doc_path), str(result_path))
    print(
        f"  实体={summary.canonical_entities}, "
        f"关系={summary.canonical_relations}, "
        f"证据={summary.evidence}"
    )

print()
print("所有抽取结果已导入 SQLite。")

# 导出 graph.json
print("导出 graph.json ...")
graph_path = export_graph_json(DEFAULT_DB_PATH, DEFAULT_OUTPUT_PATH, seed_demo=False)
print(f"图谱已导出: {graph_path}")
