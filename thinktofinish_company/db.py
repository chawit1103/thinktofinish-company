from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import data_root


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS trace_nodes (
    project TEXT NOT NULL,
    node_type TEXT NOT NULL,
    node_id TEXT NOT NULL,
    title TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project, node_type, node_id)
);

CREATE TABLE IF NOT EXISTS trace_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project, source_type, source_id, target_type, target_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_trace_edges_source
ON trace_edges(project, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_trace_edges_target
ON trace_edges(project, target_type, target_id);

CREATE TABLE IF NOT EXISTS task_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    cycle_seconds REAL NOT NULL DEFAULT 0,
    retries INTEGER NOT NULL DEFAULT 0,
    human_interventions INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    first_pass INTEGER NOT NULL DEFAULT 0,
    autonomous INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project, task_id)
);
CREATE INDEX IF NOT EXISTS idx_metrics_project ON task_metrics(project);
"""


def db_path() -> Path:
    return data_root() / "company.db"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
