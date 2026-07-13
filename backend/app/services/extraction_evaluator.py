"""Entity and relation extraction evaluation against manually reviewed golden data."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from scripts.validate_extraction_result import ALLOWED_RELATIONS


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GOLDEN_SCHEMA_PATH = REPO_ROOT / "docs/schemas/golden.schema.json"


def validate_golden_schema(
    golden: dict[str, Any],
    schema_path: Path | None = None,
) -> list[str]:
    validator = Draft202012Validator(
        json.loads((schema_path or DEFAULT_GOLDEN_SCHEMA_PATH).read_text(encoding="utf-8"))
    )
    return [
        f"{'.'.join(str(part) for part in error.path) or '$'}: {error.message}"
        for error in sorted(validator.iter_errors(golden), key=lambda item: list(item.path))
    ]


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = normalized.strip("\"'`")
    return re.sub(r"\s+", " ", normalized)


def _entity_names(entity: dict[str, Any]) -> set[str]:
    values = [entity.get("name", ""), *entity.get("aliases", [])]
    return {normalize_name(value) for value in values if isinstance(value, str) and value.strip()}


def _entity_match_score(predicted: dict[str, Any], golden: dict[str, Any]) -> int:
    if predicted.get("type") != golden.get("type"):
        return 0
    predicted_name = normalize_name(predicted.get("name", ""))
    golden_name = normalize_name(golden.get("name", ""))
    if predicted_name and predicted_name == golden_name:
        return 3
    if _entity_names(predicted) & _entity_names(golden):
        return 2
    return 0


def _match_entities(
    predicted: list[dict[str, Any]],
    golden: list[dict[str, Any]],
) -> dict[int, int]:
    candidates: list[tuple[int, int, int]] = []
    for predicted_index, predicted_entity in enumerate(predicted):
        for golden_index, golden_entity in enumerate(golden):
            score = _entity_match_score(predicted_entity, golden_entity)
            if score:
                candidates.append((-score, predicted_index, golden_index))

    matches: dict[int, int] = {}
    matched_golden: set[int] = set()
    for _negative_score, predicted_index, golden_index in sorted(candidates):
        if predicted_index in matches or golden_index in matched_golden:
            continue
        matches[predicted_index] = golden_index
        matched_golden.add(golden_index)
    return matches


def _entity_lookup(entities: list[dict[str, Any]]) -> dict[tuple[str, str], list[int]]:
    lookup: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, entity in enumerate(entities):
        entity_type = entity.get("type", "")
        for name in _entity_names(entity):
            lookup[(entity_type, name)].append(index)
    return lookup


def _resolve_endpoint(
    lookup: dict[tuple[str, str], list[int]],
    name: str,
    entity_type: str,
) -> int | None:
    matches = lookup.get((entity_type, normalize_name(name)), [])
    return matches[0] if len(matches) == 1 else None


def _relation_signature(
    relation: dict[str, Any],
    entity_lookup: dict[tuple[str, str], list[int]],
) -> tuple[int, str, int] | None:
    head_index = _resolve_endpoint(
        entity_lookup,
        relation.get("head_name", ""),
        relation.get("head_type", ""),
    )
    tail_index = _resolve_endpoint(
        entity_lookup,
        relation.get("tail_name", ""),
        relation.get("tail_type", ""),
    )
    if head_index is None or tail_index is None:
        return None
    return head_index, relation.get("relation_type", ""), tail_index


def _metric_counts(true_positive: int, predicted: int, golden: int) -> dict[str, int | float]:
    precision = true_positive / predicted if predicted else (1.0 if golden == 0 else 0.0)
    recall = true_positive / golden if golden else (1.0 if predicted == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "predicted": predicted,
        "golden": golden,
        "true_positive": true_positive,
        "false_positive": predicted - true_positive,
        "false_negative": golden - true_positive,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _entity_summary(chunk_id: str, entity: dict[str, Any]) -> dict[str, str]:
    return {
        "chunk_id": chunk_id,
        "name": entity.get("name", ""),
        "type": entity.get("type", ""),
    }


def _relation_summary(chunk_id: str, relation: dict[str, Any]) -> dict[str, str]:
    return {
        "chunk_id": chunk_id,
        "head_name": relation.get("head_name", ""),
        "head_type": relation.get("head_type", ""),
        "relation_type": relation.get("relation_type", ""),
        "tail_name": relation.get("tail_name", ""),
        "tail_type": relation.get("tail_type", ""),
    }


def _breakdown(
    predicted_types: list[str],
    golden_types: list[str],
    matched_types: list[str],
) -> dict[str, dict[str, int | float]]:
    result: dict[str, dict[str, int | float]] = {}
    for item_type in sorted(set(predicted_types) | set(golden_types)):
        result[item_type] = _metric_counts(
            matched_types.count(item_type),
            predicted_types.count(item_type),
            golden_types.count(item_type),
        )
    return result


def validate_golden_payload(
    golden: dict[str, Any],
    *,
    document: dict[str, Any] | None = None,
) -> list[str]:
    """Validate golden relation direction, endpoints, and optional evidence spans."""
    errors: list[str] = []
    doc_ids = set(golden.get("doc_ids", []))
    clean_text = document.get("clean_text", "") if document else ""
    if document and document.get("doc_id") not in doc_ids:
        errors.append("document.doc_id 不在 golden.doc_ids 中")

    for chunk_index, chunk in enumerate(golden.get("chunks", [])):
        chunk_id = chunk.get("chunk_id", f"chunks[{chunk_index}]")
        chunk_doc_id = chunk.get("doc_id", "")
        if chunk_doc_id not in doc_ids:
            errors.append(f"{chunk_id}: doc_id 不在 golden.doc_ids 中")

        entities = chunk.get("entities", [])
        known_entities = {
            (name, entity.get("type"))
            for entity in entities
            for name in [entity.get("name"), *entity.get("aliases", [])]
            if name and entity.get("type")
        }
        for relation_index, relation in enumerate(chunk.get("relations", [])):
            prefix = f"{chunk_id}.relations[{relation_index}]"
            relation_type = relation.get("relation_type")
            head_type = relation.get("head_type")
            tail_type = relation.get("tail_type")
            rule = ALLOWED_RELATIONS.get(relation_type)
            if rule is None:
                errors.append(f"{prefix}: 未知关系类型 {relation_type!r}")
            elif relation_type != "RELATED_TO" and (head_type, tail_type) not in rule["pairs"]:
                errors.append(
                    f"{prefix}: 不允许类型组合 {head_type} -> {relation_type} -> {tail_type}"
                )

            if (relation.get("head_name"), head_type) not in known_entities:
                errors.append(f"{prefix}: 主体未在同一 chunk 的 golden entities 中声明")
            if (relation.get("tail_name"), tail_type) not in known_entities:
                errors.append(f"{prefix}: 客体未在同一 chunk 的 golden entities 中声明")

        if document is None:
            continue
        for collection_name in ("entities", "relations"):
            for item_index, item in enumerate(chunk.get(collection_name, [])):
                prefix = f"{chunk_id}.{collection_name}[{item_index}]"
                evidence = item.get("evidence_text", "")
                start = item.get("char_start")
                end = item.get("char_end")
                if not evidence or evidence not in clean_text:
                    errors.append(f"{prefix}: evidence_text 未出现在 document.clean_text 中")
                    continue
                if start is None and end is None:
                    continue
                if not isinstance(start, int) or not isinstance(end, int):
                    errors.append(f"{prefix}: char_start/char_end 必须同时为整数或 null")
                elif not (0 <= start < end <= len(clean_text)):
                    errors.append(f"{prefix}: 字符范围超出 document.clean_text")
                elif clean_text[start:end] != evidence:
                    errors.append(f"{prefix}: 字符范围与 evidence_text 不一致")
    return errors


def evaluate_extraction(
    extraction_result: dict[str, Any],
    golden: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate names/types and typed relation endpoints with one-to-one matching."""
    doc_id = extraction_result.get("doc_id", "")
    if doc_id not in golden.get("doc_ids", []):
        raise ValueError(f"extraction_result.doc_id {doc_id!r} 不在 golden.doc_ids 中")

    predicted_chunks = {
        chunk["chunk_id"]: chunk for chunk in extraction_result.get("chunks", [])
    }
    golden_chunks = {chunk["chunk_id"]: chunk for chunk in golden.get("chunks", [])}

    predicted_entity_types: list[str] = []
    golden_entity_types: list[str] = []
    matched_entity_types: list[str] = []
    predicted_relation_types: list[str] = []
    golden_relation_types: list[str] = []
    matched_relation_types: list[str] = []

    missing_entities: list[dict[str, str]] = []
    extra_entities: list[dict[str, str]] = []
    missing_relations: list[dict[str, str]] = []
    extra_relations: list[dict[str, str]] = []

    for chunk_id in sorted(set(predicted_chunks) | set(golden_chunks)):
        predicted_chunk = predicted_chunks.get(chunk_id, {"entities": [], "relations": []})
        golden_chunk = golden_chunks.get(chunk_id, {"entities": [], "relations": []})
        predicted_entities = predicted_chunk.get("entities", [])
        golden_entities = golden_chunk.get("entities", [])
        predicted_relations = predicted_chunk.get("relations", [])
        golden_relations = golden_chunk.get("relations", [])

        predicted_entity_types.extend(entity.get("type", "") for entity in predicted_entities)
        golden_entity_types.extend(entity.get("type", "") for entity in golden_entities)
        predicted_relation_types.extend(
            relation.get("relation_type", "") for relation in predicted_relations
        )
        golden_relation_types.extend(relation.get("relation_type", "") for relation in golden_relations)

        entity_matches = _match_entities(predicted_entities, golden_entities)
        matched_golden_entities = set(entity_matches.values())
        matched_entity_types.extend(
            golden_entities[golden_index].get("type", "")
            for golden_index in entity_matches.values()
        )
        extra_entities.extend(
            _entity_summary(chunk_id, entity)
            for index, entity in enumerate(predicted_entities)
            if index not in entity_matches
        )
        missing_entities.extend(
            _entity_summary(chunk_id, entity)
            for index, entity in enumerate(golden_entities)
            if index not in matched_golden_entities
        )

        predicted_lookup = _entity_lookup(predicted_entities)
        golden_lookup = _entity_lookup(golden_entities)
        unmatched_golden_relations = set(range(len(golden_relations)))
        golden_relation_signatures = [
            _relation_signature(relation, golden_lookup) for relation in golden_relations
        ]

        for predicted_relation in predicted_relations:
            predicted_signature = _relation_signature(predicted_relation, predicted_lookup)
            translated_signature: tuple[int, str, int] | None = None
            if predicted_signature is not None:
                predicted_head, relation_type, predicted_tail = predicted_signature
                if predicted_head in entity_matches and predicted_tail in entity_matches:
                    translated_signature = (
                        entity_matches[predicted_head],
                        relation_type,
                        entity_matches[predicted_tail],
                    )

            matched_relation_index = next(
                (
                    index
                    for index in sorted(unmatched_golden_relations)
                    if golden_relation_signatures[index] == translated_signature
                ),
                None,
            )
            if matched_relation_index is None or translated_signature is None:
                extra_relations.append(_relation_summary(chunk_id, predicted_relation))
                continue

            unmatched_golden_relations.remove(matched_relation_index)
            matched_relation_types.append(
                golden_relations[matched_relation_index].get("relation_type", "")
            )

        missing_relations.extend(
            _relation_summary(chunk_id, golden_relations[index])
            for index in sorted(unmatched_golden_relations)
        )

    entity_metrics = _metric_counts(
        len(matched_entity_types),
        len(predicted_entity_types),
        len(golden_entity_types),
    )
    relation_metrics = _metric_counts(
        len(matched_relation_types),
        len(predicted_relation_types),
        len(golden_relation_types),
    )

    return {
        "schema_version": "1.0",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "extraction": {
            "run_id": extraction_result.get("run_id", ""),
            "doc_id": doc_id,
            "model_name": extraction_result.get("model_name", ""),
            "prompt_version": extraction_result.get("prompt_version", ""),
        },
        "golden": {
            "target_group": golden.get("target_group", ""),
            "doc_ids": golden.get("doc_ids", []),
        },
        "matching_policy": {
            "entity": "same chunk + same type + normalized name or alias overlap",
            "relation": "same chunk + matched typed endpoints + exact relation type",
            "evidence": "validated separately against document.clean_text; not part of F1 matching",
        },
        "entity_metrics": entity_metrics,
        "relation_metrics": relation_metrics,
        "entity_metrics_by_type": _breakdown(
            predicted_entity_types,
            golden_entity_types,
            matched_entity_types,
        ),
        "relation_metrics_by_type": _breakdown(
            predicted_relation_types,
            golden_relation_types,
            matched_relation_types,
        ),
        "errors": {
            "missing_entities": missing_entities,
            "extra_entities": extra_entities,
            "missing_relations": missing_relations,
            "extra_relations": extra_relations,
        },
    }
