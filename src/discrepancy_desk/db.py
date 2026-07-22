from __future__ import annotations

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000
EXPECTED_JOURNAL_MODE = "wal"


def _configure(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise RuntimeError("SQLite foreign-key enforcement is disabled")
    if str(journal_mode).lower() != EXPECTED_JOURNAL_MODE:
        connection.close()
        raise RuntimeError(f"Unexpected SQLite journal mode: {journal_mode}")
    return connection


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return _configure(
        sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    )


def connect_existing(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=rw"
    return _configure(
        sqlite3.connect(uri, uri=True, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    )


def begin_write(connection: sqlite3.Connection) -> None:
    connection.execute("BEGIN IMMEDIATE")
