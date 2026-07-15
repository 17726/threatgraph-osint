from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

try:
    from neo4j import GraphDatabase
except ImportError:  # optional dependency
    GraphDatabase = None


class Neo4jService:
    """将 SQLite canonical graph 同步为可重建的 Neo4j 查询投影。"""

    def __init__(self, db_path: str | Path, driver: Any = None, uri: str | None = None, auth: tuple[str, str] | None = None) -> None:
        self.db_path = Path(db_path)
        self.driver = driver
        if self.driver is None and GraphDatabase is not None and uri:
            self.driver = GraphDatabase.driver(uri, auth=auth)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def health(self) -> dict[str, Any]:
        if self.driver is None:
            return {"available": False, "status": "disconnected"}
        try:
            with self.driver.session() as session:
                session.run("RETURN 1 AS ok").single()
            return {"available": True, "status": "connected"}
        except Exception:
            return {"available": False, "status": "disconnected"}

    def close(self) -> None:
        if self.driver is not None:
            self.driver.close()

    def get_watermark(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT watermark FROM sync_state WHERE state_key = 'neo4j'"
            ).fetchone()
        return int(row[0]) if row else 0

    def rebuild(self) -> dict[str, Any]:
        if self.driver is None:
            return {"status": "failed", "reason": "neo4j_unavailable"}
        with self.connect() as connection:
            entities = [dict(row) for row in connection.execute("SELECT * FROM entities ORDER BY entity_id")]
            relations = [dict(row) for row in connection.execute("SELECT * FROM relations ORDER BY relation_id")]
            evidence = [dict(row) for row in connection.execute("SELECT * FROM evidence ORDER BY evidence_id")]
            evidence_by_entity: dict[str, list[str]] = {}
            evidence_by_relation: dict[str, list[str]] = {}
            for item in evidence:
                if item["entity_id"]:
                    evidence_by_entity.setdefault(item["entity_id"], []).append(item["evidence_id"])
                if item["relation_id"]:
                    evidence_by_relation.setdefault(item["relation_id"], []).append(item["evidence_id"])
            for entity in entities:
                entity["evidence_ids"] = evidence_by_entity.get(entity["entity_id"], [])
            for relation in relations:
                relation["evidence_ids"] = evidence_by_relation.get(relation["relation_id"], [])
        try:
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                for entity in entities:
                    session.run(
                        "MERGE (n:Entity {id: $id}) SET n += $properties",
                        id=entity["entity_id"], properties=self._entity_properties(entity),
                    )
                for evidence_item in evidence:
                    session.run(
                        "MERGE (e:Evidence {id: $id}) SET e += $properties",
                        id=evidence_item["evidence_id"], properties=self._evidence_properties(evidence_item),
                    )
                for relation in relations:
                    session.run(
                        "MATCH (s:Entity {id: $source}), (t:Entity {id: $target}) "
                        "MERGE (s)-[r:RELATES {id: $id}]->(t) SET r += $properties",
                        source=relation["source_entity_id"], target=relation["target_entity_id"],
                        id=relation["relation_id"], properties=self._relation_properties(relation),
                    )
            with self.connect() as connection:
                watermark_row = connection.execute("SELECT coalesce(max(change_id), 0) FROM graph_changes").fetchone()
                watermark = int(watermark_row[0]) if watermark_row and watermark_row[0] is not None else 0
                connection.execute(
                    "UPDATE sync_state SET watermark = ?, updated_at = CURRENT_TIMESTAMP WHERE state_key = 'neo4j'",
                    (watermark,),
                )
                connection.commit()
            return {"status": "succeeded", "nodes": len(entities), "edges": len(relations), "watermark": watermark}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc)}

    def sync_incremental(self) -> dict[str, Any]:
        if self.driver is None:
            return {"status": "failed", "reason": "neo4j_unavailable"}
        watermark = self.get_watermark()
        with self.connect() as connection:
            changes = [dict(row) for row in connection.execute(
                "SELECT * FROM graph_changes WHERE change_id > ? ORDER BY change_id", (watermark,)
            )]
            records = []
            for change in changes:
                if change["operation"] == "delete":
                    records.append(change | {"record": None})
                    continue
                table = change["table_name"]
                key = {"entities": "entity_id", "relations": "relation_id", "evidence": "evidence_id"}[table]
                record = connection.execute(f"SELECT * FROM {table} WHERE {key} = ?", (change["record_id"],)).fetchone()
                records.append(change | {"record": dict(record) if record else None})
        try:
            with self.driver.session() as session:
                for change in records:
                    record = change["record"]
                    if change["table_name"] == "entities":
                        if record is None:
                            session.run("MATCH (n:Entity {id: $id}) DETACH DELETE n", id=change["record_id"])
                        else:
                            session.run("MERGE (n:Entity {id: $id}) SET n += $properties", id=record["entity_id"], properties=self._entity_properties(record))
                    elif change["table_name"] == "evidence":
                        if record is None:
                            session.run("MATCH (e:Evidence {id: $id}) DETACH DELETE e", id=change["record_id"])
                        else:
                            session.run("MERGE (e:Evidence {id: $id}) SET e += $properties", id=record["evidence_id"], properties=self._evidence_properties(record))
                    elif record is not None:
                        endpoints = session.run(
                            "MATCH (s:Entity {id: $source}), (t:Entity {id: $target}) "
                            "RETURN count(s) = 1 AND count(t) = 1 AS endpoints_match",
                            source=record["source_entity_id"], target=record["target_entity_id"],
                        ).single()
                        if not endpoints or not endpoints["endpoints_match"]:
                            raise RuntimeError(
                                "relation endpoints missing: "
                                f"{record['source_entity_id']} -> {record['target_entity_id']}"
                            )
                        session.run(
                            "MATCH (s:Entity {id: $source}), (t:Entity {id: $target}) "
                            "MERGE (s)-[r:RELATES {id: $id}]->(t) SET r += $properties",
                            source=record["source_entity_id"], target=record["target_entity_id"],
                            id=record["relation_id"], properties=self._relation_properties(record),
                        )
                    else:
                        session.run("MATCH ()-[r:RELATES {id: $id}]-() DELETE r", id=change["record_id"])
            new_watermark = changes[-1]["change_id"] if changes else watermark
            with self.connect() as connection:
                connection.execute(
                    "UPDATE sync_state SET watermark = ?, updated_at = CURRENT_TIMESTAMP WHERE state_key = 'neo4j'",
                    (new_watermark,),
                )
                connection.commit()
            return {"status": "succeeded", "changes": len(changes), "watermark": new_watermark}
        except Exception as exc:
            return {"status": "failed", "reason": str(exc), "watermark": watermark}

    def get_path(
        self,
        source: str,
        target: str,
        max_depth: int = 4,
        relation_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        if self.driver is None:
            return {"source": source, "target": target, "engine": "sqlite", "paths": []}
        query = (
            "MATCH p=shortestPath((s:Entity {id: $source})-[*..20]-(t:Entity {id: $target})) "
            "WHERE length(p) <= $max_depth "
            "AND (size($relation_types) = 0 OR all(rel IN relationships(p) WHERE rel.relation_type IN $relation_types)) "
            "AND ($min_confidence IS NULL OR all(rel IN relationships(p) WHERE rel.confidence >= $min_confidence)) "
            "RETURN p"
        )
        parameters = {
            "source": source,
            "target": target,
            "max_depth": max_depth,
            "relation_types": relation_types or [],
            "min_confidence": min_confidence,
        }
        try:
            with self.driver.session() as session:
                result = session.run(query, **parameters)
                paths = [self._serialize_path(row.get("p")) for row in result.data()]
            return {"source": source, "target": target, "engine": "neo4j", "paths": [path for path in paths if path]}
        except Exception:
            return {"source": source, "target": target, "engine": "sqlite", "paths": []}

    @staticmethod
    def _serialize_path(path: Any) -> dict[str, Any] | None:
        if path is None:
            return None
        try:
            nodes = [
                {"id": node.get("id"), **dict(node)}
                for node in path.nodes
            ]
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
                "evidence_ids": sorted({
                    evidence_id
                    for relation in path.relationships
                    for evidence_id in (relation.get("evidence_ids") or [])
                }),
            }
        except (AttributeError, TypeError):
            return None

    @staticmethod
    def _entity_properties(entity: dict[str, Any]) -> dict[str, Any]:
        properties = dict(entity)
        properties.pop("entity_id", None)
        for key in ("aliases_json", "tags_json"):
            if key in properties:
                properties[key.removesuffix("_json")] = json.loads(properties.pop(key) or "[]")
        return properties

    @staticmethod
    def _evidence_properties(evidence: dict[str, Any]) -> dict[str, Any]:
        properties = dict(evidence)
        properties.pop("evidence_id", None)
        return properties

    @staticmethod
    def _relation_properties(relation: dict[str, Any]) -> dict[str, Any]:
        properties = dict(relation)
        properties.pop("relation_id", None)
        properties.pop("source_entity_id", None)
        properties.pop("target_entity_id", None)
        return properties

