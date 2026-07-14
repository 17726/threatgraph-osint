import sqlite3

import pytest

from backend.app.core.document_contract import document_content_hash
from backend.app.db.schema import migrate_documents_clean_text_schema


def test_documents_migration_rejects_ambiguous_raw_text_and_preserves_foreign_keys():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    body = "Legacy cleaned body"
    connection.executescript(
        """
        CREATE TABLE documents (
          doc_id TEXT PRIMARY KEY,
          raw_text TEXT NOT NULL,
          content_hash TEXT NOT NULL
        );
        CREATE TABLE chunks (
          chunk_id TEXT PRIMARY KEY,
          doc_id TEXT NOT NULL,
          FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
        );
        """
    )
    connection.execute(
        "INSERT INTO documents (doc_id, raw_text, content_hash) VALUES (?, ?, ?)",
        ("legacy_doc", body, document_content_hash(body)),
    )
    connection.execute(
        "INSERT INTO chunks (chunk_id, doc_id) VALUES (?, ?)",
        ("legacy_doc_c001", "legacy_doc"),
    )

    with pytest.raises(RuntimeError, match="无法证明.*清洗正文"):
        migrate_documents_clean_text_schema(connection)

    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
    chunk = connection.execute("SELECT doc_id FROM chunks").fetchone()
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert columns == {"doc_id", "raw_text", "content_hash"}
    assert chunk == ("legacy_doc",)
    assert foreign_key_errors == []
