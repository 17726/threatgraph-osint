from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from backend.app.services.neo4j_service import Neo4jService
from backend.tests.neo4j_fixtures import seed_canonical_graph


class FakeResult:
    def __init__(self, *, rows=None, single=None, data_rows=None):
        self._rows = rows or []
        self._single = single
        self._data_rows = data_rows

    def single(self):
        return self._single

    def data(self):
        return self._rows if self._data_rows is None else self._data_rows

    def __iter__(self):
        return iter(self._rows)

    def consume(self):
        return None


class FakeTransaction:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def run(self, query: str, **parameters: Any) -> FakeResult:
        self.driver.calls.append((query, parameters))
        if self.driver.fail_on and self.driver.fail_on in query:
            raise RuntimeError("bolt://neo4j:7687 secret-password")
        if "RETURN count(r) AS synced" in query:
            return FakeResult(single={"synced": len(parameters["records"])})
        return FakeResult()


class FakeSession:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute_write(self, callback: Callable, *args):
        self.driver.execute_write_count += 1
        if self.driver.before_write is not None:
            callback_before = self.driver.before_write
            self.driver.before_write = None
            callback_before()
        return callback(FakeTransaction(self.driver), *args)

    def run(self, query: str, **parameters: Any) -> FakeResult:
        self.driver.calls.append((query, parameters))
        if "RETURN 1 AS ok" in query:
            return FakeResult(single={"ok": 1})
        return FakeResult(
            rows=self.driver.path_rows,
            data_rows=self.driver.path_data_rows,
        )


class FakeDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.execute_write_count = 0
        self.before_write: Callable[[], None] | None = None
        self.fail_on: str | None = None
        self.path_rows: list[dict[str, Any]] = []
        self.path_data_rows: list[dict[str, Any]] | None = None

    def session(self):
        return FakeSession(self)

    def close(self):
        return None


def test_path_query_uses_raw_records_instead_of_lossy_result_data(tmp_path):
    class FakeNode(dict):
        pass

    class FakeRelationship(dict):
        def __init__(self, source, target):
            super().__init__(
                id="rel-1",
                relation_type="USES",
                evidence_ids=["ev-1"],
            )
            self.start_node = source
            self.end_node = target

    source = FakeNode(id="apt_group:apt28", name="APT28")
    target = FakeNode(id="malware:x-agent", name="X-Agent")
    path = type(
        "FakePath",
        (),
        {
            "nodes": [source, target],
            "relationships": [FakeRelationship(source, target)],
        },
    )()
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    service.rebuild()
    driver.path_rows = [{"p": path}]
    # neo4j.Result.data() 会把 Path 有损转换为 list，不能用于路径序列化。
    driver.path_data_rows = [{"p": []}]

    result = service.get_path(
        "apt_group:apt28",
        "malware:x-agent",
        max_depth=1,
    )

    assert result["engine"] == "neo4j"
    assert result["paths"][0]["length"] == 1
    assert result["paths"][0]["evidence_ids"] == ["ev-1"]


def test_rebuild_scopes_delete_and_uses_one_write_transaction(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()

    result = Neo4jService(db_path, driver=driver).rebuild()

    assert result["status"] == "succeeded"
    assert result["nodes"] == 2
    assert result["edges"] == 1
    assert result["evidence"] == 1
    assert driver.execute_write_count == 1
    queries = [query for query, _parameters in driver.calls]
    assert any(
        "MATCH ()-[r:THREAT_RELATION {projection: $projection}]-() DELETE r"
        in query
        for query in queries
    )
    assert "MATCH (n:ThreatGraphProjection) DELETE n" in queries
    assert not any("DETACH DELETE n" in query for query in queries)
    assert "MATCH (n) DETACH DELETE n" not in queries
    assert any("CREATE CONSTRAINT threatgraph_projection_entity_id" in query for query in queries)
    assert any("CREATE CONSTRAINT threatgraph_projection_evidence_id" in query for query in queries)
    assert any("CREATE INDEX threatgraph_projection_relation_id" in query for query in queries)
    entity_parameters = next(
        parameters
        for query, parameters in driver.calls
        if "MERGE (n:ThreatGraphProjection:ThreatEntity" in query
    )
    entity_properties = entity_parameters["records"][0]["properties"]
    assert entity_properties["sync_version"] == result["watermark"]
    assert entity_properties["canonical_updated_at"]
    relation_parameters = next(
        parameters
        for query, parameters in driver.calls
        if "MERGE (s)-[r:THREAT_RELATION" in query
    )
    assert relation_parameters["records"][0]["properties"]["type"] == "USES"


def test_rebuild_keeps_change_committed_after_sqlite_snapshot_pending(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()

    def add_concurrent_change():
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """INSERT INTO entities (
                     entity_id, name, type, aliases_json, description,
                     confidence, source_count, tags_json
                   ) VALUES ('tool:new', 'New Tool', 'TOOL', '[]', '', 0.7, 1, '[]')"""
            )

    driver.before_write = add_concurrent_change
    service = Neo4jService(db_path, driver=driver)

    result = service.rebuild()
    status = service.status()

    assert result["status"] == "succeeded"
    assert status["watermark"] == result["watermark"]
    assert status["pending_changes"] == 1


def test_incremental_requires_completed_full_rebuild(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()

    result = Neo4jService(db_path, driver=driver).sync_incremental()

    assert result["status"] == "requires_rebuild"
    assert driver.execute_write_count == 0


def test_incremental_is_idempotent_and_advances_watermark(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    rebuilt = service.rebuild()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE entities SET description = 'updated' WHERE entity_id = ?",
            ("apt_group:apt28",),
        )

    first = service.sync_incremental()
    second = service.sync_incremental()

    assert first["status"] == "succeeded"
    assert first["changes"] == 1
    assert first["watermark"] > rebuilt["watermark"]
    assert second == {
        "status": "succeeded",
        "changes": 0,
        "watermark": first["watermark"],
    }


def test_evidence_delete_refreshes_owner_evidence_ids(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    service.rebuild()
    driver.calls.clear()
    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM evidence WHERE evidence_id = 'ev-1'")

    result = service.sync_incremental()

    relation_parameters = next(
        parameters
        for query, parameters in driver.calls
        if "MERGE (s)-[r:THREAT_RELATION" in query
    )
    assert result["status"] == "succeeded"
    assert relation_parameters["records"][0]["properties"]["evidence_ids"] == []
    evidence_delete_query = next(
        query
        for query, _parameters in driver.calls
        if "MATCH (e:ThreatGraphProjection:ThreatEvidence" in query
    )
    assert "DETACH" not in evidence_delete_query
    assert "DELETE e" in evidence_delete_query


def test_incremental_relation_replacement_is_scoped_to_projection(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    service.rebuild()
    driver.calls.clear()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO entities (entity_id, name, type) VALUES (?, ?, ?)",
            ("tool:new", "New Tool", "TOOL"),
        )
        connection.execute(
            "UPDATE relations SET target_entity_id = ? WHERE relation_id = ?",
            ("tool:new", "rel:apt_group:apt28:USES:malware:x-agent"),
        )

    result = service.sync_incremental()

    queries = [query for query, _parameters in driver.calls]
    scoped_delete_index = next(
        index
        for index, query in enumerate(queries)
        if "MATCH (:ThreatGraphProjection)-[r:THREAT_RELATION" in query
    )
    upsert_index = next(
        index
        for index, query in enumerate(queries)
        if "MERGE (s)-[r:THREAT_RELATION" in query
    )
    assert result["status"] == "succeeded"
    assert scoped_delete_index < upsert_index
    assert "projection: $projection" in queries[scoped_delete_index]
    assert "MATCH (s:ThreatGraphProjection:ThreatEntity" in queries[upsert_index]
    assert "MATCH (t:ThreatGraphProjection:ThreatEntity" in queries[upsert_index]
    assert "{id: record.id, projection: $projection}" in queries[upsert_index]
    assert driver.calls[upsert_index][1]["projection"] == "threatgraph-osint"


def test_incremental_entity_delete_does_not_detach_external_relations(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    service.rebuild()
    driver.calls.clear()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "DELETE FROM entities WHERE entity_id = 'malware:x-agent'"
        )

    result = service.sync_incremental()

    entity_delete_query = next(
        query
        for query, _parameters in driver.calls
        if "MATCH (n:ThreatGraphProjection:ThreatEntity" in query
    )
    assert result["status"] == "succeeded"
    assert "DETACH" not in entity_delete_query
    assert "DELETE n" in entity_delete_query


def test_concurrent_incremental_syncs_are_serialized(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    service.rebuild()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE entities SET description = 'first' WHERE entity_id = ?",
            ("apt_group:apt28",),
        )

    first_write_entered = threading.Event()
    release_first_write = threading.Event()

    def block_first_write():
        first_write_entered.set()
        assert release_first_write.wait(timeout=2)

    driver.before_write = block_first_write
    results = []
    first = threading.Thread(
        target=lambda: results.append(service.sync_incremental()),
    )
    first.start()
    assert first_write_entered.wait(timeout=1)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE entities SET description = 'second' WHERE entity_id = ?",
            ("apt_group:apt28",),
        )

    second_attempted = threading.Event()

    def run_second():
        second_attempted.set()
        results.append(service.sync_incremental())

    second = threading.Thread(target=run_second)
    second.start()
    assert second_attempted.wait(timeout=1)
    second.join(timeout=0.1)

    assert second.is_alive(), "第二次同步不应越过正在执行的写事务"
    assert driver.execute_write_count == 2
    release_first_write.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive() and not second.is_alive()
    assert all(result["status"] == "succeeded" for result in results)
    assert service.status()["pending_changes"] == 0


def test_incremental_failure_keeps_watermark_and_sanitizes_error(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)
    rebuilt = service.rebuild()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE entities SET description = 'updated' WHERE entity_id = ?",
            ("apt_group:apt28",),
        )
    driver.fail_on = "MERGE"

    result = service.sync_incremental()
    status = service.status()

    assert result == {
        "status": "failed",
        "reason": "neo4j_sync_failed",
        "watermark": rebuilt["watermark"],
    }
    assert status["watermark"] == rebuilt["watermark"]
    assert status["status"] == "failed"
    assert status["error"] == "neo4j_sync_failed"
    assert "secret-password" not in str(result)


def test_sync_state_schema_records_attempt_and_full_sync_times(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_canonical_graph(db_path)
    service = Neo4jService(db_path, driver=FakeDriver())

    service.rebuild()

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM sync_state WHERE state_key = 'neo4j'"
        ).fetchone()
    assert row["status"] == "succeeded"
    assert row["last_attempt_at"]
    assert row["last_success_at"]
    assert row["last_full_sync_at"]
    assert row["error_message"] is None
