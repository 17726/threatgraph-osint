from scripts.seed_demo_data import seed_demo_data

from backend.app.services.graph_query_service import GraphQueryService


def test_graph_query_filters_entity_ids_within_target_bfs_scope(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(
        target="APT28",
        entity_ids=["technique:t1566"],
        depth=2,
    )

    assert {node["id"] for node in result["nodes"]} == {
        "apt_group:apt28",
        "technique:t1566",
    }
    assert all(
        edge["source"] in {"apt_group:apt28", "technique:t1566"}
        and edge["target"] in {"apt_group:apt28", "technique:t1566"}
        for edge in result["edges"]
    )
    assert result["filters"]["entity_ids"] == ["technique:t1566"]


def test_graph_query_entity_ids_without_target_keeps_only_selected_entities(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(entity_ids=["technique:t1566"])

    assert {node["id"] for node in result["nodes"]} == {"technique:t1566"}
    assert result["edges"] == []


def test_graph_query_returns_empty_graph_when_target_is_missing(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(target="does-not-exist")

    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["evidence"] == []


def test_graph_query_returns_empty_graph_when_target_is_excluded_by_entity_filter(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(
        target="APT28",
        entity_types=["MALWARE"],
    )

    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["evidence"] == []


def test_graph_query_source_filters_keep_only_evidence_supported_graph_items(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(
        source_types=["knowledge_base"],
        languages=["zh"],
    )

    evidence_ids = {item["id"] for item in result["evidence"]}
    assert result["nodes"]
    assert result["edges"]
    assert all(set(node["evidence_ids"]) & evidence_ids for node in result["nodes"])
    assert all(set(edge["evidence_ids"]) & evidence_ids for edge in result["edges"])
    assert all(
        item["entity_id"] in {node["id"] for node in result["nodes"]}
        or item["relation_id"] in {edge["id"] for edge in result["edges"]}
        for item in result["evidence"]
    )


def test_graph_query_supports_alias_filters_and_metadata(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(
        target="Fancy Bear",
        entity_types=["APT_GROUP"],
        tags=["apt"],
        source_types=["knowledge_base"],
        languages=["zh"],
        first_seen_from="2010-01-01",
        last_seen_to="2026-12-31",
        min_confidence=0.9,
        depth=1,
        limit=10,
    )

    assert result["engine"] == "sqlite"
    assert result["filters"]["target"] == "Fancy Bear"
    assert {node["id"] for node in result["nodes"]} == {"apt_group:apt28"}
    assert result["edges"] == []
    assert result["evidence"]
    assert result["stats"]["node_count"] == 1
    assert result["stats"]["edge_count"] == 0


def test_graph_query_filters_relation_type_and_confidence(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(
        target="apt_group:apt28",
        relation_types=["USES"],
        min_confidence=0.9,
        depth=2,
    )

    assert {edge["type"] for edge in result["edges"]} == {"USES"}
    assert all(edge["confidence"] >= 0.9 for edge in result["edges"])
    assert {node["id"] for node in result["nodes"]} >= {
        "apt_group:apt28",
        "technique:t1566",
    }


def test_graph_query_limit_and_evidence_source_filters(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_graph(
        source_types=["knowledge_base"],
        languages=["zh"],
        limit=2,
    )

    assert len(result["nodes"]) <= 2
    assert len(result["edges"]) <= 2
    assert result["evidence"]
    assert all(item["source_type"] == "knowledge_base" for item in result["evidence"])
    assert all(item["language"] == "zh" for item in result["evidence"])


def test_path_query_supports_depth_relation_and_confidence_filters(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)
    service = GraphQueryService(db_path)

    result = service.get_path(
        "apt_group:apt28",
        "malware:x-agent",
        max_depth=2,
        relation_types=["USES"],
        min_confidence=0.8,
    )

    assert result["engine"] == "sqlite"
    assert result["paths"]
    assert result["paths"][0]["length"] == 1
    assert all(edge["type"] == "USES" for edge in result["paths"][0]["edges"])
    assert all(edge["confidence"] >= 0.8 for edge in result["paths"][0]["edges"])
    assert result["paths"][0]["evidence_ids"]


def test_path_query_does_not_reuse_relation_ids_as_global_visited_state(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)
    service = GraphQueryService(db_path)

    result = service.get_path("technique:t1566", "malware:x-agent", max_depth=3)

    assert result["paths"]
    assert [node["id"] for node in result["paths"][0]["nodes"]] == [
        "technique:t1566",
        "apt_group:apt28",
        "malware:x-agent",
    ]


def test_path_query_respects_max_depth_and_returns_compatible_shape(tmp_path):
    db_path = tmp_path / "graph.db"
    seed_demo_data(db_path)

    result = GraphQueryService(db_path).get_path(
        "apt_group:apt28", "malware:x-agent", max_depth=0
    )

    assert result["paths"] == []
