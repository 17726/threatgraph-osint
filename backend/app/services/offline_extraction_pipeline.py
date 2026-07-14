import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.core.document_contract import document_content_hash, require_valid_document
from backend.app.db.schema import migrate_documents_clean_text_schema
from scripts.validate_extraction_result import (
    ALLOWED_RELATIONS,
    DEFAULT_SCHEMA_PATH,
    load_json,
    validate_import_payload,
)


RELATION_LABELS = {
    "USES": "使用",
    "TARGETS": "攻击目标",
    "EXPLOITS": "利用漏洞",
    "ATTRIBUTED_TO": "归因于",
    "AFFILIATED_WITH": "关联",
    "LOCATED_IN": "位于",
    "HAPPENED_AT": "发生于",
    "PART_OF": "属于",
    "LEADS_TO": "导致",
    "RELATED_TO": "相关",
    "DISCOVERED_BY": "发现者",
    "CAUSES": "导致",
    "HAS_BEHAVIOR": "具备行为",
    "MEMBER_OF": "成员属于",
    "CONTROLS": "控制",
    "TRANSFERS_TO": "转账至",
    "INSTANCE_OF": "实例属于类别",
    "PRECEDES": "先于",
}

ENTITY_PREFIXES = {
    "APT_GROUP": "apt_group",
    "ORGANIZATION": "organization",
    "PERSON": "person",
    "MALWARE": "malware",
    "TOOL": "tool",
    "CVE": "cve",
    "TECHNIQUE": "technique",
    "INFRASTRUCTURE": "infrastructure",
    "LOCATION": "location",
    "FINANCIAL_ACCOUNT": "financial_account",
    "COUNTRY": "country",
    "REGION": "region",
    "INDUSTRY": "industry",
    "TIME": "time",
    "EVENT": "event",
    "CAMPAIGN": "campaign",
    "BEHAVIOR_PATTERN": "behavior_pattern",
}


def document_text(document: dict[str, Any]) -> str:
    return require_valid_document(document)


@dataclass
class OfflinePipelineSummary:
    doc_id: str
    run_id: str
    chunks: int
    extracted_entities: int
    extracted_relations: int
    canonical_entities: int
    canonical_relations: int
    evidence: int
    behavior_patterns: int


class OfflineExtractionPipeline:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def run(
        self,
        document_path: str | Path,
        extraction_result_path: str | Path,
    ) -> OfflinePipelineSummary:
        document = load_json(Path(document_path))
        extraction_result = load_json(Path(extraction_result_path))
        schema_report = validate_import_payload(
            extraction_result,
            document,
            schema_path=DEFAULT_SCHEMA_PATH,
        )
        if not schema_report.ok:
            raise ValueError(
                "Document/extraction_result 契约校验失败: "
                + "; ".join(schema_report.errors)
            )

        with self.connect() as connection:
            self.initialize_schema(connection)
            self.clear_document_canonical_artifacts(connection, document["doc_id"])
            self.import_document(connection, document, extraction_result)
            self.import_extraction_result(connection, document, extraction_result)
            self.normalize_candidates(connection, extraction_result["run_id"])
            self.build_rule_analysis(connection, document["target_group"])
            self.upsert_report(connection, document["target_group"])
            connection.commit()

            return OfflinePipelineSummary(
                doc_id=document["doc_id"],
                run_id=extraction_result["run_id"],
                chunks=len(extraction_result["chunks"]),
                extracted_entities=self._count(
                    connection, "extracted_entities", "run_id = ?", (extraction_result["run_id"],)
                ),
                extracted_relations=self._count(
                    connection, "extracted_relations", "run_id = ?", (extraction_result["run_id"],)
                ),
                canonical_entities=self._count(connection, "entities"),
                canonical_relations=self._count(connection, "relations"),
                evidence=self._count(connection, "evidence"),
                behavior_patterns=self._count(
                    connection, "behavior_patterns", "target_group = ?", (document["target_group"],)
                ),
            )

    def initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
              doc_id TEXT PRIMARY KEY,
              schema_version TEXT NOT NULL DEFAULT '1.0',
              collection_item_id TEXT,
              target_group TEXT NOT NULL,
              target_groups_json TEXT NOT NULL DEFAULT '[]',
              source_url TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_name TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL,
              language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
              clean_text TEXT NOT NULL,
              content_hash TEXT NOT NULL,
              published_at TEXT,
              retrieved_at TEXT,
              source_reliability TEXT NOT NULL DEFAULT 'unknown',
              tlp TEXT NOT NULL DEFAULT 'TLP:CLEAR',
              tags_json TEXT NOT NULL DEFAULT '[]',
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
              chunk_id TEXT PRIMARY KEY,
              doc_id TEXT NOT NULL,
              chunk_index INTEGER NOT NULL DEFAULT 0,
              section_title TEXT NOT NULL DEFAULT '',
              text TEXT NOT NULL,
              char_start INTEGER NOT NULL,
              char_end INTEGER NOT NULL,
              text_hash TEXT NOT NULL,
              token_count INTEGER,
              FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
            );

            CREATE TABLE IF NOT EXISTS entities (
              entity_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              aliases_json TEXT NOT NULL DEFAULT '[]',
              description TEXT NOT NULL DEFAULT '',
              confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
              source_count INTEGER NOT NULL DEFAULT 0,
              first_seen TEXT,
              last_seen TEXT,
              tags_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS relations (
              relation_id TEXT PRIMARY KEY,
              source_entity_id TEXT NOT NULL,
              target_entity_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              label TEXT NOT NULL,
              confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
              source_count INTEGER NOT NULL DEFAULT 0,
              evidence_count INTEGER NOT NULL DEFAULT 0,
              first_seen TEXT,
              last_seen TEXT,
              validation_status TEXT NOT NULL DEFAULT 'valid' CHECK (validation_status IN ('valid', 'invalid')),
              created_at TEXT,
              updated_at TEXT,
              FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id),
              FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id)
            );

            CREATE TABLE IF NOT EXISTS evidence (
              evidence_id TEXT PRIMARY KEY,
              doc_id TEXT NOT NULL,
              chunk_id TEXT,
              entity_id TEXT,
              relation_id TEXT,
              evidence_text TEXT NOT NULL,
              source_url TEXT NOT NULL,
              source_type TEXT NOT NULL DEFAULT '',
              source_name TEXT NOT NULL DEFAULT '',
              evidence_type TEXT NOT NULL DEFAULT 'summary',
              quote_start INTEGER,
              quote_end INTEGER,
              published_at TEXT,
              retrieved_at TEXT,
              source_reliability TEXT NOT NULL DEFAULT 'unknown',
              language TEXT NOT NULL CHECK (language IN ('zh', 'en')),
              created_at TEXT,
              FOREIGN KEY (doc_id) REFERENCES documents(doc_id),
              FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
              FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
              FOREIGN KEY (relation_id) REFERENCES relations(relation_id)
            );

            CREATE TABLE IF NOT EXISTS extraction_runs (
              run_id TEXT PRIMARY KEY,
              schema_version TEXT NOT NULL DEFAULT '1.0',
              doc_id TEXT NOT NULL,
              model_name TEXT NOT NULL,
              prompt_version TEXT NOT NULL,
              parameters_json TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
              validation_status TEXT NOT NULL DEFAULT 'unchecked' CHECK (validation_status IN ('unchecked', 'valid', 'invalid')),
              validation_errors_json TEXT NOT NULL DEFAULT '[]',
              started_at TEXT NOT NULL,
              finished_at TEXT,
              error_message TEXT,
              FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
            );

            CREATE TABLE IF NOT EXISTS extracted_entities (
              extracted_entity_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              chunk_id TEXT NOT NULL,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              aliases_json TEXT NOT NULL DEFAULT '[]',
              description TEXT NOT NULL DEFAULT '',
              mention_text TEXT NOT NULL DEFAULT '',
              evidence_text TEXT NOT NULL,
              char_start INTEGER,
              char_end INTEGER,
              confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
              candidate_status TEXT NOT NULL DEFAULT 'candidate' CHECK (candidate_status IN ('candidate', 'accepted', 'rejected', 'merged')),
              normalized_entity_id TEXT,
              validation_status TEXT NOT NULL DEFAULT 'unchecked' CHECK (validation_status IN ('unchecked', 'valid', 'invalid')),
              validation_errors_json TEXT NOT NULL DEFAULT '[]',
              FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id),
              FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
              FOREIGN KEY (normalized_entity_id) REFERENCES entities(entity_id)
            );

            CREATE TABLE IF NOT EXISTS extracted_relations (
              extracted_relation_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              chunk_id TEXT NOT NULL,
              head_name TEXT NOT NULL,
              head_type TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              tail_name TEXT NOT NULL,
              tail_type TEXT NOT NULL,
              evidence_text TEXT NOT NULL,
              char_start INTEGER,
              char_end INTEGER,
              confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
              candidate_status TEXT NOT NULL DEFAULT 'candidate' CHECK (candidate_status IN ('candidate', 'accepted', 'rejected', 'merged')),
              normalized_relation_id TEXT,
              validation_status TEXT NOT NULL DEFAULT 'unchecked' CHECK (validation_status IN ('unchecked', 'valid', 'invalid')),
              validation_errors_json TEXT NOT NULL DEFAULT '[]',
              FOREIGN KEY (run_id) REFERENCES extraction_runs(run_id),
              FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
              FOREIGN KEY (normalized_relation_id) REFERENCES relations(relation_id)
            );

            CREATE TABLE IF NOT EXISTS behavior_patterns (
              pattern_id TEXT PRIMARY KEY,
              target_group TEXT NOT NULL,
              stage TEXT NOT NULL,
              description TEXT NOT NULL,
              technique_ids_json TEXT NOT NULL DEFAULT '[]',
              relation_ids_json TEXT NOT NULL DEFAULT '[]',
              evidence_ids_json TEXT NOT NULL DEFAULT '[]',
              confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS mitre_mappings (
              mapping_id TEXT PRIMARY KEY,
              target_group TEXT NOT NULL,
              technique_id TEXT NOT NULL,
              technique_name TEXT NOT NULL,
              tactic TEXT NOT NULL,
              attack_stage TEXT NOT NULL,
              entity_id TEXT,
              relation_id TEXT,
              evidence_ids_json TEXT NOT NULL DEFAULT '[]',
              confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
              source TEXT NOT NULL CHECK (source IN ('rule', 'llm', 'manual')),
              created_at TEXT NOT NULL,
              FOREIGN KEY (entity_id) REFERENCES entities(entity_id),
              FOREIGN KEY (relation_id) REFERENCES relations(relation_id)
            );

            CREATE TABLE IF NOT EXISTS inferred_relations (
              inferred_relation_id TEXT PRIMARY KEY,
              source_entity_id TEXT NOT NULL,
              target_entity_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              rationale TEXT NOT NULL,
              support_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
              confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
              status TEXT NOT NULL CHECK (status IN ('candidate', 'accepted', 'rejected')),
              created_at TEXT NOT NULL,
              FOREIGN KEY (source_entity_id) REFERENCES entities(entity_id),
              FOREIGN KEY (target_entity_id) REFERENCES entities(entity_id)
            );

            CREATE TABLE IF NOT EXISTS reports (
              report_id TEXT PRIMARY KEY,
              target_group TEXT NOT NULL,
              title TEXT NOT NULL,
              markdown TEXT NOT NULL,
              generated_at TEXT,
              graph_version TEXT NOT NULL
            );
            """
        )
        migrate_documents_clean_text_schema(connection)
        self._ensure_columns(connection)

    def _ensure_columns(self, connection: sqlite3.Connection) -> None:
        migrations = {
            "entities": {
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "relations": {
                "created_at": "TEXT",
                "updated_at": "TEXT",
            },
            "evidence": {
                "created_at": "TEXT",
            },
            "reports": {
                "generated_at": "TEXT",
            },
        }
        for table_name, columns in migrations.items():
            existing_columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_definition in columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                    )

    def clear_document_canonical_artifacts(
        self,
        connection: sqlite3.Connection,
        doc_id: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT entity_id, relation_id
            FROM evidence
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchall()
        stale_entity_ids = {row["entity_id"] for row in rows if row["entity_id"]}
        stale_relation_ids = {row["relation_id"] for row in rows if row["relation_id"]}

        if stale_relation_ids:
            placeholders = ",".join("?" for _ in stale_relation_ids)
            relation_rows = connection.execute(
                f"""
                SELECT source_entity_id, target_entity_id
                FROM relations
                WHERE relation_id IN ({placeholders})
                """,
                tuple(stale_relation_ids),
            ).fetchall()
            for row in relation_rows:
                stale_entity_ids.add(row["source_entity_id"])
                stale_entity_ids.add(row["target_entity_id"])

        connection.execute("DELETE FROM evidence WHERE doc_id = ?", (doc_id,))

        for relation_id in stale_relation_ids:
            remaining_evidence = connection.execute(
                "SELECT 1 FROM evidence WHERE relation_id = ? LIMIT 1",
                (relation_id,),
            ).fetchone()
            if remaining_evidence is None:
                connection.execute(
                    """
                    UPDATE extracted_relations
                    SET normalized_relation_id = NULL
                    WHERE normalized_relation_id = ?
                    """,
                    (relation_id,),
                )
                if self._table_exists(connection, "mitre_mappings"):
                    connection.execute(
                        "UPDATE mitre_mappings SET relation_id = NULL WHERE relation_id = ?",
                        (relation_id,),
                    )
                connection.execute("DELETE FROM relations WHERE relation_id = ?", (relation_id,))

        for entity_id in stale_entity_ids:
            remaining_evidence = connection.execute(
                "SELECT 1 FROM evidence WHERE entity_id = ? LIMIT 1",
                (entity_id,),
            ).fetchone()
            remaining_relation = connection.execute(
                """
                SELECT 1
                FROM relations
                WHERE source_entity_id = ? OR target_entity_id = ?
                LIMIT 1
                """,
                (entity_id, entity_id),
            ).fetchone()
            if remaining_evidence is None and remaining_relation is None:
                connection.execute(
                    """
                    UPDATE extracted_entities
                    SET normalized_entity_id = NULL
                    WHERE normalized_entity_id = ?
                    """,
                    (entity_id,),
                )
                if self._table_exists(connection, "mitre_mappings"):
                    connection.execute(
                        "UPDATE mitre_mappings SET entity_id = NULL WHERE entity_id = ?",
                        (entity_id,),
                    )
                if self._table_exists(connection, "inferred_relations"):
                    connection.execute(
                        """
                        DELETE FROM inferred_relations
                        WHERE source_entity_id = ? OR target_entity_id = ?
                        """,
                        (entity_id, entity_id),
                    )
                connection.execute("DELETE FROM entities WHERE entity_id = ?", (entity_id,))

        self.refresh_source_counts(connection)

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def import_document(
        self,
        connection: sqlite3.Connection,
        document: dict[str, Any],
        extraction_result: dict[str, Any],
    ) -> None:
        now = now_iso()
        clean_text = document_text(document)
        content_hash = document_content_hash(clean_text)
        connection.execute(
            """
            INSERT OR REPLACE INTO documents (
              doc_id, schema_version, collection_item_id, target_group, target_groups_json,
              source_url, source_type, source_name, title, language, clean_text, content_hash,
              published_at, retrieved_at, source_reliability, tlp, tags_json, metadata_json,
              created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document["doc_id"],
                document.get("schema_version", "1.0"),
                document.get("collection_item_id"),
                document["target_group"],
                json.dumps(document.get("target_groups", [document["target_group"]]), ensure_ascii=False),
                document["source_url"],
                document["source_type"],
                document.get("source_name", ""),
                document["title"],
                document["language"],
                clean_text,
                content_hash,
                document.get("published_at"),
                document.get("retrieved_at"),
                document.get("source_reliability", "unknown"),
                document.get("tlp", "TLP:CLEAR"),
                json.dumps(document.get("tags", []), ensure_ascii=False),
                json.dumps(document.get("metadata", {}), ensure_ascii=False),
                now,
            ),
        )

        for index, chunk in enumerate(extraction_result["chunks"]):
            connection.execute(
                """
                INSERT OR REPLACE INTO chunks (
                  chunk_id, doc_id, chunk_index, section_title, text,
                  char_start, char_end, text_hash, token_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk["chunk_id"],
                    document["doc_id"],
                    index,
                    "",
                    clean_text,
                    0,
                    len(clean_text),
                    "sha256:" + sha256_text(clean_text),
                    None,
                ),
            )

    def import_extraction_result(
        self,
        connection: sqlite3.Connection,
        document: dict[str, Any],
        extraction_result: dict[str, Any],
    ) -> None:
        run_id = extraction_result["run_id"]
        now = now_iso()
        connection.execute("DELETE FROM extracted_relations WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM extracted_entities WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM extraction_runs WHERE run_id = ?", (run_id,))

        candidate_errors: list[str] = []
        clean_text = document_text(document)
        for chunk in extraction_result["chunks"]:
            known_entities = collect_known_entities(chunk)
            for entity_index, entity in enumerate(chunk["entities"]):
                errors = evidence_validation_errors(entity, clean_text)
                candidate_errors.extend(
                    f"{chunk['chunk_id']}.entities[{entity_index}]: {error}" for error in errors
                )
            for relation_index, relation in enumerate(chunk["relations"]):
                errors = relation_validation_errors(relation, known_entities)
                errors.extend(evidence_validation_errors(relation, clean_text))
                candidate_errors.extend(
                    f"{chunk['chunk_id']}.relations[{relation_index}]: {error}" for error in errors
                )

        run_validation_status = "invalid" if candidate_errors else "valid"
        connection.execute(
            """
            INSERT INTO extraction_runs (
              run_id, schema_version, doc_id, model_name, prompt_version, parameters_json,
              status, validation_status, validation_errors_json, started_at, finished_at,
              error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                extraction_result["schema_version"],
                extraction_result["doc_id"],
                extraction_result["model_name"],
                extraction_result["prompt_version"],
                "{}",
                "succeeded",
                run_validation_status,
                json.dumps(candidate_errors, ensure_ascii=False),
                now,
                now,
                None,
            ),
        )

        for chunk in extraction_result["chunks"]:
            known_entities = collect_known_entities(chunk)
            for entity_index, entity in enumerate(chunk["entities"]):
                errors = evidence_validation_errors(entity, clean_text)
                validation_status = "invalid" if errors else "valid"
                connection.execute(
                    """
                    INSERT INTO extracted_entities (
                      extracted_entity_id, run_id, chunk_id, name, type, aliases_json,
                      description, mention_text, evidence_text, char_start, char_end,
                      confidence, candidate_status, normalized_entity_id, validation_status,
                      validation_errors_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        extracted_entity_id(run_id, chunk["chunk_id"], entity_index, entity),
                        run_id,
                        chunk["chunk_id"],
                        entity["name"],
                        entity["type"],
                        json.dumps(entity["aliases"], ensure_ascii=False),
                        entity["description"],
                        entity["mention_text"],
                        entity["evidence_text"],
                        entity["char_start"],
                        entity["char_end"],
                        entity["confidence"],
                        entity["candidate_status"],
                        None,
                        validation_status,
                        json.dumps(errors, ensure_ascii=False),
                    ),
                )

            for relation_index, relation in enumerate(chunk["relations"]):
                errors = relation_validation_errors(relation, known_entities)
                errors.extend(evidence_validation_errors(relation, clean_text))
                validation_status = "invalid" if errors else "valid"
                connection.execute(
                    """
                    INSERT INTO extracted_relations (
                      extracted_relation_id, run_id, chunk_id, head_name, head_type,
                      relation_type, tail_name, tail_type, evidence_text, char_start,
                      char_end, confidence, candidate_status, normalized_relation_id,
                      validation_status, validation_errors_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        extracted_relation_id(run_id, chunk["chunk_id"], relation_index, relation),
                        run_id,
                        chunk["chunk_id"],
                        relation["head_name"],
                        relation["head_type"],
                        relation["relation_type"],
                        relation["tail_name"],
                        relation["tail_type"],
                        relation["evidence_text"],
                        relation["char_start"],
                        relation["char_end"],
                        relation["confidence"],
                        relation["candidate_status"],
                        None,
                        validation_status,
                        json.dumps(errors, ensure_ascii=False),
                    ),
                )

    def normalize_candidates(self, connection: sqlite3.Connection, run_id: str) -> None:
        entity_map: dict[tuple[str, str], str] = {}
        rows = connection.execute(
            """
            SELECT ee.*, d.target_group, d.published_at, d.retrieved_at, d.source_url,
                   d.source_type, d.source_name, d.source_reliability, d.language,
                   d.tags_json
            FROM extracted_entities ee
            JOIN chunks c ON c.chunk_id = ee.chunk_id
            JOIN documents d ON d.doc_id = c.doc_id
            WHERE ee.run_id = ? AND ee.validation_status = 'valid'
            ORDER BY ee.extracted_entity_id
            """,
            (run_id,),
        ).fetchall()

        for row in rows:
            aliases = json.loads(row["aliases_json"])
            entity_id = canonical_entity_id(row["type"], row["name"])
            merged_aliases = merge_aliases(connection, entity_id, aliases)
            tags = merge_tags(connection, entity_id, json.loads(row["tags_json"]))
            first_seen = row["published_at"] or row["retrieved_at"]
            last_seen = row["published_at"] or row["retrieved_at"]
            now = now_iso()
            connection.execute(
                """
                INSERT INTO entities (
                  entity_id, name, type, aliases_json, description, confidence,
                  source_count, first_seen, last_seen, tags_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                  aliases_json = excluded.aliases_json,
                  description = CASE
                    WHEN length(excluded.description) > length(entities.description)
                    THEN excluded.description ELSE entities.description END,
                  confidence = max(entities.confidence, excluded.confidence),
                  first_seen = coalesce(entities.first_seen, excluded.first_seen),
                  last_seen = coalesce(excluded.last_seen, entities.last_seen),
                  tags_json = excluded.tags_json,
                  updated_at = excluded.updated_at
                """,
                (
                    entity_id,
                    row["name"],
                    row["type"],
                    json.dumps(merged_aliases, ensure_ascii=False),
                    row["description"],
                    row["confidence"],
                    0,
                    first_seen,
                    last_seen,
                    json.dumps(tags, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE extracted_entities
                SET normalized_entity_id = ?
                WHERE extracted_entity_id = ?
                """,
                (entity_id, row["extracted_entity_id"]),
            )
            evidence_id = stable_evidence_id(
                row["chunk_id"], "entity", entity_id, row["evidence_text"]
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence (
                  evidence_id, doc_id, chunk_id, entity_id, relation_id, evidence_text,
                  source_url, source_type, source_name, evidence_type, quote_start,
                  quote_end, published_at, retrieved_at, source_reliability, language,
                  created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    row["chunk_id"].rsplit("_c", 1)[0],
                    row["chunk_id"],
                    entity_id,
                    None,
                    row["evidence_text"],
                    row["source_url"],
                    row["source_type"],
                    row["source_name"],
                    "summary",
                    row["char_start"],
                    row["char_end"],
                    row["published_at"],
                    row["retrieved_at"],
                    row["source_reliability"],
                    row["language"],
                    now,
                ),
            )
            for alias in [row["name"], *aliases]:
                entity_map[(normalize_lookup(alias), row["type"])] = entity_id

        relation_rows = connection.execute(
            """
            SELECT er.*, d.published_at, d.retrieved_at, d.source_url, d.source_type,
                   d.source_name, d.source_reliability, d.language
            FROM extracted_relations er
            JOIN chunks c ON c.chunk_id = er.chunk_id
            JOIN documents d ON d.doc_id = c.doc_id
            WHERE er.run_id = ? AND er.validation_status = 'valid'
            ORDER BY er.extracted_relation_id
            """,
            (run_id,),
        ).fetchall()

        for row in relation_rows:
            source_entity_id = entity_map.get((normalize_lookup(row["head_name"]), row["head_type"]))
            target_entity_id = entity_map.get((normalize_lookup(row["tail_name"]), row["tail_type"]))
            if not source_entity_id or not target_entity_id:
                errors = ["关系端点无法归一化到候选实体"]
                connection.execute(
                    """
                    UPDATE extracted_relations
                    SET validation_status = 'invalid', validation_errors_json = ?
                    WHERE extracted_relation_id = ?
                    """,
                    (json.dumps(errors, ensure_ascii=False), row["extracted_relation_id"]),
                )
                continue

            relation_id = canonical_relation_id(
                source_entity_id, row["relation_type"], target_entity_id
            )
            now = now_iso()
            first_seen = row["published_at"] or row["retrieved_at"]
            last_seen = row["published_at"] or row["retrieved_at"]
            connection.execute(
                """
                INSERT INTO relations (
                  relation_id, source_entity_id, target_entity_id, relation_type, label,
                  confidence, source_count, evidence_count, first_seen, last_seen,
                  validation_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(relation_id) DO UPDATE SET
                  confidence = max(relations.confidence, excluded.confidence),
                  first_seen = coalesce(relations.first_seen, excluded.first_seen),
                  last_seen = coalesce(excluded.last_seen, relations.last_seen),
                  validation_status = excluded.validation_status,
                  updated_at = excluded.updated_at
                """,
                (
                    relation_id,
                    source_entity_id,
                    target_entity_id,
                    row["relation_type"],
                    RELATION_LABELS.get(row["relation_type"], row["relation_type"]),
                    row["confidence"],
                    0,
                    0,
                    first_seen,
                    last_seen,
                    "valid",
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE extracted_relations
                SET normalized_relation_id = ?
                WHERE extracted_relation_id = ?
                """,
                (relation_id, row["extracted_relation_id"]),
            )
            evidence_id = stable_evidence_id(
                row["chunk_id"], "relation", relation_id, row["evidence_text"]
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO evidence (
                  evidence_id, doc_id, chunk_id, entity_id, relation_id, evidence_text,
                  source_url, source_type, source_name, evidence_type, quote_start,
                  quote_end, published_at, retrieved_at, source_reliability, language,
                  created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    row["chunk_id"].rsplit("_c", 1)[0],
                    row["chunk_id"],
                    None,
                    relation_id,
                    row["evidence_text"],
                    row["source_url"],
                    row["source_type"],
                    row["source_name"],
                    "summary",
                    row["char_start"],
                    row["char_end"],
                    row["published_at"],
                    row["retrieved_at"],
                    row["source_reliability"],
                    row["language"],
                    now,
                ),
            )

        self.refresh_source_counts(connection)

    def refresh_source_counts(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            UPDATE entities
            SET source_count = (
              SELECT count(DISTINCT doc_id) FROM evidence WHERE evidence.entity_id = entities.entity_id
            )
            """
        )
        connection.execute(
            """
            UPDATE relations
            SET source_count = (
                  SELECT count(DISTINCT doc_id) FROM evidence WHERE evidence.relation_id = relations.relation_id
                ),
                evidence_count = (
                  SELECT count(*) FROM evidence WHERE evidence.relation_id = relations.relation_id
                )
            """
        )

    def build_rule_analysis(self, connection: sqlite3.Connection, target_group: str) -> None:
        now = now_iso()
        target_entity_id = canonical_entity_id("APT_GROUP", target_group)
        connection.execute("DELETE FROM behavior_patterns WHERE target_group = ?", (target_group,))

        uses_rows = connection.execute(
            """
            SELECT r.relation_id, r.confidence, e.name AS target_name
            FROM relations r
            JOIN entities e ON e.entity_id = r.target_entity_id
            WHERE r.source_entity_id = ? AND r.relation_type = 'USES'
              AND e.type IN ('MALWARE', 'TOOL')
            ORDER BY e.name
            """,
            (target_entity_id,),
        ).fetchall()
        if uses_rows:
            relation_ids = [row["relation_id"] for row in uses_rows]
            evidence_ids = evidence_ids_for_relations(connection, relation_ids)
            tool_names = "、".join(row["target_name"] for row in uses_rows)
            connection.execute(
                """
                INSERT OR REPLACE INTO behavior_patterns (
                  pattern_id, target_group, stage, description, technique_ids_json,
                  relation_ids_json, evidence_ids_json, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"pattern_{slugify(target_group)}_tool_use",
                    target_group,
                    "工具使用",
                    f"{target_group} 在当前样例中与 {tool_names} 等恶意软件或工具存在使用关系。",
                    "[]",
                    json.dumps(relation_ids, ensure_ascii=False),
                    json.dumps(evidence_ids, ensure_ascii=False),
                    average(row["confidence"] for row in uses_rows),
                    now,
                ),
            )

        target_rows = connection.execute(
            """
            SELECT r.relation_id, r.confidence, e.name AS target_name
            FROM relations r
            JOIN entities e ON e.entity_id = r.target_entity_id
            WHERE r.source_entity_id = ? AND r.relation_type = 'TARGETS'
            ORDER BY e.type, e.name
            """,
            (target_entity_id,),
        ).fetchall()
        if target_rows:
            relation_ids = [row["relation_id"] for row in target_rows]
            evidence_ids = evidence_ids_for_relations(connection, relation_ids)
            target_names = "、".join(row["target_name"] for row in target_rows)
            connection.execute(
                """
                INSERT OR REPLACE INTO behavior_patterns (
                  pattern_id, target_group, stage, description, technique_ids_json,
                  relation_ids_json, evidence_ids_json, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"pattern_{slugify(target_group)}_targeting",
                    target_group,
                    "目标偏好",
                    f"{target_group} 在当前样例中呈现对 {target_names} 的目标偏好。",
                    "[]",
                    json.dumps(relation_ids, ensure_ascii=False),
                    json.dumps(evidence_ids, ensure_ascii=False),
                    average(row["confidence"] for row in target_rows),
                    now,
                ),
            )

    def upsert_report(self, connection: sqlite3.Connection, target_group: str) -> None:
        target_entity_id = canonical_entity_id("APT_GROUP", target_group)
        entity_count = self._count(connection, "entities")
        relation_count = self._count(
            connection, "relations", "source_entity_id = ? OR target_entity_id = ?", (target_entity_id, target_entity_id)
        )
        evidence_count = self._count(connection, "evidence")
        patterns = connection.execute(
            """
            SELECT stage, description
            FROM behavior_patterns
            WHERE target_group = ?
            ORDER BY pattern_id
            """,
            (target_group,),
        ).fetchall()
        pattern_lines = "\n".join(f"- {row['stage']}：{row['description']}" for row in patterns)
        if not pattern_lines:
            pattern_lines = "- 暂无可由规则生成的行为模式。"
        markdown = (
            f"## {target_group} 离线候选抽取报告\n\n"
            f"当前报告由本地 document.json 和 extraction_result.json 生成，未调用真实 LLM API。\n\n"
            f"### 图谱规模\n\n"
            f"- 实体：{entity_count}\n"
            f"- 与 {target_group} 直接相关的关系：{relation_count}\n"
            f"- 证据：{evidence_count}\n\n"
            f"### 行为模式\n\n"
            f"{pattern_lines}\n"
        )
        now = now_iso()
        connection.execute(
            """
            INSERT OR REPLACE INTO reports (
              report_id, target_group, title, markdown, generated_at, graph_version
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"report_{slugify(target_group)}_offline",
                target_group,
                f"{target_group} 离线候选抽取报告",
                markdown,
                now,
                "offline-extraction-v1",
            ),
        )

    def _count(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        where_clause: str | None = None,
        params: tuple[Any, ...] = (),
    ) -> int:
        sql = f"SELECT count(*) AS count FROM {table_name}"
        if where_clause:
            sql += f" WHERE {where_clause}"
        return int(connection.execute(sql, params).fetchone()["count"])


def collect_known_entities(chunk: dict[str, Any]) -> set[tuple[str, str]]:
    known = set()
    for entity in chunk.get("entities", []):
        known.add((entity["name"], entity["type"]))
        known.update((alias, entity["type"]) for alias in entity["aliases"])
    return known


def relation_validation_errors(
    relation: dict[str, Any],
    known_entities: set[tuple[str, str]],
) -> list[str]:
    errors = []
    relation_type = relation["relation_type"]
    rule = ALLOWED_RELATIONS.get(relation_type)
    if rule is None:
        return [f"未知关系类型 {relation_type}"]
    if relation_type != "RELATED_TO":
        if relation["head_type"] not in rule["heads"]:
            errors.append(f"{relation_type} 不允许主体类型 {relation['head_type']}")
        if relation["tail_type"] not in rule["tails"]:
            errors.append(f"{relation_type} 不允许客体类型 {relation['tail_type']}")
        if (relation["head_type"], relation["tail_type"]) not in rule["pairs"]:
            errors.append(
                f"不允许类型组合 {relation['head_type']} -> "
                f"{relation_type} -> {relation['tail_type']}"
            )
    if (relation["head_name"], relation["head_type"]) not in known_entities:
        errors.append("主体实体未在同一 chunk 的候选实体中声明")
    if (relation["tail_name"], relation["tail_type"]) not in known_entities:
        errors.append("客体实体未在同一 chunk 的候选实体中声明")
    return errors


def evidence_validation_errors(item: dict[str, Any], clean_text: str) -> list[str]:
    evidence_text = item["evidence_text"]
    if evidence_text not in clean_text:
        return ["evidence_text 未出现在 document.clean_text 中"]
    char_start = item.get("char_start")
    char_end = item.get("char_end")
    if char_start is None and char_end is None:
        return []
    if char_start is None or char_end is None:
        return ["char_start 和 char_end 必须同时为空或同时填写"]
    if not (0 <= char_start < char_end <= len(clean_text)):
        return ["字符范围超出 clean_text"]
    if clean_text[char_start:char_end] != evidence_text:
        return ["字符范围与 evidence_text 不一致"]
    return []


def merge_aliases(connection: sqlite3.Connection, entity_id: str, aliases: list[str]) -> list[str]:
    existing = connection.execute(
        "SELECT aliases_json FROM entities WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    existing_aliases = json.loads(existing["aliases_json"]) if existing else []
    return sorted({alias for alias in [*existing_aliases, *aliases] if alias})


def merge_tags(connection: sqlite3.Connection, entity_id: str, tags: list[str]) -> list[str]:
    existing = connection.execute(
        "SELECT tags_json FROM entities WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    existing_tags = json.loads(existing["tags_json"]) if existing else []
    return sorted({tag for tag in [*existing_tags, *tags] if tag})


def evidence_ids_for_relations(
    connection: sqlite3.Connection,
    relation_ids: list[str],
) -> list[str]:
    if not relation_ids:
        return []
    placeholders = ",".join("?" for _ in relation_ids)
    rows = connection.execute(
        f"""
        SELECT evidence_id
        FROM evidence
        WHERE relation_id IN ({placeholders})
        ORDER BY evidence_id
        """,
        tuple(relation_ids),
    ).fetchall()
    return [row["evidence_id"] for row in rows]


def canonical_entity_id(entity_type: str, name: str) -> str:
    if entity_type == "TECHNIQUE":
        match = re.search(r"\bT\d{4}(?:\.\d{3})?\b", name, flags=re.IGNORECASE)
        if match:
            return f"{ENTITY_PREFIXES[entity_type]}:{match.group(0).lower()}"
    return f"{ENTITY_PREFIXES[entity_type]}:{slugify(name)}"


def canonical_relation_id(source_entity_id: str, relation_type: str, target_entity_id: str) -> str:
    return f"rel:{source_entity_id}:{relation_type}:{target_entity_id}"


def extracted_entity_id(
    run_id: str,
    chunk_id: str,
    entity_index: int,
    entity: dict[str, Any],
) -> str:
    return "xent_" + short_hash(run_id, chunk_id, str(entity_index), entity["name"], entity["type"])


def extracted_relation_id(
    run_id: str,
    chunk_id: str,
    relation_index: int,
    relation: dict[str, Any],
) -> str:
    return "xrel_" + short_hash(
        run_id,
        chunk_id,
        str(relation_index),
        relation["head_name"],
        relation["relation_type"],
        relation["tail_name"],
    )


def stable_evidence_id(
    chunk_id: str,
    evidence_kind: str,
    normalized_id: str,
    evidence_text: str,
) -> str:
    doc_id = chunk_id.rsplit("_c", 1)[0]
    return f"ev_{doc_id}_{short_hash(evidence_kind, normalized_id, evidence_text)}"


def slugify(value: str) -> str:
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def normalize_lookup(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def short_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def average(values: Any) -> float:
    numbers = list(values)
    return round(sum(numbers) / len(numbers), 4) if numbers else 0.0
