"""SQLite connection and schema initialization.

`schema.sql` creates the tables on a fresh database. Because it uses
``CREATE TABLE IF NOT EXISTS`` it does *not* add new columns to an existing
database, so `migrate_db` backfills those separately (idempotently).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Columns added after the initial release: {table: {column: SQL declaration}}.
# schema.sql already includes them for fresh databases; migrate_db adds them to
# databases created by an older version.
ADD_COLUMNS: dict[str, dict[str, str]] = {
    "jobs": {"match_attempts": "INTEGER NOT NULL DEFAULT 0"},
    "matches": {"profile_hash": "TEXT"},
}

# Obsolete pieces removed from the schema (the old detail-scraper fields). They
# are dropped from older databases so they match a fresh one. Indexes must go
# first: SQLite refuses to drop a column that an index still references.
DROP_INDEXES = ("idx_jobs_linkedin_id", "idx_jobs_title_company")
DROP_COLUMNS: dict[str, tuple[str, ...]] = {
    "jobs": (
        "linkedin_job_id",
        "description",
        "employment_type",
        "experience_level",
        "salary",
        "remote_status",
        "company_url",
        "source",
        "raw_json",
    ),
}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names currently present on ``table``."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    """Return the names of all indexes in the database."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    return {row["name"] for row in rows}


def migrate_db(conn: sqlite3.Connection) -> None:
    """Bring an existing database in line with the current schema (idempotent).

    New columns are added with ALTER TABLE ADD COLUMN; obsolete columns (and the
    indexes referencing them) are dropped.
    """
    # 1) Add columns introduced by newer versions.
    for table, columns in ADD_COLUMNS.items():
        existing = _table_columns(conn, table)
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    # 2) Drop obsolete indexes, then the columns they protected.
    indexes = _index_names(conn)
    for index in DROP_INDEXES:
        if index in indexes:
            conn.execute(f"DROP INDEX {index}")

    for table, columns in DROP_COLUMNS.items():
        existing = _table_columns(conn, table)
        for name in columns:
            if name in existing:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {name}")

    conn.commit()


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the database, creating its parent directory if needed."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["column"]
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # better concurrent read/write
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema if absent, then apply any pending migrations."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    migrate_db(conn)
    conn.commit()
