from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


class MigrationIntegrityError(RuntimeError):
    pass


def verify_manifest(migrations_root: Path) -> None:
    manifest = migrations_root / "manifest.sha256"
    if not manifest.is_file():
        raise MigrationIntegrityError("migration manifest is missing")
    for line_number, raw_line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            name, expected = line.split(maxsplit=1)
        except ValueError as exc:
            raise MigrationIntegrityError(f"malformed manifest line {line_number}") from exc
        candidate = migrations_root / "versions" / name
        if not candidate.is_file():
            raise MigrationIntegrityError(f"migration is missing: {name}")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            raise MigrationIntegrityError(f"migration hash mismatch: {name}")


def dirty_marker_path(database_path: Path) -> Path:
    return database_path.with_name(database_path.name + ".migration-dirty.json")


def assert_clean_migration_state(database_path: Path) -> None:
    marker = dirty_marker_path(database_path)
    if marker.exists():
        raise MigrationIntegrityError(f"database migration state is dirty: {marker.name}")


def begin_migration_guard(database_path: Path, *, operation_id: str, target_revision: str) -> Path:
    marker = dirty_marker_path(database_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"operation_id": operation_id, "target_revision": target_revision}
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise MigrationIntegrityError("migration dirty marker already exists") from exc
    return marker


def clear_migration_guard(database_path: Path, *, operation_id: str) -> None:
    marker = dirty_marker_path(database_path)
    if not marker.is_file():
        raise MigrationIntegrityError("migration dirty marker is missing")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationIntegrityError("migration dirty marker is malformed") from exc
    if payload.get("operation_id") != operation_id:
        raise MigrationIntegrityError("migration dirty marker operation mismatch")
    marker.unlink()


def read_migration_guard(database_path: Path) -> dict[str, str]:
    marker = dirty_marker_path(database_path)
    if not marker.is_file():
        raise MigrationIntegrityError("migration dirty marker is missing")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationIntegrityError("migration dirty marker is malformed") from exc
    operation_id = payload.get("operation_id")
    target_revision = payload.get("target_revision")
    if not isinstance(operation_id, str) or not isinstance(target_revision, str):
        raise MigrationIntegrityError("migration dirty marker has invalid fields")
    return {"operation_id": operation_id, "target_revision": target_revision}


def recover_completed_migration(
    database_path: Path, migrations_root: Path, *, operation_id: str
) -> None:
    payload = read_migration_guard(database_path)
    if payload["operation_id"] != operation_id:
        raise MigrationIntegrityError("migration recovery operation mismatch")
    verify_manifest(migrations_root)
    if not database_path.is_file():
        raise MigrationIntegrityError("cannot recover completed migration: database is missing")
    connection = sqlite3.connect(database_path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MigrationIntegrityError("cannot recover completed migration: integrity check failed")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "alembic_version" not in tables:
            raise MigrationIntegrityError("cannot recover completed migration: version table is missing")
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if revision is None or not str(revision[0]):
            raise MigrationIntegrityError("cannot recover completed migration: version marker is missing")
    finally:
        connection.close()
    clear_migration_guard(database_path, operation_id=operation_id)


def discard_failed_empty_migration(database_path: Path, *, operation_id: str) -> None:
    payload = read_migration_guard(database_path)
    if payload["operation_id"] != operation_id:
        raise MigrationIntegrityError("migration recovery operation mismatch")
    if database_path.exists():
        connection = sqlite3.connect(database_path)
        try:
            user_objects = [
                str(row[0])
                for row in connection.execute(
                    """SELECT name FROM sqlite_master
                    WHERE type IN ('table','index','trigger','view')
                    AND name NOT LIKE 'sqlite_%'"""
                )
            ]
        finally:
            connection.close()
        if user_objects:
            raise MigrationIntegrityError(
                "refusing to discard failed migration with persistent database objects"
            )
        database_path.unlink()
    for suffix in ("-wal", "-shm", "-journal"):
        database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)
    clear_migration_guard(database_path, operation_id=operation_id)
