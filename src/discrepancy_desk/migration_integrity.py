from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .migration_spec import MigrationSpec


class MigrationIntegrityError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _manifest_files(spec: MigrationSpec) -> dict[str, Path]:
    resolved = spec.resolved()
    versions = resolved.migrations_root / "versions"
    if not versions.is_dir():
        raise MigrationIntegrityError("migration versions directory is missing")
    files = {
        "alembic.ini": resolved.config_path,
        "env.py": resolved.migrations_root / "env.py",
        "script.py.mako": resolved.migrations_root / "script.py.mako",
    }
    for candidate in sorted(versions.glob("*.py")):
        files[f"versions/{candidate.name}"] = candidate
    return files


def verify_manifest(spec: MigrationSpec) -> str:
    resolved = spec.resolved()
    manifest = resolved.manifest_path
    if not manifest.is_file():
        raise MigrationIntegrityError("migration manifest is missing")
    expected_files = _manifest_files(resolved)
    recorded: dict[str, str] = {}
    for line_number, raw_line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            name, expected = line.split(maxsplit=1)
        except ValueError as exc:
            raise MigrationIntegrityError(f"malformed manifest line {line_number}") from exc
        if name in recorded:
            raise MigrationIntegrityError(f"duplicate migration manifest entry: {name}")
        if len(expected) != 64 or any(value not in "0123456789abcdef" for value in expected):
            raise MigrationIntegrityError(f"invalid migration hash: {name}")
        recorded[name] = expected
    if set(recorded) != set(expected_files):
        missing = sorted(set(expected_files) - set(recorded))
        extra = sorted(set(recorded) - set(expected_files))
        raise MigrationIntegrityError(
            f"migration manifest coverage mismatch: missing={missing}, extra={extra}"
        )
    for name, candidate in expected_files.items():
        if not candidate.is_file():
            raise MigrationIntegrityError(f"migration resource is missing: {name}")
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != recorded[name]:
            raise MigrationIntegrityError(f"migration hash mismatch: {name}")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def dirty_marker_path(database_path: Path) -> Path:
    return database_path.with_name(database_path.name + ".migration-dirty.json")


def assert_clean_migration_state(database_path: Path) -> None:
    marker = dirty_marker_path(database_path)
    if marker.exists():
        raise MigrationIntegrityError(f"database migration state is dirty: {marker.name}")


def begin_migration_guard(
    database_path: Path,
    *,
    operation_id: str,
    target_revision: str,
    spec: MigrationSpec | None = None,
    from_revision: str | None = None,
    identity: dict[str, str] | None = None,
    manifest_sha256: str | None = None,
) -> Path:
    marker = dirty_marker_path(database_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "operation_id": operation_id,
        "target_revision": target_revision,
        "started_at": _utc_now(),
    }
    if spec is not None:
        payload.update(
            {
                "schema_name": spec.schema_name,
                "expected_head": spec.expected_head,
                "version_table": spec.version_table,
                "manifest_sha256": manifest_sha256 or verify_manifest(spec),
                "from_revision": from_revision,
                "identity": identity or {},
            }
        )
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise MigrationIntegrityError("migration dirty marker already exists") from exc
    return marker


def clear_migration_guard(database_path: Path, *, operation_id: str) -> None:
    marker = dirty_marker_path(database_path)
    payload = read_migration_guard(database_path)
    if payload.get("operation_id") != operation_id:
        raise MigrationIntegrityError("migration dirty marker operation mismatch")
    marker.unlink()


def read_migration_guard(database_path: Path) -> dict[str, object]:
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
    return payload


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


def recover_completed_migration(
    database_path: Path,
    spec: MigrationSpec,
    *,
    operation_id: str,
    identity: dict[str, str] | None = None,
) -> None:
    payload = read_migration_guard(database_path)
    resolved = spec.resolved()
    if payload["operation_id"] != operation_id:
        raise MigrationIntegrityError("migration recovery operation mismatch")
    manifest_sha256 = verify_manifest(resolved)
    expected = {
        "schema_name": resolved.schema_name,
        "expected_head": resolved.expected_head,
        "version_table": resolved.version_table,
        "manifest_sha256": manifest_sha256,
        "identity": identity or {},
    }
    for name, value in expected.items():
        if payload.get(name) != value:
            raise MigrationIntegrityError(f"migration recovery {name} mismatch")
    if not database_path.is_file():
        raise MigrationIntegrityError("cannot recover completed migration: database is missing")
    connection = sqlite3.connect(database_path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MigrationIntegrityError("cannot recover completed migration: integrity check failed")
    finally:
        connection.close()
    if _current_revision(database_path, resolved.version_table) != resolved.expected_head:
        raise MigrationIntegrityError("cannot recover completed migration: expected head is missing")
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
