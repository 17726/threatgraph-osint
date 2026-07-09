import hashlib
import json
import os
import sqlite3
from collections import deque
from datetime import UTC, datetime
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
    def __init__(self, db_path: str | Path | None = None, seed_demo: bool = True) -> None:
        configured_path = db_path or os.getenv("SQLITE_DB_PATH") or DEFAULT_DB_PATH
        self.db_path = Path(configured_path)
        self.seed_demo = seed_demo
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
                  language TEXT NOT NULL,
                  raw_text TEXT NOT NULL,
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
                  generated_at TEXT,
                  graph_version TEXT NOT NULL
                );
                """
            )
            self._ensure_columns(connection)
            if self.seed_demo:
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
            "reports": {
                "generated_at": "TEXT",
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

    def count_rows(self, table_name: str) -> int:
        with self.connect() as connection:
            row = connection.execute(f"SELECT count(*) AS count FROM {table_name}").fetchone()
        return int(row["count"])

    def import_document(self, document: dict[str, Any]) -> dict[str, Any]:
        clean_text = document.get("clean_text")
        if not clean_text:
            raise ValueError("document.clean_text 不能为空")
        doc_id = document["doc_id"]
        chunk_id = f"{doc_id}_c001"
        now = now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO documents (
                  doc_id, schema_version, collection_item_id, target_group, target_groups_json,
                  source_url, source_type, source_name, title, language, raw_text, content_hash,
                  published_at, retrieved_at, source_reliability, tlp, tags_json, metadata_json,
                  created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    document.get("schema_version", "1.0"),
                    document.get("collection_item_id"),
                    document["target_group"],
                    json.dumps(document.get("target_groups", []), ensure_ascii=False),
                    document["source_url"],
                    document["source_type"],
                    document["source_name"],
                    document["title"],
                    document["language"],
                    clean_text,
                    document["content_hash"],
                    document.get("published_at"),
                    document["retrieved_at"],
                    document.get("source_reliability", "unknown"),
                    document.get("tlp", "TLP:CLEAR"),
                    json.dumps(document.get("tags", []), ensure_ascii=False),
                    json.dumps(document.get("metadata", {}), ensure_ascii=False),
                    now,
                ),
            )
            connection.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            connection.execute(
                """
                INSERT INTO chunks (
                  chunk_id, doc_id, chunk_index, section_title, text, char_start,
                  char_end, text_hash, token_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    doc_id,
                    0,
                    "",
                    clean_text,
                    0,
                    len(clean_text),
                    "sha256:" + sha256_text(clean_text),
                    None,
                ),
            )
            connection.commit()
        return {"doc_id": doc_id, "chunk_count": 1, "chunk_ids": [chunk_id]}

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

    def search_entities(self, query: str) -> list[dict[str, Any]]:
        normalized_query = query.lower()
        graph = self.get_graph()
        return [
            node
            for node in graph["nodes"]
            if normalized_query in node["id"].lower()
            or normalized_query in node["name"].lower()
            or any(normalized_query in alias.lower() for alias in node["aliases"])
        ]

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        graph = self.get_graph()
        node = next((item for item in graph["nodes"] if item["id"] == entity_id), None)
        if node is None:
            return None
        evidence = [item for item in graph["evidence"] if item["entity_id"] == entity_id]
        return {**node, "evidence": evidence}

    def find_paths(self, source: str, target: str, max_depth: int = 4) -> dict[str, Any]:
        graph = self.get_graph()
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        edges_by_id = {edge["id"]: edge for edge in graph["edges"]}
        if source not in nodes_by_id or target not in nodes_by_id:
            return {"source": source, "target": target, "engine": "sqlite", "paths": []}

        adjacency: dict[str, list[tuple[str, str]]] = {}
        for edge in graph["edges"]:
            adjacency.setdefault(edge["source"], []).append((edge["target"], edge["id"]))
            adjacency.setdefault(edge["target"], []).append((edge["source"], edge["id"]))
        for items in adjacency.values():
            items.sort(key=lambda item: (item[0], item[1]))

        queue = deque([(source, [source], [])])
        paths = []
        while queue and len(paths) < 3:
            current, node_path, edge_path = queue.popleft()
            if len(edge_path) >= max_depth:
                continue
            for next_node, edge_id in adjacency.get(current, []):
                if next_node in node_path:
                    continue
                next_node_path = [*node_path, next_node]
                next_edge_path = [*edge_path, edge_id]
                if next_node == target:
                    path_edges = [edges_by_id[item] for item in next_edge_path]
                    evidence_ids = sorted(
                        {
                            evidence_id
                            for edge in path_edges
                            for evidence_id in edge["evidence_ids"]
                        }
                    )
                    paths.append(
                        {
                            "nodes": [minimal_node(nodes_by_id[item]) for item in next_node_path],
                            "edges": [minimal_edge(item) for item in path_edges],
                            "length": len(next_edge_path),
                            "evidence_ids": evidence_ids,
                        }
                    )
                    continue
                queue.append((next_node, next_node_path, next_edge_path))

        return {"source": source, "target": target, "engine": "sqlite", "paths": paths}

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

    def get_analysis(self, target_group: str | None = None) -> dict[str, Any]:
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

        analysis = {
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
        if target_group is None:
            return analysis

        return {
            "mitre_mappings": [
                item
                for item in analysis["mitre_mappings"]
                if item["target_group"].lower() == target_group.lower()
            ],
            "behavior_patterns": [
                item
                for item in analysis["behavior_patterns"]
                if item["target_group"].lower() == target_group.lower()
            ],
            "inferred_relations": analysis["inferred_relations"],
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


def minimal_node(node: dict[str, Any]) -> dict[str, Any]:
    return {"id": node["id"], "name": node["name"], "type": node["type"]}


def minimal_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": edge["id"],
        "source": edge["source"],
        "target": edge["target"],
        "type": edge["type"],
        "label": edge["label"],
    }


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
