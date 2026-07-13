"""Entity and relation extraction evaluation against manually reviewed golden data."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from backend.app.services.artifact_naming import SCHEMA_VERSION, iso_timestamp, now_utc
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


def _add_flow_edge(
    graph: list[list[list[int]]],
    source: int,
    target: int,
    capacity: int,
    cost: int,
) -> None:
    graph[source].append([target, len(graph[target]), capacity, cost])
    graph[target].append([source, len(graph[source]) - 1, 0, -cost])


def _match_entities(
    predicted: list[dict[str, Any]],
    golden: list[dict[str, Any]],
) -> dict[int, int]:
    """Return maximum-cardinality, then maximum-score, one-to-one matches."""
    source = 0
    predicted_offset = 1
    golden_offset = predicted_offset + len(predicted)
    sink = golden_offset + len(golden)
    graph: list[list[list[int]]] = [[] for _ in range(sink + 1)]

    for predicted_index, predicted_entity in enumerate(predicted):
        _add_flow_edge(graph, source, predicted_offset + predicted_index, 1, 0)
        for golden_index, golden_entity in enumerate(golden):
            score = _entity_match_score(predicted_entity, golden_entity)
            if score:
                _add_flow_edge(
                    graph,
                    predicted_offset + predicted_index,
                    golden_offset + golden_index,
                    1,
                    -score,
                )
    for golden_index in range(len(golden)):
        _add_flow_edge(graph, golden_offset + golden_index, sink, 1, 0)

    while True:
        distances = [float("inf")] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distances[source] = 0

        for _ in range(len(graph) - 1):
            changed = False
            for node, edges in enumerate(graph):
                if distances[node] == float("inf"):
                    continue
                for edge_index, edge in enumerate(edges):
                    target, _reverse, capacity, cost = edge
                    candidate_distance = distances[node] + cost
                    if capacity > 0 and candidate_distance < distances[target]:
                        distances[target] = candidate_distance
                        previous[target] = (node, edge_index)
                        changed = True
            if not changed:
                break

        if previous[sink] is None:
            break

        node = sink
        while node != source:
            previous_node, edge_index = previous[node] or (-1, -1)
            edge = graph[previous_node][edge_index]
            edge[2] -= 1
            graph[node][edge[1]][2] += 1
            node = previous_node

    matches: dict[int, int] = {}
    for predicted_index in range(len(predicted)):
        predicted_node = predicted_offset + predicted_index
        for target, _reverse, capacity, cost in graph[predicted_node]:
            if golden_offset <= target < sink and cost < 0 and capacity == 0:
                matches[predicted_index] = target - golden_offset
                break
    return matches


def _index_unique_chunks(
    chunks: Any,
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(chunks, list):
        raise ValueError(f"{label}.chunks 必须是数组")
    indexed: dict[str, dict[str, Any]] = {}
    for chunk_index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise ValueError(f"{label}.chunks[{chunk_index}] 必须是对象")
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"{label}.chunks[{chunk_index}] 缺少有效 chunk_id")
        if chunk_id in indexed:
            raise ValueError(f"{label} 包含重复 chunk_id: {chunk_id}")
        indexed[chunk_id] = chunk
    return indexed


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


def _entity_summary(
    chunk_id: str,
    entity: dict[str, Any],
    *,
    source: str = "extraction_result",
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "chunk_id": chunk_id,
        "name": entity.get("name", ""),
        "type": entity.get("type", ""),
        "source": source,
    }
    if source == "candidate_audit":
        summary["audit_reason"] = entity.get("audit_reason", "")
        summary["validation_errors"] = entity.get("validation_errors", [])
    return summary


def _relation_summary(
    chunk_id: str,
    relation: dict[str, Any],
    *,
    source: str = "extraction_result",
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "chunk_id": chunk_id,
        "head_name": relation.get("head_name", ""),
        "head_type": relation.get("head_type", ""),
        "relation_type": relation.get("relation_type", ""),
        "tail_name": relation.get("tail_name", ""),
        "tail_type": relation.get("tail_type", ""),
        "source": source,
    }
    if source == "candidate_audit":
        summary["audit_reason"] = relation.get("audit_reason", "")
        summary["validation_errors"] = relation.get("validation_errors", [])
    return summary


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
    """Validate chunk identity, relation semantics, and document evidence spans."""
    errors: list[str] = []
    doc_ids = set(golden.get("doc_ids", []))
    clean_text = document.get("clean_text", "") if document else ""
    document_doc_id = document.get("doc_id") if document else None
    if document and document_doc_id not in doc_ids:
        errors.append("document.doc_id 不在 golden.doc_ids 中")

    seen_chunk_ids: set[str] = set()
    document_chunk_count = 0
    for chunk_index, chunk in enumerate(golden.get("chunks", [])):
        chunk_id = chunk.get("chunk_id", f"chunks[{chunk_index}]")
        if chunk_id in seen_chunk_ids:
            errors.append(f"golden 包含重复 chunk_id: {chunk_id}")
        seen_chunk_ids.add(chunk_id)

        chunk_doc_id = chunk.get("doc_id", "")
        if chunk_doc_id not in doc_ids:
            errors.append(f"{chunk_id}: doc_id 不在 golden.doc_ids 中")
        if document and chunk_doc_id == document_doc_id:
            document_chunk_count += 1

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

        if document is None or chunk_doc_id != document_doc_id:
            continue

        chunk_start = chunk.get("char_start")
        chunk_end = chunk.get("char_end")
        chunk_bounds: tuple[int, int] | None = None
        if chunk_start is None and chunk_end is None:
            pass
        elif not isinstance(chunk_start, int) or not isinstance(chunk_end, int):
            errors.append(f"{chunk_id}: char_start/char_end 必须同时为整数或 null")
        elif not (0 <= chunk_start < chunk_end <= len(clean_text)):
            errors.append(f"{chunk_id}: chunk 字符范围超出 document.clean_text")
        else:
            chunk_bounds = (chunk_start, chunk_end)

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
                    if chunk_bounds and evidence not in clean_text[chunk_start:chunk_end]:
                        errors.append(f"{prefix}: evidence_text 未出现在所属 chunk 范围内")
                    continue
                if not isinstance(start, int) or not isinstance(end, int):
                    errors.append(f"{prefix}: char_start/char_end 必须同时为整数或 null")
                elif not (0 <= start < end <= len(clean_text)):
                    errors.append(f"{prefix}: 字符范围超出 document.clean_text")
                elif clean_text[start:end] != evidence:
                    errors.append(f"{prefix}: 字符范围与 evidence_text 不一致")
                elif chunk_bounds and not (chunk_start <= start < end <= chunk_end):
                    errors.append(f"{prefix}: 字符范围超出所属 chunk 范围")

    if document and document_doc_id in doc_ids and document_chunk_count == 0:
        errors.append(f"golden 不包含 document.doc_id={document_doc_id!r} 的 chunk")
    return errors


def evaluate_extraction(
    extraction_result: dict[str, Any],
    golden: dict[str, Any],
    *,
    candidate_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate raw candidate quality with validated results and optional rejected audit."""
    doc_id = extraction_result.get("doc_id", "")
    if doc_id not in golden.get("doc_ids", []):
        raise ValueError(f"extraction_result.doc_id {doc_id!r} 不在 golden.doc_ids 中")
    if candidate_audit and candidate_audit.get("doc_id") != doc_id:
        raise ValueError("candidate_audit.doc_id 与 extraction_result.doc_id 不一致")

    predicted_chunks = _index_unique_chunks(
        extraction_result.get("chunks", []),
        label="extraction_result",
    )
    golden_chunks = _index_unique_chunks(
        [chunk for chunk in golden.get("chunks", []) if chunk.get("doc_id") == doc_id],
        label=f"golden[{doc_id}]",
    )
    if not golden_chunks:
        raise ValueError(f"golden 不包含 doc_id={doc_id!r} 的 chunk")
    audit_chunks = _index_unique_chunks(
        candidate_audit.get("chunks", []) if candidate_audit else [],
        label="candidate_audit",
    )

    predicted_entity_types: list[str] = []
    golden_entity_types: list[str] = []
    matched_entity_types: list[str] = []
    predicted_relation_types: list[str] = []
    golden_relation_types: list[str] = []
    matched_relation_types: list[str] = []

    missing_entities: list[dict[str, Any]] = []
    extra_entities: list[dict[str, Any]] = []
    missing_relations: list[dict[str, Any]] = []
    extra_relations: list[dict[str, Any]] = []
    rejected_entity_count = 0
    rejected_relation_count = 0

    for chunk_id in sorted(set(predicted_chunks) | set(golden_chunks) | set(audit_chunks)):
        predicted_chunk = predicted_chunks.get(chunk_id, {"entities": [], "relations": []})
        golden_chunk = golden_chunks.get(chunk_id, {"entities": [], "relations": []})
        audit_chunk = audit_chunks.get(
            chunk_id,
            {"rejected_entities": [], "rejected_relations": []},
        )
        predicted_entities = predicted_chunk.get("entities", [])
        golden_entities = golden_chunk.get("entities", [])
        predicted_relations = predicted_chunk.get("relations", [])
        golden_relations = golden_chunk.get("relations", [])
        rejected_entities = audit_chunk.get("rejected_entities", [])
        rejected_relations = audit_chunk.get("rejected_relations", [])
        if not isinstance(rejected_entities, list) or not isinstance(rejected_relations, list):
            raise ValueError(
                f"candidate_audit chunk {chunk_id!r} 的 rejected_entities/relations 必须是数组"
            )
        if not all(isinstance(item, dict) for item in [*rejected_entities, *rejected_relations]):
            raise ValueError(f"candidate_audit chunk {chunk_id!r} 的候选项必须是对象")

        predicted_entity_types.extend(entity.get("type", "") for entity in predicted_entities)
        predicted_entity_types.extend(
            entity.get("type", "") or "__INVALID__" for entity in rejected_entities
        )
        golden_entity_types.extend(entity.get("type", "") for entity in golden_entities)
        predicted_relation_types.extend(
            relation.get("relation_type", "") for relation in predicted_relations
        )
        predicted_relation_types.extend(
            relation.get("relation_type", "") or "__INVALID__" for relation in rejected_relations
        )
        golden_relation_types.extend(relation.get("relation_type", "") for relation in golden_relations)
        rejected_entity_count += len(rejected_entities)
        rejected_relation_count += len(rejected_relations)
        extra_entities.extend(
            _entity_summary(chunk_id, entity, source="candidate_audit")
            for entity in rejected_entities
        )
        extra_relations.extend(
            _relation_summary(chunk_id, relation, source="candidate_audit")
            for relation in rejected_relations
        )

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
        "schema_version": SCHEMA_VERSION,
        "evaluated_at": iso_timestamp(now_utc()),
        "extraction": {
            "run_id": extraction_result.get("run_id", ""),
            "doc_id": doc_id,
            "model_name": extraction_result.get("model_name", ""),
            "prompt_version": extraction_result.get("prompt_version", ""),
            "schema_version": extraction_result.get("schema_version", ""),
        },
        "golden": {
            "language": golden.get("language", ""),
            "doc_id": doc_id,
            "schema_version": golden.get("schema_version", ""),
            "golden_version": golden.get("golden_version", ""),
            "target_group": golden.get("target_group", ""),
            "doc_ids": golden.get("doc_ids", []),
        },
        "matching_policy": {
            "entity": (
                "same chunk + same type + normalized name or alias overlap; "
                "maximum cardinality then maximum score"
            ),
            "relation": "same chunk + matched typed endpoints + exact relation type",
            "evidence": "validated separately against document.clean_text; not part of F1 matching",
            "rejected_candidates": "candidate_audit rejected items count as false positives",
        },
        "candidate_audit": {
            "provided": candidate_audit is not None,
            "rejected_entities": rejected_entity_count,
            "rejected_relations": rejected_relation_count,
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
