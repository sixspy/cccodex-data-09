import sqlite3
from contextlib import contextmanager

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def db_transaction():
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def _add_missing_columns(db):
    """兼容旧库：为已存在的表补上点头流程所需列。"""
    migrations = {
        "crawl_jobs": [
            ("created_by", "TEXT NOT NULL DEFAULT ''"),
            ("approval_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("approved_by", "TEXT"),
            ("approved_at", "TEXT"),
        ],
        "crawl_records": [
            ("approved", "INTEGER NOT NULL DEFAULT 0"),
        ],
    }
    for table, columns in migrations.items():
        existing = {
            row["name"] for row in db.execute(f"PRAGMA table_info({table})")
        }
        for name, ddl in columns:
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS crawl_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                seed_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_by TEXT NOT NULL DEFAULT '',
                approval_status TEXT NOT NULL DEFAULT 'pending',
                approved_by TEXT,
                approved_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS crawl_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
                item_key TEXT NOT NULL,
                title TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(job_id, item_key)
            );
            """
        )
        _add_missing_columns(db)
        db.commit()
