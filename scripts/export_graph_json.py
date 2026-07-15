import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.demo_store import DEFAULT_DB_PATH, DemoStore


DEFAULT_OUTPUT_PATH = Path("data/graph/graph.json")


def export_graph_json(
    db_path: str | Path = DEFAULT_DB_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    store = DemoStore(db_path, seed_demo=False)
    graph = store.get_graph()
    payload = {
        "version": "2.0",
        "schema_version": graph["schema_version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "exported_from": "sqlite",
        "source_of_truth": str(db_path),
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "evidence": graph["evidence"],
        "analysis": store.get_analysis(),
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    path = export_graph_json()
    print(f"已导出图谱快照：{path}")
