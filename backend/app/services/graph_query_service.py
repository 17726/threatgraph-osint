from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any, Iterable


class GraphQueryService:
    """基于 SQLite canonical graph 的图查询服务。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def get_graph(
        self,
        target: str | None = None,
        entity_types: Iterable[str] | None = None,
        entity_ids: Iterable[str] | None = None,
        relation_types: Iterable[str] | None = None,
        tags: Iterable[str] | None = None,
        source_types: Iterable[str] | None = None,
        languages: Iterable[str] | None = None,
        first_seen_from: str | None = None,
        last_seen_to: str | None = None,
        min_confidence: float | None = None,
        depth: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        entity_types = list(entity_types or [])
        entity_ids = list(entity_ids or [])
        relation_types = list(relation_types or [])
        tags = list(tags or [])
        source_types = list(source_types or [])
        languages = list(languages or [])
        with self.connect() as connection:
            all_nodes = self._query_nodes(connection, [], [], None, None, None) if target else []
            nodes = self._query_nodes(connection, entity_types, tags, first_seen_from, last_seen_to, min_confidence)
            edges = self._query_edges(connection, relation_types, first_seen_from, last_seen_to, min_confidence)
            evidence = self._query_evidence(connection, source_types, languages)

        nodes = [self._node_from_row(row) for row in nodes]
        edges = [self._edge_from_row(row) for row in edges]
        evidence = [self._evidence_from_row(row) for row in evidence]
        self._attach_evidence(nodes, edges, evidence)

        if source_types or languages:
            candidate_node_ids = {node["id"] for node in nodes}
            edges = [
                edge
                for edge in edges
                if edge["evidence_ids"]
                and edge["source"] in candidate_node_ids
                and edge["target"] in candidate_node_ids
            ]
            supported_node_ids = {
                node["id"] for node in nodes if node["evidence_ids"]
            }
            supported_node_ids.update(
                endpoint
                for edge in edges
                for endpoint in (edge["source"], edge["target"])
            )
            nodes = [node for node in nodes if node["id"] in supported_node_ids]

        node_ids = {node["id"] for node in nodes}
        edges = self._closed_edges(edges, node_ids)

        target_ids: set[str] = set()
        visible_target_ids: set[str] = set()

        if target:
            target_ids = self._target_ids(
                [self._node_from_row(row) for row in all_nodes],
                target,
            )
            visible_target_ids = target_ids & {node["id"] for node in nodes}
            if not visible_target_ids:
                nodes = []
                edges = []
            else:
                visible_ids = self._nodes_at_depth(
                    visible_target_ids,
                    edges,
                    depth if depth is not None else 20,
                )
                nodes = [node for node in nodes if node["id"] in visible_ids]
                edges = self._closed_edges(edges, visible_ids)

        if entity_ids:
            selected_ids = set(entity_ids)
            if target:
                selected_ids &= {node["id"] for node in nodes}
                selected_ids.update(visible_target_ids)
            nodes = [node for node in nodes if node["id"] in selected_ids]
            node_ids = {node["id"] for node in nodes}
            edges = self._closed_edges(edges, node_ids)

        if limit is not None:
            if visible_target_ids:
                nodes = self._limit_nodes(nodes, edges, visible_target_ids, limit)
            else:
                nodes = nodes[:limit]
            node_ids = {node["id"] for node in nodes}
            edges = self._closed_edges(edges, node_ids)

        visible_node_ids = {node["id"] for node in nodes}
        visible_edge_ids = {edge["id"] for edge in edges}
        evidence = [
            item for item in evidence
            if (item["entity_id"] in visible_node_ids if item["entity_id"] else False)
            or (item["relation_id"] in visible_edge_ids if item["relation_id"] else False)
        ]
        return {
            "schema_version": "1.0",
            "nodes": nodes,
            "edges": edges,
            "evidence": evidence,
            "engine": "sqlite",
            "filters": {
                "target": target,
                "entity_types": entity_types,
                "entity_ids": entity_ids,
                "relation_types": relation_types,
                "tags": tags,
                "source_types": source_types,
                "languages": languages,
                "first_seen_from": first_seen_from,
                "last_seen_to": last_seen_to,
                "min_confidence": min_confidence,
                "depth": depth,
                "limit": limit,
            },
            "stats": {"node_count": len(nodes), "edge_count": len(edges), "evidence_count": len(evidence)},
        }

    def get_neighbors(
        self,
        entity_id: str,
        relation_types: Iterable[str] | None = None,
        source_types: Iterable[str] | None = None,
        languages: Iterable[str] | None = None,
        min_confidence: float | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """返回中心实体、直接邻居、连接边及相关证据。"""
        return self.get_graph(
            target=entity_id,
            relation_types=relation_types,
            source_types=source_types,
            languages=languages,
            min_confidence=min_confidence,
            depth=1,
            limit=limit,
        )

    def get_path(
        self,
        source: str,
        target: str,
        max_depth: int = 4,
        relation_types: Iterable[str] | None = None,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        relation_types = list(relation_types or [])
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM relations WHERE confidence >= ?",
                (min_confidence if min_confidence is not None else 0,),
            ).fetchall()
            if relation_types:
                rows = [row for row in rows if row["relation_type"] in relation_types]
            edge_rows = {row["relation_id"]: row for row in rows}
            node_rows = {
                row["entity_id"]: row
                for row in connection.execute("SELECT * FROM entities").fetchall()
            }
            evidence_rows = connection.execute("SELECT * FROM evidence").fetchall()

        queue = deque([(source, [source], [])])
        visited: set[str] = {source}
        while queue:
            current, node_path, edge_path = queue.popleft()
            if current == target:
                return self._path_result(source, target, node_path, edge_path, node_rows, edge_rows, evidence_rows)
            if len(edge_path) >= max_depth:
                continue
            for row in rows:
                if row["relation_id"] in edge_path:
                    continue
                if row["source_entity_id"] == current:
                    neighbor = row["target_entity_id"]
                elif row["target_entity_id"] == current:
                    neighbor = row["source_entity_id"]
                else:
                    continue
                new_nodes = node_path + [neighbor]
                new_edges = edge_path + [row["relation_id"]]
                if neighbor == target:
                    return self._path_result(source, target, new_nodes, new_edges, node_rows, edge_rows, evidence_rows)
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, new_nodes, new_edges))
        return {"source": source, "target": target, "engine": "sqlite", "paths": []}

    def _query_nodes(self, connection, entity_types, tags, first_seen_from, last_seen_to, min_confidence):
        clauses = []
        params: list[Any] = []
        if entity_types:
            clauses.append("type IN (" + ",".join("?" for _ in entity_types) + ")")
            params.extend(entity_types)
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(min_confidence)
        if first_seen_from:
            clauses.append("(last_seen IS NULL OR last_seen >= ?)")
            params.append(first_seen_from)
        if last_seen_to:
            clauses.append("(first_seen IS NULL OR first_seen <= ?)")
            params.append(last_seen_to)
        for tag in tags:
            clauses.append("EXISTS (SELECT 1 FROM json_each(tags_json) WHERE value = ?)")
            params.append(tag)
        sql = "SELECT * FROM entities" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY type, name"
        return connection.execute(sql, params).fetchall()

    def _query_edges(self, connection, relation_types, first_seen_from, last_seen_to, min_confidence):
        clauses = []
        params: list[Any] = []
        if relation_types:
            clauses.append("relation_type IN (" + ",".join("?" for _ in relation_types) + ")")
            params.extend(relation_types)
        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(min_confidence)
        if first_seen_from:
            clauses.append("(last_seen IS NULL OR last_seen >= ?)")
            params.append(first_seen_from)
        if last_seen_to:
            clauses.append("(first_seen IS NULL OR first_seen <= ?)")
            params.append(last_seen_to)
        sql = "SELECT * FROM relations" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY relation_id"
        return connection.execute(sql, params).fetchall()

    def _query_evidence(self, connection, source_types, languages):
        clauses = []
        params: list[Any] = []
        if source_types:
            clauses.append("source_type IN (" + ",".join("?" for _ in source_types) + ")")
            params.extend(source_types)
        if languages:
            clauses.append("language IN (" + ",".join("?" for _ in languages) + ")")
            params.extend(languages)
        sql = "SELECT * FROM evidence" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY evidence_id"
        return connection.execute(sql, params).fetchall()

    def _target_ids(self, nodes, target):
        normalized = target.strip().casefold()
        result = set()
        for node in nodes:
            node_id = node["id"].strip().casefold()
            name = node["name"].strip().casefold()
            aliases = [alias.strip().casefold() for alias in node["aliases"]]
            if normalized in {node_id, name, *aliases}:
                result.add(node["id"])
        return result

    def _closed_edges(self, edges, node_ids):
        return [
            edge
            for edge in edges
            if edge["source"] in node_ids and edge["target"] in node_ids
        ]

    def _limit_nodes(self, nodes, edges, roots, limit):
        distances = {root: 0 for root in roots}
        queue = deque(sorted(roots))
        while queue:
            current = queue.popleft()
            for edge in edges:
                if edge["source"] == current:
                    neighbor = edge["target"]
                elif edge["target"] == current:
                    neighbor = edge["source"]
                else:
                    continue
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        positions = {node["id"]: index for index, node in enumerate(nodes)}
        return sorted(
            nodes,
            key=lambda node: (
                distances.get(node["id"], len(nodes) + 1),
                positions[node["id"]],
            ),
        )[:limit]

    def _nodes_at_depth(self, roots, edges, depth):
        visible = set(roots)
        frontier = set(roots)
        for _ in range(max(depth, 0)):
            frontier = {neighbor for edge in edges if edge["source"] in frontier or edge["target"] in frontier for neighbor in (edge["source"], edge["target"])} - visible
            visible.update(frontier)
        return visible

    def _attach_evidence(self, nodes, edges, evidence):
        node_ids: dict[str, list[str]] = {}
        edge_ids: dict[str, list[str]] = {}
        for item in evidence:
            if item["entity_id"]:
                node_ids.setdefault(item["entity_id"], []).append(item["id"])
            if item["relation_id"]:
                edge_ids.setdefault(item["relation_id"], []).append(item["id"])
        for node in nodes:
            node["evidence_ids"] = node_ids.get(node["id"], [])
        for edge in edges:
            edge["evidence_ids"] = edge_ids.get(edge["id"], [])

    def _path_result(self, source, target, node_path, edge_path, node_rows, edge_rows, evidence_rows):
        nodes = [self._node_from_row(node_rows[node_id]) for node_id in node_path if node_id in node_rows]
        edges = [self._edge_from_row(edge_rows[edge_id]) for edge_id in edge_path]
        evidence = [row for row in evidence_rows if row["entity_id"] in node_path or row["relation_id"] in edge_path]
        self._attach_evidence(nodes, edges, [self._evidence_from_row(row) for row in evidence])
        return {"source": source, "target": target, "engine": "sqlite", "paths": [{"nodes": nodes, "edges": edges, "length": len(edge_path), "evidence_ids": list(dict.fromkeys([item["evidence_id"] for item in evidence]))}]}

    def _node_from_row(self, row):
        return {"id": row["entity_id"], "name": row["name"], "type": row["type"], "aliases": json.loads(row["aliases_json"]), "description": row["description"], "confidence": row["confidence"], "source_count": row["source_count"], "first_seen": row["first_seen"], "last_seen": row["last_seen"], "tags": json.loads(row["tags_json"]), "evidence_ids": []}

    def _edge_from_row(self, row):
        return {"id": row["relation_id"], "source": row["source_entity_id"], "target": row["target_entity_id"], "type": row["relation_type"], "label": row["label"], "confidence": row["confidence"], "source_count": row["source_count"], "evidence_count": row["evidence_count"], "first_seen": row["first_seen"], "last_seen": row["last_seen"], "validation_status": row["validation_status"], "evidence_ids": []}

    def _evidence_from_row(self, row):
        return {"id": row["evidence_id"], "doc_id": row["doc_id"], "chunk_id": row["chunk_id"], "entity_id": row["entity_id"], "relation_id": row["relation_id"], "text": row["evidence_text"], "source_url": row["source_url"], "source_type": row["source_type"], "source_name": row["source_name"], "evidence_type": row["evidence_type"], "quote_start": row["quote_start"], "quote_end": row["quote_end"], "published_at": row["published_at"], "retrieved_at": row["retrieved_at"], "source_reliability": row["source_reliability"], "language": row["language"]}
