import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_document_schema_uses_clean_text_contract() -> None:
    schema = load_json("docs/schemas/document.schema.json")

    assert "clean_text" in schema["required"]
    assert "raw_text" not in schema["required"]
    assert "clean_text" in schema["properties"]
    assert "raw_text" not in schema["properties"]


def test_document_schema_accepts_collection_item_identity() -> None:
    schema = load_json("docs/schemas/document.schema.json")

    assert schema["properties"]["collection_item_id"] == {
        "type": ["string", "null"]
    }


def test_document_example_hashes_clean_text() -> None:
    document = load_json("data/examples/document.apt28.thn.beardshell.example.json")

    assert "clean_text" in document
    assert "raw_text" not in document

    expected_hash = "sha256:" + hashlib.sha256(
        document["clean_text"].encode("utf-8")
    ).hexdigest()
    assert document["content_hash"] == expected_hash
