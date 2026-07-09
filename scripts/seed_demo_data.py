from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.demo_store import DEFAULT_DB_PATH, DemoStore


def seed_demo_data(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    store = DemoStore(db_path)
    store.seed_demo_data()
    return store.db_path


if __name__ == "__main__":
    path = seed_demo_data()
    print(f"已初始化演示数据库：{path}")
