import sqlite3

from backend.app.core.document_contract import document_content_hash


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def ensure_import_compatible_columns(connection: sqlite3.Connection) -> None:
    """补齐 API 启动库与离线导入共同依赖的文档、切块字段。"""
    migrations = {
        "documents": {
            "collection_item_id": "TEXT",
            "target_groups_json": "TEXT NOT NULL DEFAULT '[]'",
            "tlp": "TEXT NOT NULL DEFAULT 'TLP:CLEAR'",
            "tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        },
        "chunks": {
            "section_title": "TEXT NOT NULL DEFAULT ''",
            "token_count": "INTEGER",
        },
    }
    for table_name, columns in migrations.items():
        if not _table_exists(connection, table_name):
            continue
        existing_columns = _table_columns(connection, table_name)
        for column_name, column_definition in columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                )
    if _table_exists(connection, "documents"):
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_content_hash "
            "ON documents(content_hash)"
        )


def ensure_graph_sync_schema(connection: sqlite3.Connection) -> None:
    """创建 SQLite 到 Neo4j 投影同步所需的变更日志和水位表。"""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS graph_changes (
          change_id INTEGER PRIMARY KEY AUTOINCREMENT,
          table_name TEXT NOT NULL
            CHECK (table_name IN ('entities', 'relations', 'evidence')),
          record_id TEXT NOT NULL,
          operation TEXT NOT NULL CHECK (operation IN ('upsert', 'delete')),
          changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sync_state (
          state_key TEXT PRIMARY KEY,
          watermark INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'requires_rebuild',
          last_attempt_at TEXT,
          last_success_at TEXT,
          last_full_sync_at TEXT,
          error_message TEXT,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT OR IGNORE INTO sync_state (state_key, watermark)
        VALUES ('neo4j', 0);

        CREATE TRIGGER IF NOT EXISTS entities_graph_change_insert
        AFTER INSERT ON entities
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('entities', NEW.entity_id, 'upsert');
        END;
        CREATE TRIGGER IF NOT EXISTS entities_graph_change_update
        AFTER UPDATE ON entities
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('entities', NEW.entity_id, 'upsert');
        END;
        CREATE TRIGGER IF NOT EXISTS entities_graph_change_delete
        AFTER DELETE ON entities
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('entities', OLD.entity_id, 'delete');
        END;
        CREATE TRIGGER IF NOT EXISTS relations_graph_change_insert
        AFTER INSERT ON relations
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('relations', NEW.relation_id, 'upsert');
        END;
        CREATE TRIGGER IF NOT EXISTS relations_graph_change_update
        AFTER UPDATE ON relations
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('relations', NEW.relation_id, 'upsert');
        END;
        CREATE TRIGGER IF NOT EXISTS relations_graph_change_delete
        AFTER DELETE ON relations
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('relations', OLD.relation_id, 'delete');
        END;
        CREATE TRIGGER IF NOT EXISTS evidence_graph_change_insert
        AFTER INSERT ON evidence
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('evidence', NEW.evidence_id, 'upsert');
        END;
        CREATE TRIGGER IF NOT EXISTS evidence_graph_change_update
        AFTER UPDATE ON evidence
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('evidence', NEW.evidence_id, 'upsert');
        END;
        CREATE TRIGGER IF NOT EXISTS evidence_graph_change_delete
        AFTER DELETE ON evidence
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          VALUES ('evidence', OLD.evidence_id, 'delete');
        END;
        CREATE TRIGGER IF NOT EXISTS evidence_owner_graph_change_insert
        AFTER INSERT ON evidence
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'entities', NEW.entity_id, 'upsert'
          WHERE NEW.entity_id IS NOT NULL;
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'relations', NEW.relation_id, 'upsert'
          WHERE NEW.relation_id IS NOT NULL;
        END;
        CREATE TRIGGER IF NOT EXISTS evidence_owner_graph_change_update
        AFTER UPDATE ON evidence
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'entities', OLD.entity_id, 'upsert'
          WHERE OLD.entity_id IS NOT NULL;
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'relations', OLD.relation_id, 'upsert'
          WHERE OLD.relation_id IS NOT NULL;
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'entities', NEW.entity_id, 'upsert'
          WHERE NEW.entity_id IS NOT NULL;
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'relations', NEW.relation_id, 'upsert'
          WHERE NEW.relation_id IS NOT NULL;
        END;
        CREATE TRIGGER IF NOT EXISTS evidence_owner_graph_change_delete
        AFTER DELETE ON evidence
        BEGIN
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'entities', OLD.entity_id, 'upsert'
          WHERE OLD.entity_id IS NOT NULL;
          INSERT INTO graph_changes (table_name, record_id, operation)
          SELECT 'relations', OLD.relation_id, 'upsert'
          WHERE OLD.relation_id IS NOT NULL;
        END;
        """
    )
    sync_state_columns = _table_columns(connection, "sync_state")
    migrations = {
        "status": "TEXT NOT NULL DEFAULT 'requires_rebuild'",
        "last_attempt_at": "TEXT",
        "last_success_at": "TEXT",
        "last_full_sync_at": "TEXT",
        "error_message": "TEXT",
    }
    for column_name, definition in migrations.items():
        if column_name not in sync_state_columns:
            connection.execute(
                f"ALTER TABLE sync_state ADD COLUMN {column_name} {definition}"
            )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_changes_after_watermark "
        "ON graph_changes(change_id, table_name, record_id)"
    )


def ensure_pipeline_schema(connection: sqlite3.Connection) -> None:
    """创建统一流水线任务及步骤状态表。"""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS pipeline_jobs (
          job_id TEXT PRIMARY KEY,
          doc_id TEXT,
          target_group TEXT,
          use_cache INTEGER NOT NULL DEFAULT 1 CHECK (use_cache IN (0, 1)),
          extraction_mode TEXT NOT NULL DEFAULT 'reviewed'
            CHECK (extraction_mode IN ('reviewed', 'live')),
          operation TEXT NOT NULL DEFAULT 'import_extraction_and_build',
          request_key TEXT,
          steps_json TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
          current_step TEXT,
          failed_step TEXT,
          result_json TEXT NOT NULL DEFAULT '{}',
          error_message TEXT,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pipeline_job_steps (
          job_id TEXT NOT NULL,
          step_name TEXT NOT NULL,
          step_order INTEGER NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')),
          result_json TEXT NOT NULL DEFAULT '{}',
          error_message TEXT,
          started_at TEXT,
          finished_at TEXT,
          PRIMARY KEY (job_id, step_name),
          FOREIGN KEY (job_id) REFERENCES pipeline_jobs(job_id) ON DELETE CASCADE
        );
        """
    )
    existing_columns = _table_columns(connection, "pipeline_jobs")
    if "extraction_mode" not in existing_columns:
        connection.execute(
            "ALTER TABLE pipeline_jobs ADD COLUMN extraction_mode TEXT "
            "NOT NULL DEFAULT 'reviewed'"
        )
    if "operation" not in existing_columns:
        connection.execute(
            "ALTER TABLE pipeline_jobs ADD COLUMN operation TEXT "
            "NOT NULL DEFAULT 'import_extraction_and_build'"
        )
    if "request_key" not in existing_columns:
        connection.execute(
            "ALTER TABLE pipeline_jobs ADD COLUMN request_key TEXT"
        )
        connection.execute(
            "UPDATE pipeline_jobs SET request_key = job_id WHERE request_key IS NULL"
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_jobs_active_request "
        "ON pipeline_jobs(request_key) "
        "WHERE status IN ('pending', 'running')"
    )


def _validate_document_hashes(connection: sqlite3.Connection, text_column: str) -> None:
    rows = connection.execute(
        f"SELECT doc_id, {text_column}, content_hash FROM documents ORDER BY doc_id"
    ).fetchall()
    for row in rows:
        doc_id, text, content_hash = row
        expected_hash = document_content_hash(text)
        if content_hash != expected_hash:
            raise ValueError(
                f"documents[{doc_id}].content_hash 与 {text_column} 不一致: "
                f"expected={expected_hash}, actual={content_hash!r}"
            )


def migrate_documents_clean_text_schema(connection: sqlite3.Connection) -> None:
    """校验 documents 契约，并拒绝无法证明语义的旧 raw_text 自动升格。"""
    if not _table_exists(connection, "documents"):
        return

    connection.execute("SAVEPOINT migrate_documents_clean_text")
    try:
        if _table_exists(connection, "documents_new"):
            connection.execute("DROP TABLE documents_new")

        columns = _table_columns(connection, "documents")
        has_clean_text = "clean_text" in columns
        has_raw_text = "raw_text" in columns
        if has_clean_text and has_raw_text:
            raise RuntimeError("SQLite documents 表同时包含 clean_text 和 raw_text，禁止自动迁移")
        if has_raw_text:
            raise RuntimeError(
                "SQLite documents.raw_text 缺少清洗 provenance，"
                "无法证明其为清洗正文，禁止自动迁移到 clean_text"
            )
        if not has_clean_text:
            raise RuntimeError("SQLite documents 表缺少 clean_text 列")

        _validate_document_hashes(connection, "clean_text")

        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"SQLite 外键检查失败: {len(foreign_key_errors)} 项")
        connection.execute("RELEASE SAVEPOINT migrate_documents_clean_text")
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT migrate_documents_clean_text")
        connection.execute("RELEASE SAVEPOINT migrate_documents_clean_text")
        raise
