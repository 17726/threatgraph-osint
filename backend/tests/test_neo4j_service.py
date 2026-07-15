from __future__ import annotations

import sqlite3

from backend.app.services.demo_store import DemoStore
from backend.app.services.neo4j_service import Neo4jService


class FakeResult:
    def __init__(self, rows=None, single=None):
        self._rows = rows or []
        self._single = single

    def single(self):
        return self._single

    def data(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def run(self, query, **parameters):
        self.calls.append((query, parameters))
        if "RETURN 1 AS ok" in query:
            return FakeResult(single={"ok": 1})
        if "endpoints_match" in query:
            return FakeResult(single={"endpoints_match": parameters.get("target") != "entity:missing"})
        return FakeResult()


class FakeDriver:
    def __init__(self):
        self.calls = []
        self.closed = False

    def session(self):
        return FakeSession(self.calls)

    def close(self):
        self.closed = True


def test_health_is_false_when_neo4j_driver_is_unavailable(tmp_path):
    service = Neo4jService(tmp_path / "graph.db", driver=None)

    assert service.health() == {"available": False, "status": "disconnected"}


def test_rebuild_merges_sqlite_canonical_graph(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)

    result = service.rebuild()

    assert result["status"] == "succeeded"
    assert result["nodes"] >= 1
    assert result["edges"] >= 1
    queries = [query for query, _ in driver.calls]
    assert any("MERGE (n:Entity" in query for query in queries)
    assert any("MERGE (s)-[r:RELATES" in query for query in queries)


def test_incremental_sync_advances_watermark_only_after_success(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)

    result = service.sync_incremental()
    assert result["status"] == "succeeded"
    with sqlite3.connect(db_path) as connection:
        watermark = connection.execute(
            "SELECT watermark FROM sync_state WHERE state_key = 'neo4j'"
        ).fetchone()[0]
        changes = connection.execute("SELECT max(change_id) FROM graph_changes").fetchone()[0]
    assert watermark == changes

    class FailingDriver(FakeDriver):
        def session(self):
            session = super().session()
            original = session.run
            def run(query, **parameters):
                if "MERGE" in query:
                    raise RuntimeError("neo4j down")
                return original(query, **parameters)
            session.run = run
            return session

    failing = Neo4jService(db_path, driver=FailingDriver())
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE entities SET description = description || ' changed' WHERE entity_id = ?", ("apt_group:apt28",))
        connection.commit()
    before = service.get_watermark()
    failed = failing.sync_incremental()
    assert failed["status"] == "failed"
    assert failing.get_watermark() == before


def test_rebuild_projects_evidence_nodes_and_relation_type(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    result = Neo4jService(db_path, driver=driver).rebuild()

    assert result["status"] == "succeeded"
    calls = driver.calls
    evidence_call = next((params for query, params in calls if "Evidence" in query), None)
    assert evidence_call["id"] == "ev_apt28_profile_001"
    relation_calls = [params for query, params in calls if "MERGE (s)-[r:RELATES" in query]
    assert {params["properties"]["relation_type"] for params in relation_calls} >= {"USES", "TARGETS"}


def test_incremental_sync_projects_evidence_changes(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE evidence SET evidence_text = evidence_text || ' updated' WHERE evidence_id = ?",
            ("ev_apt28_profile_001",),
        )
        connection.commit()
    result = service.sync_incremental()

    assert result["status"] == "succeeded"
    assert any("Evidence" in query for query, _ in driver.calls)


def test_path_serialization_uses_relation_type_and_evidence_ids():
    class FakeNode(dict):
        pass

    class FakeRelationship(dict):
        def __init__(self, start_node, end_node):
            super().__init__(id="rel-1", relation_type="USES", evidence_ids=["ev-1"])
            self.start_node = start_node
            self.end_node = end_node

    source = FakeNode(id="source")
    target = FakeNode(id="target")
    path = type("FakePath", (), {
        "nodes": [source, target],
        "relationships": [FakeRelationship(source, target)],
    })()

    serialized = Neo4jService._serialize_path(path)

    assert serialized["edges"][0]["type"] == "USES"
    assert serialized["evidence_ids"] == ["ev-1"]


def test_path_query_uses_parameterized_depth_and_returns_compatible_path_shape(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)

    result = service.get_path(
        "apt_group:apt28",
        "malware:x-agent",
        max_depth=3,
        relation_types=["USES"],
        min_confidence=0.8,
    )

    assert result["engine"] == "neo4j"
    query, parameters = next((query, params) for query, params in driver.calls if "shortestPath" in query)
    assert "[*..$max_depth]" not in query
    assert "rel.relation_type IN $relation_types" in query
    assert parameters["max_depth"] == 3
    assert parameters["relation_types"] == ["USES"]


def test_incremental_relation_sync_does_not_advance_watermark_when_endpoint_is_missing(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE relations SET target_entity_id = ? WHERE relation_id = ?",
            ("entity:missing", "rel:apt_group:apt28:USES:technique:t1566"),
        )
        connection.commit()

    result = service.sync_incremental()

    assert result["status"] == "failed"
    assert service.get_watermark() == 0
    assert not any("MERGE (s)-[r:RELATES" in query for query, _ in driver.calls)


def test_incremental_relation_sync_checks_endpoints_after_entities_in_same_batch(tmp_path):
    db_path = tmp_path / "graph.db"
    DemoStore(db_path).initialize()
    driver = FakeDriver()
    service = Neo4jService(db_path, driver=driver)

    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM graph_changes")
        connection.execute("UPDATE sync_state SET watermark = 0 WHERE state_key = 'neo4j'")
        connection.execute(
            "INSERT INTO entities (entity_id, name, type) VALUES (?, ?, ?)",
            ("entity:new", "New Entity", "ORGANIZATION"),
        )
        connection.execute(
            "INSERT INTO relations (relation_id, source_entity_id, target_entity_id, relation_type, label) "
            "VALUES (?, ?, ?, ?, ?)",
            ("rel:new", "apt_group:apt28", "entity:new", "USES", "使用"),
        )
        connection.commit()

    result = service.sync_incremental()

    assert result["status"] == "succeeded"
    endpoint_indexes = [index for index, (query, _) in enumerate(driver.calls) if "endpoints_match" in query]
    relation_indexes = [index for index, (query, _) in enumerate(driver.calls) if "MERGE (s)-[r:RELATES" in query]
    assert endpoint_indexes
    assert relation_indexes
    assert endpoint_indexes[-1] < relation_indexes[-1]
