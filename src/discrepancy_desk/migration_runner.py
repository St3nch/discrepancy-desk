from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .db import connect
from .migration_integrity import (
    MigrationIntegrityError,
    assert_clean_migration_state,
    begin_migration_guard,
    clear_migration_guard,
    verify_manifest,
)


def run_guarded_upgrade(
    database_path: Path,
    migrations_root: Path,
    *,
    operation_id: str,
    target_revision: str = "head",
) -> None:
    verify_manifest(migrations_root)
    assert_clean_migration_state(database_path)
    begin_migration_guard(
        database_path,
        operation_id=operation_id,
        target_revision=target_revision,
    )
    try:
        config = Config(str(migrations_root.parent / "alembic.ini"))
        config.set_main_option("script_location", str(migrations_root))
        config.set_main_option(
            "sqlalchemy.url", f"sqlite:///{database_path.as_posix()}"
        )
        command.upgrade(config, target_revision)
        connection = connect(database_path)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise MigrationIntegrityError("post-migration integrity check failed")
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            if revision is None:
                raise MigrationIntegrityError("migration version marker is missing")
        finally:
            connection.close()
        clear_migration_guard(database_path, operation_id=operation_id)
    except Exception:
        # The durable marker intentionally remains for governed recovery.
        raise
