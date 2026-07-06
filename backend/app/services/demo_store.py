import json
import os
import sqlite3
from pathlib import Path
from typing import Any


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
        "entity_id": "target:government",
        "name": "Government Organizations",
        "type": "TARGET",
        "aliases": ["政府机构"],
        "description": "APT 活动中常见的高价值目标类别。",
        "confidence": 0.84,
        "source_count": 2,
        "first_seen": "2014-01-01",
        "last_seen": "2026-07-01",
        "tags": ["target"],
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
        "relation_id": "rel:apt_group:apt28:TARGETS:target:government",
        "source_entity_id": "apt_group:apt28",
        "target_entity_id": "target:government",
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
        "evidence_text": "多份公开安全报告将 APT28 描述为长期活跃并偏好政府、军事等高价值目标的威胁组织。",
        "source_url": "https://attack.mitre.org/groups/G0007/",
        "source_type": "security_report",
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
        "source_type": "security_report",
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
        "source_type": "security_report",
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

                CREATE TABLE IF NOT EXISTS reports (
                  report_id TEXT PRIMARY KEY,
                  target_group TEXT NOT NULL,
                  title TEXT NOT NULL,
                  markdown TEXT NOT NULL,
                  graph_version TEXT NOT NULL
                );
                """
            )
            self._ensure_columns(connection)
            self.seed_demo_data(connection)

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
            active_connection.commit()
        finally:
            if owns_connection:
                active_connection.close()

    def health(self) -> dict[str, str]:
        with self.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"sqlite": "ok", "neo4j": "disconnected", "llm": "not_configured"}

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

    def get_report(self, target_group: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT target_group, title, markdown
                FROM reports
                WHERE lower(target_group) = lower(?)
                """,
                (target_group,),
            ).fetchone()
        if row is None:
            return None
        return {
            "target_group": row["target_group"],
            "title": row["title"],
            "markdown": row["markdown"],
        }

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
            return nodes, edges

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
