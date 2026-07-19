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
