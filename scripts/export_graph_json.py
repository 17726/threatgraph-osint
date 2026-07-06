import json
from datetime import UTC, datetime
from pathlib import Path

from backend.app.services.demo_store import DEFAULT_DB_PATH, DemoStore


DEFAULT_OUTPUT_PATH = Path("data/graph/graph.json")


def export_graph_json(
    db_path: str | Path = DEFAULT_DB_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    graph = DemoStore(db_path).get_graph()
    payload = {
        "version": "2.0",
        "schema_version": graph["schema_version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "exported_from": "sqlite",
        "source_of_truth": str(db_path),
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "evidence": graph["evidence"],
        "analysis": {
            "mitre_mappings": [
                {
                    "mapping_id": "mitre_apt28_t1566",
                    "target_group": "APT28",
                    "technique_id": "T1566",
                    "technique_name": "Phishing",
                    "tactic": "Initial Access",
                    "attack_stage": "初始访问",
                    "confidence": 0.9,
                    "evidence_ids": ["ev_apt28_t1566_001"],
                }
            ],
            "behavior_patterns": [
                {
                    "pattern_id": "pattern_apt28_initial_access",
                    "target_group": "APT28",
                    "stage": "初始访问",
                    "description": "APT28 常通过鱼叉式钓鱼相关技术获得初始访问。",
                    "technique_ids": ["T1566"],
                    "evidence_ids": ["ev_apt28_t1566_001"],
                    "confidence": 0.88,
                }
            ],
            "inferred_relations": [],
        },
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    path = export_graph_json()
    print(f"已导出图谱快照：{path}")
