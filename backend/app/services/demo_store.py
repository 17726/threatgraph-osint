import json
import os
import sqlite3
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.db.schema import ensure_import_compatible_columns
from backend.app.services.report_generator import generate_intelligent_report


DEFAULT_DB_PATH = Path("data/threatgraph_osint.db")


DEMO_ENTITIES = [
    {
        "entity_id": "apt_group:apt28",
        "name": "APT28",
        "type": "APT_GROUP",
        "aliases": ["Fancy Bear", "Sofacy", "Sednit"],
        "description": "APT28 是长期活跃的高级持续性威胁组织，常被公开报告关联到政府和军事目标攻击。",
        "confidence": 0.95,
        "source_count": 3,
        "first_seen": "2014-01-01",
        "last_seen": "2026-07-01",
        "tags": ["apt", "mitre", "security_report"],
    },
    {
        "entity_id": "technique:t1566",
        "name": "Phishing",
        "type": "TECHNIQUE",
        "aliases": ["Spearphishing"],
        "description": "MITRE ATT&CK T1566，常用于初始访问阶段。",
        "confidence": 0.9,
        "source_count": 2,
        "first_seen": "2015-01-01",
        "last_seen": "2026-07-01",
        "tags": ["mitre", "technique"],
    },
    {
        "entity_id": "malware:x-agent",
        "name": "X-Agent",
        "type": "MALWARE",
        "aliases": ["CHOPSTICK"],
        "description": "公开威胁报告中多次提到的 APT28 相关恶意软件家族。",
        "confidence": 0.88,
        "source_count": 2,
        "first_seen": "2015-01-01",
        "last_seen": "2024-12-31",
        "tags": ["malware", "security_report"],
    },
    {
        "entity_id": "organization:government-organizations",
        "name": "Government Organizations",
        "type": "ORGANIZATION",
        "aliases": ["政府机构"],
        "description": "APT 活动中常见的高价值目标类别。",
        "confidence": 0.84,
        "source_count": 2,
        "first_seen": "2014-01-01",
        "last_seen": "2026-07-01",
        "tags": ["target", "organization"],
    },
    {
        "entity_id": "apt_group:lazarus",
        "name": "Lazarus",
        "type": "APT_GROUP",
        "aliases": ["Hidden Cobra"],
        "description": "公开报告中常与加密货币盗窃和金融目标攻击相关联的威胁组织。",
        "confidence": 0.92,
        "source_count": 2,
        "first_seen": "2009-01-01",
        "last_seen": "2026-07-01",
        "tags": ["apt", "security_report"],
    },
    {
        "entity_id": "apt_group:kimsuky",
        "name": "Kimsuky",
        "type": "APT_GROUP",
        "aliases": ["Velvet Chollima"],
        "description": "公开报告中常与情报收集和鱼叉式钓鱼活动相关联的威胁组织。",
        "confidence": 0.9,
        "source_count": 2,
        "first_seen": "2012-01-01",
        "last_seen": "2026-07-01",
        "tags": ["apt", "security_report"],
    },
]


DEMO_RELATIONS = [
    {
        "relation_id": "rel:apt_group:apt28:USES:technique:t1566",
        "source_entity_id": "apt_group:apt28",
        "target_entity_id": "technique:t1566",
        "relation_type": "USES",
        "label": "使用",
        "confidence": 0.9,
        "source_count": 2,
        "evidence_count": 1,
        "first_seen": "2015-01-01",
        "last_seen": "2026-07-01",
        "validation_status": "valid",
    },
    {
        "relation_id": "rel:apt_group:apt28:USES:malware:x-agent",
        "source_entity_id": "apt_group:apt28",
        "target_entity_id": "malware:x-agent",
        "relation_type": "USES",
        "label": "使用",
        "confidence": 0.88,
        "source_count": 2,
        "evidence_count": 1,
        "first_seen": "2015-01-01",
        "last_seen": "2024-12-31",
        "validation_status": "valid",
    },
    {
        "relation_id": "rel:apt_group:apt28:TARGETS:organization:government-organizations",
        "source_entity_id": "apt_group:apt28",
        "target_entity_id": "organization:government-organizations",
        "relation_type": "TARGETS",
        "label": "攻击目标",
        "confidence": 0.84,
        "source_count": 2,
        "evidence_count": 0,
        "first_seen": "2014-01-01",
        "last_seen": "2026-07-01",
        "validation_status": "valid",
    },
]


DEMO_EVIDENCE = [
    {
        "evidence_id": "ev_apt28_profile_001",
        "doc_id": "apt28_demo_001",
        "chunk_id": "apt28_demo_001_c001",
        "entity_id": "apt_group:apt28",
        "relation_id": None,
        "evidence_text": "公开知识库（如 MITRE ATT&CK）将 APT28 描述为长期活跃并偏好政府、军事等高价值目标的威胁组织。",
        "source_url": "https://attack.mitre.org/groups/G0007/",
        "source_type": "knowledge_base",
        "source_name": "MITRE ATT&CK",
        "evidence_type": "summary",
        "quote_start": None,
        "quote_end": None,
        "published_at": None,
        "retrieved_at": "2026-07-07T00:00:00+08:00",
        "source_reliability": "A",
        "language": "zh",
    },
    {
        "evidence_id": "ev_apt28_t1566_001",
        "doc_id": "apt28_demo_002",
        "chunk_id": "apt28_demo_002_c001",
        "entity_id": "technique:t1566",
        "relation_id": "rel:apt_group:apt28:USES:technique:t1566",
        "evidence_text": "APT28 相关攻击活动经常通过鱼叉式钓鱼邮件获得初始访问。",
        "source_url": "https://attack.mitre.org/techniques/T1566/",
        "source_type": "knowledge_base",
        "source_name": "MITRE ATT&CK",
        "evidence_type": "summary",
        "quote_start": None,
        "quote_end": None,
        "published_at": None,
        "retrieved_at": "2026-07-07T00:00:00+08:00",
        "source_reliability": "A",
        "language": "zh",
    },
    {
        "evidence_id": "ev_apt28_xagent_001",
        "doc_id": "apt28_demo_003",
        "chunk_id": "apt28_demo_003_c001",
        "entity_id": "malware:x-agent",
        "relation_id": "rel:apt_group:apt28:USES:malware:x-agent",
        "evidence_text": "公开报告中多次出现 APT28 使用 X-Agent 恶意软件的描述。",
        "source_url": "https://attack.mitre.org/software/",
        "source_type": "knowledge_base",
        "source_name": "MITRE ATT&CK",
        "evidence_type": "summary",
        "quote_start": None,
        "quote_end": None,
        "published_at": None,
        "retrieved_at": "2026-07-07T00:00:00+08:00",
        "source_reliability": "A",
        "language": "zh",
    },
]



DEMO_MITRE_MAPPINGS = [
    {
        "mapping_id": "mitre_apt28_t1566",
        "target_group": "APT28",
        "technique_id": "T1566",
        "technique_name": "Phishing",
        "tactic": "Initial Access",
        "attack_stage": "\u521d\u59cb\u8bbf\u95ee",
        "entity_id": "technique:t1566",
        "relation_id": "rel:apt_group:apt28:USES:technique:t1566",
        "evidence_ids_json": "[\"ev_apt28_t1566_001\"]",
        "confidence": 0.9,
        "source": "manual",
        "created_at": "2026-07-15T00:00:00+08:00",
    },
    {
        "mapping_id": "mitre_apt28_t1059",
        "target_group": "APT28",
        "technique_id": "T1059",
        "technique_name": "Command and Scripting Interpreter",
        "tactic": "Execution",
        "attack_stage": "\u6267\u884c",
        "entity_id": "technique:t1059",
        "relation_id": "rel:apt_group:apt28:USES:technique:t1059",
        "evidence_ids_json": "[]",
        "confidence": 0.85,
        "source": "rule",
        "created_at": "2026-07-15T00:00:00+08:00",
    },
]


DEMO_BEHAVIOR_PATTERNS = [
    {
        "pattern_id": "pattern_apt28_initial_access",
        "target_group": "APT28",
        "stage": "\u521d\u59cb\u8bbf\u95ee",
        "description": "APT28 \u5e38\u901a\u8fc7\u9c7c\u53c9\u5f0f\u9493\u9c7c\u83b7\u5f97\u521d\u59cb\u8bbf\u95ee\u3002",
        "technique_ids_json": "[\"T1566\"]",
        "relation_ids_json": "[\"rel:apt_group:apt28:USES:technique:t1566\"]",
        "evidence_ids_json": "[\"ev_apt28_t1566_001\"]",
        "confidence": 0.88,
        "created_at": "2026-07-15T00:00:00+08:00",
    },
    {
        "pattern_id": "pattern_apt28_execution",
        "target_group": "APT28",
        "stage": "\u6267\u884c",
        "description": "APT28 \u4f7f\u7528\u811a\u672c\u89e3\u91ca\u5668\u6267\u884c\u6076\u610f\u4ee3\u7801\u3002",
        "technique_ids_json": "[\"T1059\"]",
        "relation_ids_json": "[\"rel:apt_group:apt28:USES:technique:t1059\"]",
        "evidence_ids_json": "[]",
        "confidence": 0.82,
        "created_at": "2026-07-15T00:00:00+08:00",
    },
]


DEMO_INFERRED_RELATIONS = [
    {
        "inferred_relation_id": "infer_apt28_phishing_behavior",
        "source_entity_id": "apt_group:apt28",
        "target_entity_id": "technique:t1566",
        "relation_type": "HAS_BEHAVIOR",
        "rationale": "APT28 \u4f7f\u7528\u9c7c\u53c9\u5f0f\u9493\u9c7c\u6280\u672f\uff0c\u8be5\u6280\u672f\u5c5e\u4e8e\u521d\u59cb\u8bbf\u95ee\u9636\u6bb5\u3002",
        "support_evidence_ids_json": "[\"ev_apt28_t1566_001\"]",
        "confidence": 0.86,
        "status": "accepted",
        "created_at": "2026-07-15T00:00:00+08:00",
    },
]


DEMO_REPORTS = [
    {
        "report_id": "report_apt28_demo",
        "target_group": "APT28",
        "title": "APT28 威胁情报分析报告",
        "markdown": (
            "## APT28 威胁情报分析报告\n\n"
            "APT28 是本系统 P0 演示目标之一。当前 mock 图谱展示了组织、攻击技术、"
            "恶意软件和目标类型之间的基础关联。\n\n"
            "### 行为模式\n\n"
            "- 初始访问：使用鱼叉式钓鱼相关技术。\n"
            "- 工具使用：公开报告中多次提到 X-Agent。\n"
            "- 目标偏好：政府机构等高价值目标。\n"
        ),
        "graph_version": "demo-1",
    },
    {
        "report_id": "report_lazarus_demo",
        "target_group": "Lazarus",
        "title": "Lazarus 威胁情报分析报告",
        "markdown": "## Lazarus 威胁情报分析报告\n\nP0 阶段保留基础画像，后续接入真实抽取结果。",
        "graph_version": "demo-1",
    },
    {
        "report_id": "report_kimsuky_demo",
        "target_group": "Kimsuky",
        "title": "Kimsuky 威胁情报分析报告",
        "markdown": "## Kimsuky 威胁情报分析报告\n\nP0 阶段保留基础画像，后续接入真实抽取结果。",
        "graph_version": "demo-1",
    },
]


class DemoStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        configured_path = db_path or os.getenv("SQLITE_DB_PATH") or DEFAULT_DB_PATH
        self.db_path = Path(configured_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS entities (
                  entity_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  type TEXT NOT NULL,
                  aliases_json TEXT NOT NULL DEFAULT '[]',
                  description TEXT NOT NULL DEFAULT '',
                  confidence REAL NOT NULL DEFAULT 0.5,
                  source_count INTEGER NOT NULL DEFAULT 0,
                  first_seen TEXT,
                  last_seen TEXT,
                  tags_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS relations (
                  relation_id TEXT PRIMARY KEY,
                  source_entity_id TEXT NOT NULL,
                  target_entity_id TEXT NOT NULL,
                  relation_type TEXT NOT NULL,
                  label TEXT NOT NULL,
                  confidence REAL NOT NULL DEFAULT 0.5,
                  source_count INTEGER NOT NULL DEFAULT 0,
                  evidence_count INTEGER NOT NULL DEFAULT 0,
                  first_seen TEXT,
                  last_seen TEXT,
                  validation_status TEXT NOT NULL DEFAULT 'valid'
                );

                CREATE TABLE IF NOT EXISTS evidence (
                  evidence_id TEXT PRIMARY KEY,
                  doc_id TEXT NOT NULL,
                  chunk_id TEXT,
                  entity_id TEXT,
                  relation_id TEXT,
                  evidence_text TEXT NOT NULL,
                  source_url TEXT NOT NULL,
                  source_type TEXT NOT NULL DEFAULT '',
                  source_name TEXT NOT NULL DEFAULT '',
                  evidence_type TEXT NOT NULL DEFAULT 'summary',
                  quote_start INTEGER,
                  quote_end INTEGER,
                  published_at TEXT,
                  retrieved_at TEXT,
                  source_reliability TEXT NOT NULL DEFAULT 'unknown',
                  language TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mitre_mappings (
                  mapping_id TEXT PRIMARY KEY,
                  target_group TEXT NOT NULL,
                  technique_id TEXT NOT NULL,
                  technique_name TEXT NOT NULL,
                  tactic TEXT NOT NULL,
                  attack_stage TEXT NOT NULL,
                  entity_id TEXT,
                  relation_id TEXT,
                  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                  source TEXT NOT NULL CHECK (source IN ('rule', 'llm', 'manual')),
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS behavior_patterns (
                  pattern_id TEXT PRIMARY KEY,
                  target_group TEXT NOT NULL,
                  stage TEXT NOT NULL,
                  description TEXT NOT NULL,
                  technique_ids_json TEXT NOT NULL DEFAULT '[]',
                  relation_ids_json TEXT NOT NULL DEFAULT '[]',
                  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS inferred_relations (
                  inferred_relation_id TEXT PRIMARY KEY,
                  source_entity_id TEXT NOT NULL,
                  target_entity_id TEXT NOT NULL,
                  relation_type TEXT NOT NULL,
                  rationale TEXT NOT NULL,
                  support_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
                  status TEXT NOT NULL CHECK (status IN ('candidate', 'accepted', 'rejected')),
                  created_at TEXT NOT NULL,
                  FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id),
                  FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id)
                );

                CREATE TABLE IF NOT EXISTS documents (
                  doc_id TEXT PRIMARY KEY,
                  schema_version TEXT NOT NULL DEFAULT '1.0',
                  collection_item_id TEXT,
                  target_group TEXT NOT NULL,
                  target_groups_json TEXT NOT NULL DEFAULT '[]',
                  source_url TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_name TEXT NOT NULL DEFAULT '',
                  title TEXT NOT NULL,
                  language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
                  clean_text TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  published_at TEXT,
                  retrieved_at TEXT,
                  source_reliability TEXT NOT NULL DEFAULT 'unknown',
                  tlp TEXT NOT NULL DEFAULT 'TLP:CLEAR',
                  tags_json TEXT NOT NULL DEFAULT '[]',
                  metadata_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                  chunk_id TEXT PRIMARY KEY,
                  doc_id TEXT NOT NULL,
                  chunk_index INTEGER NOT NULL DEFAULT 0,
                  section_title TEXT NOT NULL DEFAULT '',
                  text TEXT NOT NULL,
                  char_start INTEGER NOT NULL,
                  char_end INTEGER NOT NULL,
                  text_hash TEXT NOT NULL,
                  token_count INTEGER,
                  FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                  report_id TEXT PRIMARY KEY,
                  target_group TEXT NOT NULL,
                  title TEXT NOT NULL,
                  markdown TEXT NOT NULL,
                  generated_at TEXT NOT NULL DEFAULT '',
                  graph_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS report_sections (
                  section_id TEXT PRIMARY KEY,
                  report_id TEXT NOT NULL,
                  section_type TEXT NOT NULL,
                  title TEXT NOT NULL,
                  markdown TEXT NOT NULL,
                  evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                  analysis_refs_json TEXT NOT NULL DEFAULT '[]',
                  graph_refs_json TEXT NOT NULL DEFAULT '{}',
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  FOREIGN KEY (report_id) REFERENCES reports(report_id)
                );
                """
            )
            ensure_import_compatible_columns(connection)
            self._ensure_columns(connection)

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        migrations = {
            "entities": {
                "first_seen": "TEXT",
                "last_seen": "TEXT",
                "tags_json": "TEXT NOT NULL DEFAULT '[]'",
            },
            "relations": {
                "source_count": "INTEGER NOT NULL DEFAULT 0",
                "evidence_count": "INTEGER NOT NULL DEFAULT 0",
                "first_seen": "TEXT",
                "last_seen": "TEXT",
                "validation_status": "TEXT NOT NULL DEFAULT 'valid'",
            },
            "evidence": {
                "source_type": "TEXT NOT NULL DEFAULT ''",
                "source_name": "TEXT NOT NULL DEFAULT ''",
                "evidence_type": "TEXT NOT NULL DEFAULT 'summary'",
                "quote_start": "INTEGER",
                "quote_end": "INTEGER",
                "published_at": "TEXT",
                "retrieved_at": "TEXT",
                "source_reliability": "TEXT NOT NULL DEFAULT 'unknown'",
            },
        }
        for table_name, columns in migrations.items():
            existing_columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_definition in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                    )

    def seed_demo_data(self, connection: sqlite3.Connection | None = None) -> None:
        owns_connection = connection is None
        active_connection = connection or self.connect()
        try:
            for entity in DEMO_ENTITIES:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO entities (
                      entity_id, name, type, aliases_json, description, confidence,
                      source_count, first_seen, last_seen, tags_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity["entity_id"],
                        entity["name"],
                        entity["type"],
                        json.dumps(entity["aliases"], ensure_ascii=False),
                        entity["description"],
                        entity["confidence"],
                        entity["source_count"],
                        entity["first_seen"],
                        entity["last_seen"],
                        json.dumps(entity["tags"], ensure_ascii=False),
                    ),
                )
            for relation in DEMO_RELATIONS:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO relations (
                      relation_id, source_entity_id, target_entity_id, relation_type, label,
                      confidence, source_count, evidence_count, first_seen, last_seen,
                      validation_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        relation["relation_id"],
                        relation["source_entity_id"],
                        relation["target_entity_id"],
                        relation["relation_type"],
                        relation["label"],
                        relation["confidence"],
                        relation["source_count"],
                        relation["evidence_count"],
                        relation["first_seen"],
                        relation["last_seen"],
                        relation["validation_status"],
                    ),
                )
            for evidence in DEMO_EVIDENCE:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO evidence (
                      evidence_id, doc_id, chunk_id, entity_id, relation_id, evidence_text,
                      source_url, source_type, source_name, evidence_type, quote_start,
                      quote_end, published_at, retrieved_at, source_reliability, language
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence["evidence_id"],
                        evidence["doc_id"],
                        evidence["chunk_id"],
                        evidence["entity_id"],
                        evidence["relation_id"],
                        evidence["evidence_text"],
                        evidence["source_url"],
                        evidence["source_type"],
                        evidence["source_name"],
                        evidence["evidence_type"],
                        evidence["quote_start"],
                        evidence["quote_end"],
                        evidence["published_at"],
                        evidence["retrieved_at"],
                        evidence["source_reliability"],
                        evidence["language"],
                    ),
                )
            for report in DEMO_REPORTS:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO reports (
                      report_id, target_group, title, markdown, graph_version
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        report["report_id"],
                        report["target_group"],
                        report["title"],
                        report["markdown"],
                        report["graph_version"],
                    ),
                )
            for mapping in DEMO_MITRE_MAPPINGS:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO mitre_mappings (
                      mapping_id, target_group, technique_id, technique_name,
                      tactic, attack_stage, entity_id, relation_id,
                      evidence_ids_json, confidence, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mapping["mapping_id"],
                        mapping["target_group"],
                        mapping["technique_id"],
                        mapping["technique_name"],
                        mapping["tactic"],
                        mapping["attack_stage"],
                        mapping["entity_id"],
                        mapping["relation_id"],
                        mapping["evidence_ids_json"],
                        mapping["confidence"],
                        mapping["source"],
                        mapping["created_at"],
                    ),
                )
            for pattern in DEMO_BEHAVIOR_PATTERNS:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO behavior_patterns (
                      pattern_id, target_group, stage, description,
                      technique_ids_json, relation_ids_json,
                      evidence_ids_json, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pattern["pattern_id"],
                        pattern["target_group"],
                        pattern["stage"],
                        pattern["description"],
                        pattern["technique_ids_json"],
                        pattern["relation_ids_json"],
                        pattern["evidence_ids_json"],
                        pattern["confidence"],
                        pattern["created_at"],
                    ),
                )
            for inferred in DEMO_INFERRED_RELATIONS:
                active_connection.execute(
                    """
                    INSERT OR REPLACE INTO inferred_relations (
                      inferred_relation_id, source_entity_id, target_entity_id,
                      relation_type, rationale, support_evidence_ids_json,
                      confidence, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inferred["inferred_relation_id"],
                        inferred["source_entity_id"],
                        inferred["target_entity_id"],
                        inferred["relation_type"],
                        inferred["rationale"],
                        inferred["support_evidence_ids_json"],
                        inferred["confidence"],
                        inferred["status"],
                        inferred["created_at"],
                    ),
                )
        finally:
            if owns_connection:
                active_connection.close()

    def health(self) -> dict[str, str]:
        with self.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"sqlite": "ok", "neo4j": "disconnected", "llm": "not_configured"}

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT entity_id, name, type, aliases_json, description, confidence, "
                "source_count, first_seen, last_seen, tags_json "
                "FROM entities WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "entity_id": row["entity_id"],
            "name": row["name"],
            "type": row["type"],
            "aliases": json.loads(row["aliases_json"]) if row["aliases_json"] else [],
            "description": row["description"],
            "confidence": row["confidence"],
            "source_count": row["source_count"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
        }

    def search_entities(self, q: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT entity_id, name, type, description, confidence "
                "FROM entities "
                "WHERE name LIKE ? OR entity_id LIKE ? OR description LIKE ? "
                "LIMIT 20",
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            ).fetchall()
        return [
            {
                "entity_id": row["entity_id"],
                "name": row["name"],
                "type": row["type"],
                "description": row["description"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    def get_graph(self, target: str | None = None) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT entity_id, name, type, aliases_json, description, confidence,
                       source_count, first_seen, last_seen, tags_json
                FROM entities
                ORDER BY type, name
                """
            ).fetchall()
            relation_rows = connection.execute(
                """
                SELECT relation_id, source_entity_id, target_entity_id, relation_type,
                       label, confidence, source_count, evidence_count, first_seen,
                       last_seen, validation_status
                FROM relations
                ORDER BY relation_id
                """
            ).fetchall()
            evidence_rows = connection.execute(
                """
                SELECT evidence_id, doc_id, chunk_id, entity_id, relation_id,
                       evidence_text, source_url, source_type, source_name,
                       evidence_type, quote_start, quote_end, published_at,
                       retrieved_at, source_reliability, language
                FROM evidence
                ORDER BY evidence_id
                """
            ).fetchall()

        node_evidence_ids: dict[str, list[str]] = {}
        relation_evidence_ids: dict[str, list[str]] = {}
        for row in evidence_rows:
            if row["entity_id"]:
                node_evidence_ids.setdefault(row["entity_id"], []).append(row["evidence_id"])
            if row["relation_id"]:
                relation_evidence_ids.setdefault(row["relation_id"], []).append(row["evidence_id"])

        nodes = [self._node_from_row(row) for row in rows]
        edges = [self._edge_from_row(row) for row in relation_rows]
        for node in nodes:
            node["evidence_ids"] = node_evidence_ids.get(node["id"], [])
        for edge in edges:
            edge["evidence_ids"] = relation_evidence_ids.get(edge["id"], [])

        if target:
            nodes, edges = self._filter_graph(nodes, edges, target)
            visible_node_ids = {node["id"] for node in nodes}
            visible_edge_ids = {edge["id"] for edge in edges}
            evidence = [
                self._evidence_from_row(row)
                for row in evidence_rows
                if row["entity_id"] in visible_node_ids or row["relation_id"] in visible_edge_ids
            ]
        else:
            evidence = [self._evidence_from_row(row) for row in evidence_rows]

        return {"schema_version": "1.0", "nodes": nodes, "edges": edges, "evidence": evidence}

    def get_path(self, source: str, target: str, max_depth: int = 4) -> dict:
        """BFS 最短路径查询。"""
        with self.connect() as conn:
            sql = """
                SELECT source_entity_id, target_entity_id, relation_id
                FROM relations
                WHERE source_entity_id = ? OR target_entity_id = ?
            """
            queue = deque()
            queue.append((source, [source], []))
            visited = {source}
            while queue:
                current, node_path, edge_path = queue.popleft()
                if len(node_path) - 1 > max_depth:
                    continue
                rows = conn.execute(sql, (current, current)).fetchall()
                for row in rows:
                    if row["relation_id"] in edge_path:
                        continue
                    neighbor = row["target_entity_id"] if row["source_entity_id"] == current else row["source_entity_id"]
                    new_node_path = node_path + [neighbor]
                    new_edge_path = edge_path + [row["relation_id"]]
                    if neighbor == target:
                        all_nodes = []
                        for nid in new_node_path:
                            r = conn.execute(
                                "SELECT * FROM entities WHERE entity_id = ?", (nid,)
                            ).fetchone()
                            if r:
                                all_nodes.append(self._node_from_row(r))
                        all_edges = []
                        for rid in new_edge_path:
                            r = conn.execute(
                                "SELECT * FROM relations WHERE relation_id = ?", (rid,)
                            ).fetchone()
                            if r:
                                all_edges.append(self._edge_from_row(r))
                        evidence_ids = []
                        for n in new_node_path:
                            evs = conn.execute(
                                "SELECT evidence_id FROM evidence WHERE entity_id = ?", (n,)
                            ).fetchall()
                            evidence_ids.extend(ev["evidence_id"] for ev in evs)
                        for rid in new_edge_path:
                            evs = conn.execute(
                                "SELECT evidence_id FROM evidence WHERE relation_id = ?", (rid,)
                            ).fetchall()
                            evidence_ids.extend(ev["evidence_id"] for ev in evs)
                        return {
                            "source": source,
                            "target": target,
                            "engine": "sqlite",
                            "paths": [{
                                "nodes": all_nodes,
                                "edges": all_edges,
                                "length": len(new_node_path) - 1,
                                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                            }]
                        }
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, new_node_path, new_edge_path))
            return {"source": source, "target": target, "engine": "sqlite", "paths": []}

    def get_report(self, target_group: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT target_group, title, markdown, generated_at
                FROM reports
                WHERE lower(target_group) = lower(?)
                ORDER BY generated_at DESC NULLS LAST
                """,
                (target_group,),
            ).fetchone()
        if row is None:
            return None
        result = {
            "target_group": row["target_group"],
            "title": row["title"],
            "markdown": row["markdown"],
        }
        sections = self.get_report_sections(target_group)
        if sections:
            result["sections"] = sections
        result["generated_at"] = row["generated_at"] or ""
        return result

    def get_report_sections(self, target_group: str) -> list[dict[str, Any]]:
        """获取指定目标组织的报告结构化章节。"""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT section_id, section_type, title, markdown,
                       evidence_ids_json, analysis_refs_json, graph_refs_json,
                       sort_order
                FROM report_sections
                WHERE report_id IN (
                    SELECT report_id FROM reports
                    WHERE lower(target_group) = lower(?)
                )
                ORDER BY sort_order
                """,
                (target_group,),
            ).fetchall()
        return [
            {
                "section_id": row["section_id"],
                "section_type": row["section_type"],
                "title": row["title"],
                "markdown": row["markdown"],
                "evidence_ids": json.loads(row["evidence_ids_json"]),
                "analysis_refs": json.loads(row["analysis_refs_json"]),
                "graph_refs": json.loads(row["graph_refs_json"]),
                "sort_order": row["sort_order"],
            }
            for row in rows
        ]

    def generate_report(self, target_group: str) -> dict[str, Any] | None:
        """生成智能分析报告并写入数据库。"""
        target_entity_id = f"apt_group:{target_group.lower()}"
        with self.connect() as connection:
            entity = connection.execute(
                "SELECT entity_id FROM entities WHERE entity_id = ?",
                (target_entity_id,),
            ).fetchone()
            if entity is None:
                return None

            now_iso = datetime.now(UTC).isoformat()
            result = generate_intelligent_report(
                connection, target_group, target_entity_id
            )

            report_id = f"report_{target_group.lower()}_intelligent"
            title = f"{target_group} 威胁情报分析报告"

            if not result.get("_llm_generated", True):
                existing = connection.execute(
                    "SELECT report_id FROM reports WHERE target_group = ? AND generated_at != ''",
                    (target_group,),
                ).fetchone()
                if existing:
                    return self.get_report(target_group)

            connection.execute(
                """
                INSERT OR REPLACE INTO reports (
                  report_id, target_group, title, markdown, generated_at, graph_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (report_id, target_group, title, result["markdown"], now_iso, "intelligent-v1"),
            )

            connection.execute(
                "DELETE FROM report_sections WHERE report_id = ?",
                (report_id,),
            )

            for section in result["sections"]:
                section_id = f"{report_id}_{section['section_type']}"
                connection.execute(
                    """
                    INSERT INTO report_sections (
                      section_id, report_id, section_type, title, markdown,
                      evidence_ids_json, analysis_refs_json, graph_refs_json, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        section_id,
                        report_id,
                        section["section_type"],
                        section["title"],
                        section["markdown"],
                        json.dumps(section["evidence_ids"], ensure_ascii=False),
                        json.dumps(section["analysis_refs"], ensure_ascii=False),
                        json.dumps(section["graph_refs"], ensure_ascii=False),
                        section["sort_order"],
                    ),
                )

            connection.commit()

        return {
            "target_group": target_group,
            "title": title,
            "markdown": result["markdown"],
            "sections": result["sections"],
            "generated_at": now_iso,
        }

    def get_analysis(self) -> dict[str, Any]:
        with self.connect() as connection:
            mitre_rows = []
            behavior_rows = []
            inference_rows = []
            if self._table_exists(connection, "mitre_mappings"):
                mitre_rows = connection.execute(
                    """
                    SELECT mapping_id, target_group, technique_id, technique_name, tactic,
                           attack_stage, entity_id, relation_id, source, confidence,
                           evidence_ids_json
                    FROM mitre_mappings
                    ORDER BY mapping_id
                    """
                ).fetchall()
            if self._table_exists(connection, "behavior_patterns"):
                behavior_rows = connection.execute(
                    """
                    SELECT pattern_id, target_group, stage, description, technique_ids_json,
                           relation_ids_json, evidence_ids_json, confidence
                    FROM behavior_patterns
                    ORDER BY pattern_id
                    """
                ).fetchall()
            if self._table_exists(connection, "inferred_relations"):
                inference_rows = connection.execute(
                    """
                    SELECT inferred_relation_id, source_entity_id, target_entity_id, relation_type,
                           rationale, support_evidence_ids_json, confidence, status
                    FROM inferred_relations
                    ORDER BY inferred_relation_id
                    """
                ).fetchall()

        return {
            "mitre_mappings": [
                {
                    "mapping_id": row["mapping_id"],
                    "target_group": row["target_group"],
                    "technique_id": row["technique_id"],
                    "technique_name": row["technique_name"],
                    "tactic": row["tactic"],
                    "attack_stage": row["attack_stage"],
                    "entity_id": row["entity_id"],
                    "relation_id": row["relation_id"],
                    "source": row["source"],
                    "confidence": row["confidence"],
                    "evidence_ids": json.loads(row["evidence_ids_json"]),
                }
                for row in mitre_rows
            ],
            "behavior_patterns": [
                {
                    "pattern_id": row["pattern_id"],
                    "target_group": row["target_group"],
                    "stage": row["stage"],
                    "description": row["description"],
                    "technique_ids": json.loads(row["technique_ids_json"]),
                    "relation_ids": json.loads(row["relation_ids_json"]),
                    "evidence_ids": json.loads(row["evidence_ids_json"]),
                    "confidence": row["confidence"],
                }
                for row in behavior_rows
            ],
            "inferred_relations": [
                {
                    "inferred_relation_id": row["inferred_relation_id"],
                    "source": row["source_entity_id"],
                    "target": row["target_entity_id"],
                    "type": row["relation_type"],
                    "rationale": row["rationale"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "evidence_ids": json.loads(row["support_evidence_ids_json"]),
                }
                for row in inference_rows
            ],
        }

    def import_document(self, document: dict) -> dict:
        """导入文档，去重后写入 documents 表，自动切 chunks。"""
        doc_id = document["doc_id"]
        clean_text = document["clean_text"]
        content_hash = document.get("content_hash", "")
        if not content_hash:
            import hashlib
            content_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        from datetime import UTC, datetime as dt
        now = dt.now(UTC).isoformat()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT doc_id FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if existing:
                return {"doc_id": doc_id, "status": "skipped", "message": "文档已存在"}
            conn.execute(
                """INSERT INTO documents (
                  doc_id, schema_version, target_group, source_url, source_type,
                  source_name, title, language, clean_text, content_hash,
                  published_at, retrieved_at, source_reliability, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id,
                    document.get("schema_version", "1.0"),
                    document.get("target_group", ""),
                    document.get("source_url", ""),
                    document.get("source_type", ""),
                    document.get("source_name", ""),
                    document.get("title", ""),
                    document.get("language", "zh"),
                    clean_text,
                    content_hash,
                    document.get("published_at"),
                    document.get("retrieved_at"),
                    document.get("source_reliability", "unknown"),
                    now,
                ),
            )
            paragraphs = clean_text.split("\n")
            chunk_index = 0
            char_pos = 0
            for para in paragraphs:
                if not para.strip():
                    char_pos += len(para) + 1
                    continue
                chunk_id = f"{doc_id}_c{chunk_index:03d}"
                import hashlib
                text_hash = hashlib.sha256(para.encode("utf-8")).hexdigest()
                conn.execute(
                    """INSERT INTO chunks (
                      chunk_id, doc_id, chunk_index, text, char_start, char_end, text_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (chunk_id, doc_id, chunk_index, para, char_pos, char_pos + len(para), text_hash),
                )
                chunk_index += 1
                char_pos += len(para) + 1
        return {"doc_id": doc_id, "status": "imported", "chunks": chunk_index}

    def _filter_graph(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        target: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        normalized_target = target.lower()
        target_nodes = [
            node
            for node in nodes
            if node["name"].lower() == normalized_target or node["id"].lower().endswith(f":{normalized_target}")
        ]
        if not target_nodes:
            return [], []

        target_ids = {node["id"] for node in target_nodes}
        visible_edges = [
            edge
            for edge in edges
            if edge["source"] in target_ids or edge["target"] in target_ids
        ]
        visible_node_ids = set(target_ids)
        for edge in visible_edges:
            visible_node_ids.add(edge["source"])
            visible_node_ids.add(edge["target"])

        return [node for node in nodes if node["id"] in visible_node_ids], visible_edges

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _node_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["entity_id"],
            "name": row["name"],
            "type": row["type"],
            "aliases": json.loads(row["aliases_json"]),
            "description": row["description"],
            "confidence": row["confidence"],
            "source_count": row["source_count"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "tags": json.loads(row["tags_json"]),
            "evidence_ids": [],
        }

    def _edge_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["relation_id"],
            "source": row["source_entity_id"],
            "target": row["target_entity_id"],
            "type": row["relation_type"],
            "label": row["label"],
            "confidence": row["confidence"],
            "source_count": row["source_count"],
            "evidence_count": row["evidence_count"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "validation_status": row["validation_status"],
            "evidence_ids": [],
        }

    def _evidence_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["evidence_id"],
            "doc_id": row["doc_id"],
            "chunk_id": row["chunk_id"],
            "entity_id": row["entity_id"],
            "relation_id": row["relation_id"],
            "text": row["evidence_text"],
            "source_url": row["source_url"],
            "source_type": row["source_type"],
            "source_name": row["source_name"],
            "evidence_type": row["evidence_type"],
            "quote_start": row["quote_start"],
            "quote_end": row["quote_end"],
            "published_at": row["published_at"],
            "retrieved_at": row["retrieved_at"],
            "source_reliability": row["source_reliability"],
            "language": row["language"],
        }
