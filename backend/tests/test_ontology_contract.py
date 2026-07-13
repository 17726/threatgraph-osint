import json
from pathlib import Path

from scripts.validate_extraction_result import ALLOWED_RELATIONS


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATHS = [
    ROOT / "docs/schemas/extraction-result.schema.json",
    ROOT / "docs/schemas/golden.schema.json",
    ROOT / "docs/schemas/graph.schema.json",
]


def test_all_json_schemas_share_the_current_entity_and_relation_enums():
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in SCHEMA_PATHS]
    entity_enums = [set(schema["$defs"]["entity_type"]["enum"]) for schema in schemas]
    relation_enums = [set(schema["$defs"]["relation_type"]["enum"]) for schema in schemas]

    assert all(values == entity_enums[0] for values in entity_enums)
    assert all(values == relation_enums[0] for values in relation_enums)
    assert "TARGET" not in entity_enums[0]
    assert {"INFRASTRUCTURE", "LOCATION", "FINANCIAL_ACCOUNT"} <= entity_enums[0]
    assert set(ALLOWED_RELATIONS) == relation_enums[0]


def test_crime_network_acceptance_fixture_uses_only_current_types_and_relations():
    fixture = json.loads(
        (ROOT / "data/examples/crime-network.acceptance.json").read_text(
            encoding="utf-8"
        )
    )
    relations = {
        relation["relation_type"]
        for chunk in fixture["chunks"]
        for relation in chunk["relations"]
    }
    entity_types = {
        entity["type"] for chunk in fixture["chunks"] for entity in chunk["entities"]
    }

    assert "TARGET" not in entity_types
    assert {"PERSON", "APT_GROUP", "FINANCIAL_ACCOUNT", "TECHNIQUE"} <= entity_types
    assert {"MEMBER_OF", "CONTROLS", "TRANSFERS_TO", "USES"} <= relations
