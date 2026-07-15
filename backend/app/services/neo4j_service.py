from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.db.schema import ensure_graph_sync_schema

try:
    from neo4j import GraphDatabase
except ImportError:  # Neo4j 是可选增强能力
    GraphDatabase = None


STATE_KEY = "neo4j"
PROJECTION_NAME = "threatgraph-osint"
MAX_PATH_DEPTH = 8
TABLE_KEYS = {
    "entities": "entity_id",
    "relations": "relation_id",
    "evidence": "evidence_id",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Neo4jService:
    """将 SQLite canonical graph 同步为可重建的 Neo4j 查询投影。"""

    def __init__(
        self,
        db_path: str | Path,
        driver: Any = None,
        uri: str | None = None,
        auth: tuple[str, str] | None = None,
        database: str | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.driver = driver
        self.database = database
        self._sync_lock = threading.Lock()
        if self.driver is None and GraphDatabase is not None and uri:
            self.driver = GraphDatabase.driver(uri, auth=auth)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _session(self):
        if self.database:
            return self.driver.session(database=self.database)
        return self.driver.session()

    def close(self) -> None:
        if self.driver is not None:
            self.driver.close()

    def health(self) -> dict[str, Any]:
        if self.driver is None:
            return {"available": False, "status": "disconnected"}
        try:
            with self._session() as session:
                record = session.run("RETURN 1 AS ok").single()
            if not record or record.get("ok") != 1:
                raise RuntimeError("Neo4j 健康检查未返回预期结果")
            return {"available": True, "status": "connected"}
        except Exception:
            return {"available": False, "status": "disconnected"}

    def status(self) -> dict[str, Any]:
        with self.connect() as connection:
            ensure_graph_sync_schema(connection)
            state = connection.execute(
                "SELECT * FROM sync_state WHERE state_key = ?",
                (STATE_KEY,),
            ).fetchone()
            maximum = connection.execute(
                "SELECT coalesce(max(change_id), 0) FROM graph_changes"
            ).fetchone()[0]
        health = self.health()
        watermark = int(state["watermark"])
        return {
            "available": health["available"],
            "connection": health["status"],
            "status": state["status"],
            "watermark": watermark,
            "latest_change": int(maximum or 0),
            "pending_changes": max(0, int(maximum or 0) - watermark),
            "requires_rebuild": state["last_full_sync_at"] is None,
            "last_attempt_at": state["last_attempt_at"],
            "last_success_at": state["last_success_at"],
            "last_full_sync_at": state["last_full_sync_at"],
            "error": state["error_message"],
        }

    def get_watermark(self) -> int:
        with self.connect() as connection:
            ensure_graph_sync_schema(connection)
            row = connection.execute(
                "SELECT watermark FROM sync_state WHERE state_key = ?",
                (STATE_KEY,),
            ).fetchone()
        return int(row[0]) if row else 0

    def rebuild(self) -> dict[str, Any]:
        with self._sync_lock:
            return self._rebuild_locked()

    def _rebuild_locked(self) -> dict[str, Any]:
        if self.driver is None:
            self._mark_failed("neo4j_unavailable")
            return {"status": "failed", "reason": "neo4j_unavailable"}
        self._mark_attempt()
        try:
            snapshot = self._read_full_snapshot()
            self._validate_relation_endpoints(
                snapshot["entities"],
                snapshot["relations"],
            )
            self._ensure_neo4j_schema()
            with self._session() as session:
                session.execute_write(self._write_full_snapshot, snapshot)
            self._mark_succeeded(snapshot["watermark"], full=True)
            return {
                "status": "succeeded",
                "nodes": len(snapshot["entities"]),
                "edges": len(snapshot["relations"]),
                "evidence": len(snapshot["evidence"]),
                "watermark": snapshot["watermark"],
            }
        except Exception:
            self._mark_failed("neo4j_rebuild_failed")
            return {"status": "failed", "reason": "neo4j_rebuild_failed"}

    def sync_incremental(self) -> dict[str, Any]:
        with self._sync_lock:
            return self._sync_incremental_locked()

    def _sync_incremental_locked(self) -> dict[str, Any]:
        current = self._read_state()
        watermark = int(current["watermark"])
        if current["last_full_sync_at"] is None:
            return {"status": "requires_rebuild", "watermark": watermark}
        if self.driver is None:
            self._mark_failed("neo4j_unavailable")
            return {
                "status": "failed",
                "reason": "neo4j_unavailable",
                "watermark": watermark,
            }

        self._mark_attempt()
        try:
            batch = self._read_incremental_batch(watermark)
            if batch["changes"]:
                with self._session() as session:
                    session.execute_write(self._write_incremental_batch, batch)
            self._mark_succeeded(batch["watermark"], full=False)
            return {
                "status": "succeeded",
                "changes": batch["changes"],
                "watermark": batch["watermark"],
            }
        except Exception:
            self._mark_failed("neo4j_sync_failed")
            return {
                "status": "failed",
                "reason": "neo4j_sync_failed",
                "watermark": watermark,
            }

    def get_path(
        self,
        source: str,
        target: str,
        max_depth: int = 4,
        relation_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        if max_depth < 1 or max_depth > MAX_PATH_DEPTH:
            raise ValueError(f"max_depth 必须位于 1 到 {MAX_PATH_DEPTH} 之间")
        if self.driver is None:
            return self._unavailable_path(source, target, "neo4j_unavailable")
        state = self._read_state()
        if state["last_full_sync_at"] is None:
            return self._unavailable_path(source, target, "projection_not_ready")
        with self.connect() as connection:
            latest_change = int(
                connection.execute(
                    "SELECT coalesce(max(change_id), 0) FROM graph_changes"
                ).fetchone()[0]
            )
        if (
            state["status"] != "succeeded"
            or int(state["watermark"]) < latest_change
        ):
            return self._unavailable_path(source, target, "projection_stale")

        query = (
            "MATCH p=shortestPath("
            "(s:ThreatGraphProjection:ThreatEntity {id: $source})"
            "-[:THREAT_RELATION*..8]-"
            "(t:ThreatGraphProjection:ThreatEntity {id: $target})) "
            "WHERE length(p) <= $max_depth "
            "AND all(node IN nodes(p) WHERE node:ThreatGraphProjection) "
            "AND all(rel IN relationships(p) "
            "WHERE rel.projection = $projection) "
            "AND (size($relation_types) = 0 OR all(rel IN relationships(p) "
            "WHERE rel.relation_type IN $relation_types)) "
            "AND ($min_confidence IS NULL OR all(rel IN relationships(p) "
            "WHERE rel.confidence >= $min_confidence)) "
            "RETURN p LIMIT 1"
        )
        try:
            with self._session() as session:
                result = session.run(
                    query,
                    source=source,
                    target=target,
                    max_depth=max_depth,
                    projection=PROJECTION_NAME,
                    relation_types=relation_types or [],
                    min_confidence=min_confidence,
                )
                paths = [
                    self._serialize_path(row.get("p"))
                    # Result.data() 会把 Neo4j Path 有损转换为普通 list。
                    for row in result
                ]
            return {
                "source": source,
                "target": target,
                "engine": "neo4j",
                "paths": [path for path in paths if path is not None],
            }
        except Exception:
            return self._unavailable_path(source, target, "neo4j_query_failed")

    def _read_state(self) -> sqlite3.Row:
        with self.connect() as connection:
            ensure_graph_sync_schema(connection)
            return connection.execute(
                "SELECT * FROM sync_state WHERE state_key = ?",
                (STATE_KEY,),
            ).fetchone()

    def _mark_attempt(self) -> None:
        now = _now()
        with self.connect() as connection:
            ensure_graph_sync_schema(connection)
            connection.execute(
                """UPDATE sync_state
                   SET status = 'syncing', last_attempt_at = ?,
                       error_message = NULL, updated_at = ?
                   WHERE state_key = ?""",
                (now, now, STATE_KEY),
            )

    def _mark_succeeded(self, watermark: int, *, full: bool) -> None:
        now = _now()
        with self.connect() as connection:
            connection.execute(
                """UPDATE sync_state
                   SET watermark = ?, status = 'succeeded',
                       last_success_at = ?,
                       last_full_sync_at = CASE WHEN ? THEN ? ELSE last_full_sync_at END,
                       error_message = NULL, updated_at = ?
                   WHERE state_key = ?""",
                (watermark, now, int(full), now, now, STATE_KEY),
            )

    def _mark_failed(self, reason: str) -> None:
        now = _now()
        with self.connect() as connection:
            ensure_graph_sync_schema(connection)
            connection.execute(
                """UPDATE sync_state
                   SET status = 'failed', last_attempt_at = ?,
                       error_message = ?, updated_at = ?
                   WHERE state_key = ?""",
                (now, reason, now, STATE_KEY),
            )

    def _read_full_snapshot(self) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN")
            entities = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM entities ORDER BY entity_id"
                )
            ]
            relations = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM relations ORDER BY relation_id"
                )
            ]
            evidence = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM evidence ORDER BY evidence_id"
                )
            ]
            watermark = int(
                connection.execute(
                    "SELECT coalesce(max(change_id), 0) FROM graph_changes"
                ).fetchone()[0]
            )
            connection.commit()
        self._attach_evidence_ids(entities, relations, evidence)
        return {
            "entities": entities,
            "relations": relations,
            "evidence": evidence,
            "watermark": watermark,
            "captured_at": _now(),
        }

    def _read_incremental_batch(self, watermark: int) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN")
            upper_bound = int(
                connection.execute(
                    "SELECT coalesce(max(change_id), 0) FROM graph_changes"
                ).fetchone()[0]
            )
            changes = [
                dict(row)
                for row in connection.execute(
                    """SELECT * FROM graph_changes
                       WHERE change_id > ? AND change_id <= ?
                       ORDER BY change_id""",
                    (watermark, upper_bound),
                )
            ]
            touched = list(
                dict.fromkeys(
                    (change["table_name"], change["record_id"])
                    for change in changes
                )
            )
            records: list[dict[str, Any]] = []
            for table_name, record_id in touched:
                key = TABLE_KEYS[table_name]
                row = connection.execute(
                    f"SELECT * FROM {table_name} WHERE {key} = ?",
                    (record_id,),
                ).fetchone()
                records.append(
                    {
                        "table_name": table_name,
                        "record_id": record_id,
                        "record": dict(row) if row is not None else None,
                    }
                )
            evidence = [
                dict(row)
                for row in connection.execute("SELECT * FROM evidence")
            ]
            connection.commit()

        entities = [
            item["record"]
            for item in records
            if item["table_name"] == "entities" and item["record"] is not None
        ]
        relations = [
            item["record"]
            for item in records
            if item["table_name"] == "relations" and item["record"] is not None
        ]
        self._attach_evidence_ids(entities, relations, evidence)
        return {
            "changes": len(changes),
            "records": records,
            "watermark": upper_bound,
            "captured_at": _now(),
        }

    def _ensure_neo4j_schema(self) -> None:
        queries = (
            "CREATE CONSTRAINT threatgraph_projection_entity_id IF NOT EXISTS "
            "FOR (n:ThreatGraphProjectionEntity) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT threatgraph_projection_evidence_id IF NOT EXISTS "
            "FOR (n:ThreatGraphProjectionEvidence) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX threatgraph_projection_relation_id IF NOT EXISTS "
            "FOR ()-[r:THREAT_RELATION]-() ON (r.projection, r.id)",
        )
        with self._session() as session:
            for query in queries:
                session.run(query).consume()

    def _write_full_snapshot(self, tx: Any, snapshot: dict[str, Any]) -> None:
        tx.run(
            "MATCH ()-[r:THREAT_RELATION {projection: $projection}]-() "
            "DELETE r",
            projection=PROJECTION_NAME,
        ).consume()
        # 非 DETACH 删除会在存在外部关系时让整笔事务失败回滚。
        tx.run("MATCH (n:ThreatGraphProjection) DELETE n").consume()
        entity_records = [
            {
                "id": item["entity_id"],
                "properties": self._entity_properties(
                    item,
                    snapshot["watermark"],
                    snapshot["captured_at"],
                ),
            }
            for item in snapshot["entities"]
        ]
        evidence_records = [
            {
                "id": item["evidence_id"],
                "properties": self._evidence_properties(
                    item,
                    snapshot["watermark"],
                    snapshot["captured_at"],
                ),
            }
            for item in snapshot["evidence"]
        ]
        relation_records = [
            {
                "id": item["relation_id"],
                "source": item["source_entity_id"],
                "target": item["target_entity_id"],
                "properties": self._relation_properties(
                    item,
                    snapshot["watermark"],
                    snapshot["captured_at"],
                ),
            }
            for item in snapshot["relations"]
        ]
        self._upsert_entities(tx, entity_records)
        self._upsert_evidence(tx, evidence_records)
        self._upsert_relations(tx, relation_records)

    def _write_incremental_batch(self, tx: Any, batch: dict[str, Any]) -> None:
        upserts = {
            "entities": [],
            "relations": [],
            "evidence": [],
        }
        deletes = {
            "entities": [],
            "relations": [],
            "evidence": [],
        }
        for item in batch["records"]:
            table_name = item["table_name"]
            record = item["record"]
            if record is None:
                deletes[table_name].append(item["record_id"])
                continue
            if table_name == "entities":
                upserts[table_name].append(
                    {
                        "id": record["entity_id"],
                        "properties": self._entity_properties(
                            record,
                            batch["watermark"],
                            batch["captured_at"],
                        ),
                    }
                )
            elif table_name == "relations":
                upserts[table_name].append(
                    {
                        "id": record["relation_id"],
                        "source": record["source_entity_id"],
                        "target": record["target_entity_id"],
                        "properties": self._relation_properties(
                            record,
                            batch["watermark"],
                            batch["captured_at"],
                        ),
                    }
                )
            else:
                upserts[table_name].append(
                    {
                        "id": record["evidence_id"],
                        "properties": self._evidence_properties(
                            record,
                            batch["watermark"],
                            batch["captured_at"],
                        ),
                    }
                )

        self._upsert_entities(tx, upserts["entities"])
        self._upsert_relations(tx, upserts["relations"])
        self._upsert_evidence(tx, upserts["evidence"])
        if deletes["evidence"]:
            tx.run(
                "UNWIND $ids AS id "
                "MATCH (e:ThreatGraphProjection:ThreatEvidence {id: id}) "
                "DELETE e",
                ids=deletes["evidence"],
            ).consume()
        if deletes["relations"]:
            tx.run(
                "UNWIND $ids AS id "
                "MATCH (:ThreatGraphProjection)"
                "-[r:THREAT_RELATION {id: id, projection: $projection}]->"
                "(:ThreatGraphProjection) DELETE r",
                ids=deletes["relations"],
                projection=PROJECTION_NAME,
            ).consume()
        if deletes["entities"]:
            tx.run(
                "UNWIND $ids AS id "
                "MATCH (n:ThreatGraphProjection:ThreatEntity {id: id}) "
                "DELETE n",
                ids=deletes["entities"],
            ).consume()

    @staticmethod
    def _upsert_entities(tx: Any, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        tx.run(
            """UNWIND $records AS record
               MERGE (n:ThreatGraphProjection:ThreatEntity:ThreatGraphProjectionEntity
                      {id: record.id})
               SET n = record.properties, n.id = record.id""",
            records=records,
        ).consume()

    @staticmethod
    def _upsert_evidence(tx: Any, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        tx.run(
            """UNWIND $records AS record
               MERGE (e:ThreatGraphProjection:ThreatEvidence:ThreatGraphProjectionEvidence
                      {id: record.id})
               SET e = record.properties, e.id = record.id""",
            records=records,
        ).consume()

    @staticmethod
    def _upsert_relations(tx: Any, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        tx.run(
            """UNWIND $records AS record
               MATCH (:ThreatGraphProjection)-[r:THREAT_RELATION
                     {id: record.id, projection: $projection}]->(:ThreatGraphProjection)
               DELETE r""",
            records=records,
            projection=PROJECTION_NAME,
        ).consume()
        result = tx.run(
            """UNWIND $records AS record
               MATCH (s:ThreatGraphProjection:ThreatEntity {id: record.source})
               MATCH (t:ThreatGraphProjection:ThreatEntity {id: record.target})
               MERGE (s)-[r:THREAT_RELATION {id: record.id, projection: $projection}]->(t)
               SET r = record.properties, r.id = record.id
               RETURN count(r) AS synced""",
            records=records,
            projection=PROJECTION_NAME,
        ).single()
        if result is not None and result.get("synced") != len(records):
            raise RuntimeError("Neo4j 关系端点缺失")

    @staticmethod
    def _validate_relation_endpoints(
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> None:
        entity_ids = {item["entity_id"] for item in entities}
        if any(
            relation["source_entity_id"] not in entity_ids
            or relation["target_entity_id"] not in entity_ids
            for relation in relations
        ):
            raise ValueError("SQLite canonical relation 端点不存在")

    @staticmethod
    def _attach_evidence_ids(
        entities: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
    ) -> None:
        by_entity: dict[str, list[str]] = {}
        by_relation: dict[str, list[str]] = {}
        for item in evidence:
            if item.get("entity_id"):
                by_entity.setdefault(item["entity_id"], []).append(item["evidence_id"])
            if item.get("relation_id"):
                by_relation.setdefault(item["relation_id"], []).append(
                    item["evidence_id"]
                )
        for item in entities:
            item["evidence_ids"] = sorted(by_entity.get(item["entity_id"], []))
        for item in relations:
            item["evidence_ids"] = sorted(by_relation.get(item["relation_id"], []))

    @staticmethod
    def _entity_properties(
        entity: dict[str, Any],
        sync_version: int,
        captured_at: str,
    ) -> dict[str, Any]:
        return {
            "name": entity["name"],
            "type": entity["type"],
            "aliases": json.loads(entity.get("aliases_json") or "[]"),
            "description": entity.get("description") or "",
            "confidence": entity.get("confidence"),
            "source_count": entity.get("source_count", 0),
            "first_seen": entity.get("first_seen"),
            "last_seen": entity.get("last_seen"),
            "tags": json.loads(entity.get("tags_json") or "[]"),
            "evidence_ids": entity.get("evidence_ids", []),
            "canonical_updated_at": (
                entity.get("updated_at") or entity.get("created_at") or captured_at
            ),
            "sync_version": sync_version,
        }

    @staticmethod
    def _relation_properties(
        relation: dict[str, Any],
        sync_version: int,
        captured_at: str,
    ) -> dict[str, Any]:
        return {
            "relation_type": relation["relation_type"],
            "label": relation["label"],
            "confidence": relation.get("confidence"),
            "source_count": relation.get("source_count", 0),
            "evidence_count": relation.get("evidence_count", 0),
            "first_seen": relation.get("first_seen"),
            "last_seen": relation.get("last_seen"),
            "validation_status": relation.get("validation_status"),
            "evidence_ids": relation.get("evidence_ids", []),
            "projection": PROJECTION_NAME,
            "type": relation["relation_type"],
            "canonical_updated_at": (
                relation.get("updated_at")
                or relation.get("created_at")
                or captured_at
            ),
            "sync_version": sync_version,
        }

    @staticmethod
    def _evidence_properties(
        evidence: dict[str, Any],
        sync_version: int,
        captured_at: str,
    ) -> dict[str, Any]:
        allowed = (
            "doc_id",
            "chunk_id",
            "entity_id",
            "relation_id",
            "evidence_text",
            "evidence_type",
            "quote_start",
            "quote_end",
            "source_url",
            "source_type",
            "source_name",
            "published_at",
            "retrieved_at",
            "source_reliability",
            "language",
        )
        properties = {key: evidence.get(key) for key in allowed}
        properties.update(
            canonical_updated_at=evidence.get("created_at") or captured_at,
            sync_version=sync_version,
        )
        return properties

    @staticmethod
    def _unavailable_path(source: str, target: str, reason: str) -> dict[str, Any]:
        return {
            "source": source,
            "target": target,
            "engine": "unavailable",
            "reason": reason,
            "paths": [],
        }

    @staticmethod
    def _serialize_path(path: Any) -> dict[str, Any] | None:
        if path is None:
            return None
        try:
            nodes = [{"id": node.get("id"), **dict(node)} for node in path.nodes]
            edges = [
                {
                    "id": relation.get("id"),
                    "source": relation.start_node.get("id"),
                    "target": relation.end_node.get("id"),
                    **dict(relation),
                    "type": relation.get("relation_type"),
                }
                for relation in path.relationships
            ]
            return {
                "nodes": nodes,
                "edges": edges,
                "length": len(edges),
                "evidence_ids": sorted(
                    {
                        evidence_id
                        for relation in path.relationships
                        for evidence_id in (relation.get("evidence_ids") or [])
                    }
                ),
            }
        except (AttributeError, TypeError):
            return None
