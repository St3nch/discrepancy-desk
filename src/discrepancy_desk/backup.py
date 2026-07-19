from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2

from .db import connect
from .persistence import verify_audit_chain


@dataclass(frozen=True)
class BackupResult:
    generation_id: str
    generation_root: Path
    manifest_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_generation(
    source_db: Path,
    evidence_root: Path,
    destination_root: Path,
) -> BackupResult:
    generation_id = datetime.now(timezone.utc).strftime("dd-backup-%Y%m%dT%H%M%S%fZ")
    generation = destination_root / generation_id
    db_dir = generation / "database"
    evidence_dir = generation / "evidence"
    db_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)

    backup_db = db_dir / "discrepancy-desk.sqlite3"
    source = sqlite3.connect(source_db)
    target = sqlite3.connect(backup_db)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    files: list[dict[str, object]] = []
    files.append(
        {
            "path": backup_db.relative_to(generation).as_posix(),
            "sha256": _sha256(backup_db),
            "byte_size": backup_db.stat().st_size,
        }
    )

    if evidence_root.exists():
        for source_path in sorted(path for path in evidence_root.rglob("*") if path.is_file()):
            relative = source_path.relative_to(evidence_root)
            destination = evidence_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy2(source_path, destination)
            files.append(
                {
                    "path": destination.relative_to(generation).as_posix(),
                    "sha256": _sha256(destination),
                    "byte_size": destination.stat().st_size,
                }
            )

    manifest = {
        "generation_id": generation_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "files": files,
    }
    manifest_path = generation / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return BackupResult(generation_id, generation, manifest_path)


def verify_generation(generation_root: Path) -> None:
    manifest_path = generation_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        candidate = generation_root / entry["path"]
        if not candidate.is_file():
            raise ValueError(f"backup file missing: {entry['path']}")
        if candidate.stat().st_size != entry["byte_size"]:
            raise ValueError(f"backup size mismatch: {entry['path']}")
        if _sha256(candidate) != entry["sha256"]:
            raise ValueError(f"backup hash mismatch: {entry['path']}")

    database_path = generation_root / "database" / "discrepancy-desk.sqlite3"
    connection = connect(database_path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("restored database integrity check failed")
        if not verify_audit_chain(connection):
            raise ValueError("restored audit chain verification failed")

        referenced: set[str] = set()
        for row in connection.execute(
            "SELECT relative_path, sha256, byte_size FROM evidence_refs ORDER BY relative_path"
        ):
            relative_path = str(row[0])
            referenced.add(relative_path)
            candidate = generation_root / "evidence" / relative_path
            if not candidate.is_file():
                raise ValueError(f"restored evidence missing: {relative_path}")
            if candidate.stat().st_size != row[2]:
                raise ValueError(f"database/evidence size disagreement: {relative_path}")
            if _sha256(candidate) != row[1]:
                raise ValueError(f"database/evidence hash disagreement: {relative_path}")

        actual = {
            path.relative_to(generation_root / "evidence").as_posix()
            for path in (generation_root / "evidence").rglob("*")
            if path.is_file()
        }
        orphaned = sorted(actual - referenced)
        if orphaned:
            raise ValueError(f"restored orphan evidence: {orphaned[0]}")
    finally:
        connection.close()
