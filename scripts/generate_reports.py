"""为图谱中所有目标组织生成智能分析报告并写入 SQLite。

用法:
  python scripts/generate_reports.py                           # 默认（LLM 驱动）
  python scripts/generate_reports.py --rule                    # 强制使用规则模板
  python scripts/generate_reports.py --graph-version my-v1     # 自定义版本标签
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.demo_store import DEFAULT_DB_PATH
from backend.app.services.report_generator import generate_intelligent_report

TARGET_GROUPS = ["APT28", "Kimsuky", "Lazarus"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="为图谱中所有目标组织生成智能分析报告并写入 SQLite。"
    )
    parser.add_argument(
        "--rule",
        action="store_true",
        help="强制使用规则模板生成，不调用 LLM",
    )
    parser.add_argument(
        "--graph-version",
        default="llm-v1",
        help="报告版本标签（默认: llm-v1）",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(DEFAULT_DB_PATH),
        help="SQLite 数据库路径",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果摘要",
    )
    return parser


def generate_reports(
    db_path: Path = Path(DEFAULT_DB_PATH),
    graph_version: str = "llm-v1",
    force_rule: bool = False,
) -> list[dict[str, object]]:
    """生成所有目标组织的报告并写入 SQLite。"""
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    results: list[dict[str, object]] = []

    for target in TARGET_GROUPS:
        entity_id = f"apt_group:{target.lower()}"
        exists = conn.execute(
            "SELECT entity_id FROM entities WHERE entity_id = ?", (entity_id,)
        ).fetchone()

        if not exists:
            alt = conn.execute(
                "SELECT entity_id, name FROM entities WHERE name = ? AND type = 'APT_GROUP'",
                (target,),
            ).fetchone()
            if alt:
                entity_id = alt["entity_id"]
            else:
                results.append({"target": target, "status": "skipped", "reason": "未找到"})
                continue

        result = generate_intelligent_report(conn, target, entity_id)
        now_iso = datetime.now(UTC).isoformat()
        report_id = f"report_{target.lower()}_intelligent"
        title = f"{target} 威胁情报分析报告"

        conn.execute(
            """INSERT OR REPLACE INTO reports
               (report_id, target_group, title, markdown, generated_at, graph_version)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (report_id, target, title, result["markdown"], now_iso, graph_version),
        )

        sections_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='report_sections'"
        ).fetchone()
        if sections_table:
            conn.execute("DELETE FROM report_sections WHERE report_id = ?", (report_id,))
            for sec in result["sections"]:
                sid = f"{report_id}_{sec['section_type']}"
                conn.execute(
                    """INSERT INTO report_sections
                       (section_id, report_id, section_type, title, markdown,
                        evidence_ids_json, analysis_refs_json, graph_refs_json, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sid,
                        report_id,
                        sec["section_type"],
                        sec["title"],
                        sec["markdown"],
                        json.dumps(sec["evidence_ids"], ensure_ascii=False),
                        json.dumps(sec["analysis_refs"], ensure_ascii=False),
                        json.dumps(sec["graph_refs"], ensure_ascii=False),
                        sec["sort_order"],
                    ),
                )

        conn.commit()
        summary = {
            "target": target,
            "status": "generated",
            "sections": len(result["sections"]),
            "chars": len(result["markdown"]),
            "graph_version": graph_version,
        }
        results.append(summary)

    conn.close()
    return results


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        results = generate_reports(args.db, args.graph_version, args.rule)
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r["status"] == "generated":
                print(
                    f"{r['target']}: 报告已生成, "
                    f"章节={r['sections']}, "
                    f"markdown={r['chars']} 字符, "
                    f"version={r['graph_version']}"
                )
            else:
                print(f"{r['target']}: {r['reason']}")
        print(f"\n共处理 {len(results)} 个目标")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
