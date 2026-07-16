from backend.app.services.demo_store import DemoStore
from backend.app.services.graph_query_service import GraphQueryService


def seeded_service(tmp_path) -> GraphQueryService:
    store = DemoStore(tmp_path / "graph.db")
    with store.connect() as connection:
        store.seed_demo_data(connection)
    return GraphQueryService(store.db_path)


def assert_closed_graph(result: dict) -> None:
    visible = {node["id"] for node in result["nodes"]}
    assert all(
        edge["source"] in visible and edge["target"] in visible
        for edge in result["edges"]
    )


def test_graph_query_filters_entity_ids_within_target_bfs_scope(tmp_path):
    service = seeded_service(tmp_path)

    result = service.get_graph(
        target="APT28",
        entity_ids=["technique:t1566"],
        depth=2,
    )

    assert {node["id"] for node in result["nodes"]} == {
        "apt_group:apt28",
        "technique:t1566",
    }
    assert_closed_graph(result)


def test_entity_type_filter_never_returns_orphan_edges(tmp_path):
    result = seeded_service(tmp_path).get_graph(entity_types=["APT_GROUP"])

    assert result["nodes"]
    assert_closed_graph(result)


def test_target_matching_does_not_confuse_apt2_with_apt28(tmp_path):
    result = seeded_service(tmp_path).get_graph(target="APT2", depth=1)

    assert "apt_group:apt28" not in {node["id"] for node in result["nodes"]}
    assert result["nodes"] == []


def test_time_window_uses_interval_intersection(tmp_path):
    result = seeded_service(tmp_path).get_graph(
        target="APT28",
        first_seen_from="2020-01-01",
        last_seen_to="2021-12-31",
        depth=1,
    )

    assert "apt_group:apt28" in {node["id"] for node in result["nodes"]}
    assert "rel:apt_group:apt28:USES:technique:t1566" in {
        edge["id"] for edge in result["edges"]
    }


def test_time_window_keeps_items_with_unknown_dates(tmp_path):
    service = seeded_service(tmp_path)
    with service.connect() as connection:
        connection.execute(
            """
            INSERT INTO entities (
              entity_id, name, type, aliases_json, description, confidence,
              source_count, first_seen, last_seen, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "malware:unknown-date",
                "Unknown Date",
                "MALWARE",
                "[]",
                "",
                0.8,
                1,
                None,
                None,
                "[]",
            ),
        )
        connection.execute(
            """
            INSERT INTO relations (
              relation_id, source_entity_id, target_entity_id, relation_type,
              label, confidence, source_count, evidence_count, first_seen,
              last_seen, validation_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rel:apt28:unknown-date",
                "apt_group:apt28",
                "malware:unknown-date",
                "USES",
                "使用",
                0.8,
                1,
                0,
                None,
                None,
                "valid",
            ),
        )

    result = service.get_graph(
        target="APT28",
        first_seen_from="2020-01-01",
        last_seen_to="2021-12-31",
        depth=1,
    )

    assert "malware:unknown-date" in {node["id"] for node in result["nodes"]}
    assert "rel:apt28:unknown-date" in {edge["id"] for edge in result["edges"]}


def test_limit_preserves_target_and_graph_closure(tmp_path):
    result = seeded_service(tmp_path).get_graph(
        target="malware:x-agent",
        depth=1,
        limit=2,
    )

    assert {node["id"] for node in result["nodes"]} == {
        "malware:x-agent",
        "apt_group:apt28",
    }
    assert_closed_graph(result)


def test_limit_one_keeps_target_even_when_sorted_after_neighbor(tmp_path):
    result = seeded_service(tmp_path).get_graph(
        target="malware:x-agent",
        depth=1,
        limit=1,
    )

    assert [node["id"] for node in result["nodes"]] == ["malware:x-agent"]
    assert result["edges"] == []


def test_neighbors_returns_center_direct_neighbors_and_connecting_edges(tmp_path):
    result = seeded_service(tmp_path).get_neighbors("technique:t1566", depth=1)

    assert {node["id"] for node in result["nodes"]} == {
        "technique:t1566",
        "apt_group:apt28",
    }
    assert [edge["id"] for edge in result["edges"]] == [
        "rel:apt_group:apt28:USES:technique:t1566"
    ]
    assert_closed_graph(result)


def test_source_filter_keeps_endpoints_required_by_supported_relation(tmp_path):
    service = seeded_service(tmp_path)
    with service.connect() as connection:
        connection.execute(
            "DELETE FROM evidence WHERE evidence_id != ?",
            ("ev_apt28_t1566_001",),
        )
        connection.execute(
            "UPDATE evidence SET entity_id = NULL WHERE evidence_id = ?",
            ("ev_apt28_t1566_001",),
        )

    result = service.get_graph(
        source_types=["knowledge_base"],
        languages=["zh"],
    )

    assert {node["id"] for node in result["nodes"]} == {
        "apt_group:apt28",
        "technique:t1566",
    }
    assert [edge["id"] for edge in result["edges"]] == [
        "rel:apt_group:apt28:USES:technique:t1566"
    ]
    assert_closed_graph(result)


def test_path_query_supports_depth_relation_and_confidence_filters(tmp_path):
    result = seeded_service(tmp_path).get_path(
        "apt_group:apt28",
        "malware:x-agent",
        max_depth=2,
        relation_types=["USES"],
        min_confidence=0.8,
    )

    assert result["engine"] == "sqlite"
    assert result["paths"][0]["length"] == 1
    assert result["paths"][0]["evidence_ids"]
