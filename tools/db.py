"""Shared SQLite connection + schema for tracker.py and accounts.py."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    source_job_id TEXT,
    url           TEXT,
    apply_url     TEXT,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    norm_key      TEXT NOT NULL,
    match_score   INTEGER,
    status        TEXT NOT NULL DEFAULT 'seen',
    reason        TEXT,
    first_seen    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    applied_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_source_id
    ON jobs(source, source_job_id) WHERE source_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_jobs_norm_key ON jobs(norm_key);
CREATE INDEX IF NOT EXISTS ix_jobs_apply_url ON jobs(apply_url);

CREATE TABLE IF NOT EXISTS accounts (
    domain      TEXT PRIMARY KEY,
    email       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    verified    INTEGER NOT NULL DEFAULT 0
);
"""


# Columns added after the initial schema; connect() adds any that are missing.
JOB_COLUMNS_V2 = {
    "work_type": "TEXT",           # remote | hybrid | onsite
    "is_contract": "INTEGER NOT NULL DEFAULT 0",
    "contract_length": "TEXT",     # e.g. "+6 months", only when the posting states it
    "site_label": "TEXT",          # link text for the sheet's Site column, e.g. "Greenhouse"
    "resume_file": "TEXT",         # set only when a non-default resume was used
    "sheet_row": "INTEGER",        # Google Sheet row the application was logged to
}


def db_path() -> Path:
    override = os.environ.get("JOBS_DB")
    return Path(override) if override else DATA_DIR / "jobs.db"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    for col, decl in JOB_COLUMNS_V2.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {decl}")
    conn.commit()
    return conn
