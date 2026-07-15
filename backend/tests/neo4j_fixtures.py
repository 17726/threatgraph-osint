import sqlite3
from pathlib import Path

from backend.app.services.demo_store import DemoStore


def seed_canonical_graph(db_path: Path) -> None:
    DemoStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """INSERT INTO entities (
                 entity_id, name, type, aliases_json, description,
                 confidence, source_count, tags_json
               ) VALUES (?, ?, ?, '[]', '', 0.9, 1, '[]')""",
            ("apt_group:apt28", "APT28", "APT_GROUP"),
        )
        connection.execute(
            """INSERT INTO entities (
                 entity_id, name, type, aliases_json, description,
                 confidence, source_count, tags_json
               ) VALUES (?, ?, ?, '[]', '', 0.8, 1, '[]')""",
            ("malware:x-agent", "X-Agent", "MALWARE"),
        )
        connection.execute(
            """INSERT INTO relations (
                 relation_id, source_entity_id, target_entity_id,
                 relation_type, label, confidence, source_count,
                 evidence_count, validation_status
               ) VALUES (?, ?, ?, 'USES', '使用', 0.85, 1, 1, 'valid')""",
            (
                "rel:apt_group:apt28:USES:malware:x-agent",
                "apt_group:apt28",
                "malware:x-agent",
            ),
        )
        connection.execute(
            """INSERT INTO evidence (
                 evidence_id, doc_id, relation_id, evidence_text,
                 source_url, source_type, source_name, evidence_type,
                 source_reliability, language
               ) VALUES (?, 'doc-1', ?, 'APT28 uses X-Agent.',
                         'https://example.test', 'vendor_report', 'Example',
                         'direct_quote', 'B', 'en')""",
            (
                "ev-1",
                "rel:apt_group:apt28:USES:malware:x-agent",
            ),
        )
