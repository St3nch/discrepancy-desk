from __future__ import annotations

import hashlib
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
    payload = (
        '{\n'
        f'  "operation_id": "{operation_id}",\n'
        f'  "target_revision": "{target_revision}"\n'
        '}\n'
    )
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise MigrationIntegrityError("migration dirty marker already exists") from exc
    return marker


def clear_migration_guard(database_path: Path, *, operation_id: str) -> None:
    marker = dirty_marker_path(database_path)
    if not marker.is_file():
        raise MigrationIntegrityError("migration dirty marker is missing")
    text = marker.read_text(encoding="utf-8")
    if f'"operation_id": "{operation_id}"' not in text:
        raise MigrationIntegrityError("migration dirty marker operation mismatch")
    marker.unlink()
