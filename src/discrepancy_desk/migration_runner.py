from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from .db import connect, connect_existing
from .migration_integrity import (
    MigrationIntegrityError,
    assert_clean_migration_state,
    begin_migration_guard,
    clear_migration_guard,
    verify_manifest,
)
from .migration_spec import MigrationSpec


def _current_revision(database_path: Path, version_table: str) -> str | None:
    if not database_path.is_file():
        return None
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if version_table not in tables:
            return None
        row = connection.execute(f"SELECT version_num FROM {version_table}").fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        connection.close()


def run_guarded_upgrade(
    database_path: Path,
    spec: MigrationSpec,
    *,
    operation_id: str,
    target_revision: str | None = None,
    allow_create: bool = False,
    identity: dict[str, str] | None = None,
) -> None:
    resolved = spec.resolved()
    manifest_sha256 = verify_manifest(resolved)
    if not database_path.exists() and not allow_create:
        raise MigrationIntegrityError("migration target database does not exist")
    assert_clean_migration_state(database_path)
    requested_revision = target_revision or resolved.expected_head
    from_revision = _current_revision(database_path, resolved.version_table)
    begin_migration_guard(
        database_path,
        operation_id=operation_id,
        target_revision=requested_revision,
        spec=resolved,
        from_revision=from_revision,
        identity=identity,
        manifest_sha256=manifest_sha256,
    )
    try:
        config = Config(str(resolved.config_path))
        config.set_main_option("script_location", str(resolved.migrations_root))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.resolve().as_posix()}")
        config.set_main_option("version_table", resolved.version_table)
        config.set_main_option("schema_name", resolved.schema_name)
        command.upgrade(config, requested_revision)
        connection = connect(database_path) if allow_create else connect_existing(database_path)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise MigrationIntegrityError("post-migration integrity check failed")
            revision = connection.execute(
                f"SELECT version_num FROM {resolved.version_table}"
            ).fetchone()
            if revision is None or str(revision[0]) != requested_revision:
                raise MigrationIntegrityError("migration expected head mismatch")
        finally:
            connection.close()
        clear_migration_guard(database_path, operation_id=operation_id)
    except Exception:
        # The durable marker intentionally remains for governed recovery.
        raise
