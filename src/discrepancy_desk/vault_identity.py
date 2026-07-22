from __future__ import annotations

import json
import os
import sqlite3
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from .actor_context import ActorContext
from .db import connect_existing
from .migration_integrity import assert_clean_migration_state
from .migration_runner import run_guarded_upgrade
from .migration_spec import MigrationSpec
from .vault_persistence import (
    append_cross_database_receipt,
    append_vault_audit,
    sha256_bytes,
    verify_vault_audit_chain,
)
from .vault_registry import VaultRegistryRecord

SCHEMA_NAME = "m06a-vault"
MARKER_NAME = "VAULT_IDENTITY.json"
RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{value}" for value in range(1, 10)),
    *(f"LPT{value}" for value in range(1, 10)),
}
INVALID_WINDOWS_CHARS = set('<>:"/\\|?*')


@dataclass(frozen=True, slots=True)
class VaultIdentity:
    vault_schema_name: str
    vault_account_id: str
    vault_instance_id: str
    created_at: str
    identity_fingerprint: str

    def marker(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class OpenedVault:
    identity: VaultIdentity
    root: Path
    database_path: Path
    connection: sqlite3.Connection

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "OpenedVault":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _identity_material(
    *, vault_account_id: str, vault_instance_id: str, created_at: str
) -> dict[str, str]:
    return {
        "created_at": created_at,
        "vault_account_id": vault_account_id,
        "vault_instance_id": vault_instance_id,
        "vault_schema_name": SCHEMA_NAME,
    }


def new_vault_identity(
    vault_account_id: str,
    *,
    vault_instance_id: str | None = None,
    created_at: str | None = None,
) -> VaultIdentity:
    instance = vault_instance_id or str(uuid4())
    created = created_at or _utc_now()
    material = _identity_material(
        vault_account_id=vault_account_id,
        vault_instance_id=instance,
        created_at=created,
    )
    return VaultIdentity(
        **material,
        identity_fingerprint=sha256_bytes(
            json.dumps(material, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ),
    )


def validate_identity(identity: VaultIdentity) -> None:
    if identity.vault_schema_name != SCHEMA_NAME:
        raise ValueError("Vault schema identity mismatch")
    expected = new_vault_identity(
        identity.vault_account_id,
        vault_instance_id=identity.vault_instance_id,
        created_at=identity.created_at,
    ).identity_fingerprint
    if identity.identity_fingerprint != expected:
        raise ValueError("Vault identity fingerprint mismatch")


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(path):
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _reject_reparse_chain(path: Path, *, stop: Path | None = None) -> None:
    current = path
    while True:
        if current.exists() and _is_reparse(current):
            raise ValueError(f"Vault path contains a reparse point: {current.name}")
        if stop is not None and current == stop:
            return
        if current.parent == current:
            return
        current = current.parent


def _validate_segment(segment: str) -> None:
    if segment in {"", ".", ".."}:
        raise ValueError("Vault relative root contains an invalid segment")
    if segment.endswith((" ", ".")):
        raise ValueError("Vault path segment has a trailing dot or space")
    if any(ord(value) < 32 or value in INVALID_WINDOWS_CHARS for value in segment):
        raise ValueError("Vault path segment contains a Windows-invalid character")
    stem = segment.split(".", 1)[0].upper()
    if stem in RESERVED_WINDOWS_NAMES:
        raise ValueError("Vault path segment is a reserved Windows name")


def resolve_vault_root(
    vault_base: Path,
    relative_root: str,
    *,
    must_exist: bool,
) -> tuple[str, Path]:
    windows = PureWindowsPath(relative_root)
    if windows.is_absolute() or windows.drive or windows.root:
        raise ValueError("Vault root must be a relative path")
    parts = tuple(windows.parts)
    if not parts:
        raise ValueError("Vault relative root is required")
    for part in parts:
        _validate_segment(part)
    normalized = "/".join(parts)
    base = vault_base.resolve(strict=False)
    if vault_base.exists():
        _reject_reparse_chain(vault_base)
    current = base
    for part in parts:
        if current.exists():
            names = {child.name.casefold(): child.name for child in current.iterdir()}
            existing = names.get(part.casefold())
            if existing is not None and existing != part:
                raise ValueError("Vault path has a case-insensitive collision")
        current = current / part
        if current.exists() and _is_reparse(current):
            raise ValueError("Vault root contains a symlink, junction, or reparse point")
    if must_exist and not current.is_dir():
        raise FileNotFoundError(current)
    return normalized, current


def _read_marker(path: Path) -> VaultIdentity:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Vault identity marker is missing or malformed") from exc
    required = {
        "vault_schema_name", "vault_account_id", "vault_instance_id",
        "created_at", "identity_fingerprint",
    }
    if set(payload) != required or any(not isinstance(payload[name], str) for name in required):
        raise ValueError("Vault identity marker has invalid fields")
    identity = VaultIdentity(**payload)
    validate_identity(identity)
    return identity


def create_vault(
    *,
    vault_base: Path,
    relative_root: str,
    vault_account_id: str,
    owner_actor_id: str,
    migration_spec: MigrationSpec,
    operation_id: str,
    correlation_id: str,
    request_sha256: str,
) -> VaultIdentity:
    normalized, root = resolve_vault_root(vault_base, relative_root, must_exist=False)
    vault_base.mkdir(parents=True, exist_ok=True)
    _reject_reparse_chain(vault_base)
    if root.exists():
        raise FileExistsError(root)
    root.mkdir(parents=True, exist_ok=False)
    for relative in (
        "database", "objects/sha256", "packages/sha256", "projections/markdown",
        "projections/html", "temp", "backups",
    ):
        (root / relative).mkdir(parents=True, exist_ok=False)
    identity = new_vault_identity(vault_account_id)
    database_path = root / "database" / "vault.sqlite3"
    run_guarded_upgrade(
        database_path,
        migration_spec,
        operation_id=operation_id,
        allow_create=True,
        identity=identity.marker(),
    )
    connection = connect_existing(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO vault_metadata VALUES (1, ?, ?, ?, ?, ?)",
            (
                identity.vault_account_id,
                identity.vault_instance_id,
                identity.vault_schema_name,
                identity.created_at,
                identity.identity_fingerprint,
            ),
        )
        connection.execute(
            """INSERT INTO actors
            (id, vault_account_id, actor_class, display_name, status,
             authority_profile, created_at, created_by_actor_id)
            VALUES (?, ?, 'human', 'Local Owner', 'active', 'vault_admin,human_decision,read', ?, NULL)""",
            (owner_actor_id, vault_account_id, identity.created_at),
        )
        connection.execute(
            """INSERT INTO actor_status_history
            (id, vault_account_id, actor_id, prior_status, new_status,
             changed_at, changed_by_actor_id, reason)
            VALUES (?, ?, ?, NULL, 'active', ?, ?, 'governed Vault creation')""",
            (str(uuid4()), vault_account_id, owner_actor_id, identity.created_at, owner_actor_id),
        )
        actor = ActorContext(
            actor_id=owner_actor_id,
            actor_class="human",
            vault_account_id=vault_account_id,
            correlation_id=correlation_id,
            authentication_source="governed-vault-creation",
            allowed_operation_class="vault_admin",
        )
        append_cross_database_receipt(
            connection,
            vault_account_id=vault_account_id,
            correlation_id=correlation_id,
            operation_type="provision_vault",
            stage="central_started",
            request_sha256=request_sha256,
            result_sha256=None,
            detail={"relative_root": normalized},
        )
        append_cross_database_receipt(
            connection,
            vault_account_id=vault_account_id,
            correlation_id=correlation_id,
            operation_type="provision_vault",
            stage="vault_committed",
            request_sha256=request_sha256,
            result_sha256=identity.identity_fingerprint,
            detail={"vault_instance_id": identity.vault_instance_id},
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="vault_metadata",
            record_id=vault_account_id,
            payload={"identity": identity.marker(), "relative_root": normalized},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    marker = root / MARKER_NAME
    with marker.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(identity.marker(), indent=2, sort_keys=True) + "\n")
    return identity


def open_existing_vault(
    *,
    vault_base: Path,
    registry: VaultRegistryRecord,
    migration_spec: MigrationSpec,
) -> OpenedVault:
    if registry.registry_state != "registered":
        raise ValueError("Vault registry state is not available")
    normalized, root = resolve_vault_root(vault_base, registry.relative_root, must_exist=True)
    if normalized != registry.relative_root.replace("\\", "/"):
        raise ValueError("Vault registry relative root is not canonical")
    required_paths = [
        root, root / MARKER_NAME, root / "database", root / "database" / "vault.sqlite3",
        root / "objects", root / "packages", root / "temp", root / "backups",
    ]
    for candidate in required_paths:
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        if _is_reparse(candidate):
            raise ValueError("Vault path contains a symlink, junction, or reparse point")
    identity = _read_marker(root / MARKER_NAME)
    if (
        identity.vault_account_id != registry.vault_id
        or identity.vault_instance_id != registry.vault_instance_id
        or identity.identity_fingerprint != registry.expected_identity_fingerprint
    ):
        raise ValueError("Vault registry and marker identity mismatch")
    database_path = root / "database" / "vault.sqlite3"
    assert_clean_migration_state(database_path)
    connection = connect_existing(database_path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Vault SQLite integrity check failed")
        revision = connection.execute(
            f"SELECT version_num FROM {migration_spec.version_table}"
        ).fetchone()
        if revision is None or str(revision[0]) != migration_spec.expected_head:
            raise ValueError("Vault migration head mismatch")
        row = connection.execute(
            """SELECT vault_account_id, vault_instance_id, vault_schema_name,
                      created_at, identity_fingerprint
            FROM vault_metadata WHERE singleton_id=1"""
        ).fetchone()
        if row is None:
            raise ValueError("Vault metadata singleton is missing")
        database_identity = VaultIdentity(
            vault_account_id=str(row[0]), vault_instance_id=str(row[1]),
            vault_schema_name=str(row[2]), created_at=str(row[3]),
            identity_fingerprint=str(row[4]),
        )
        validate_identity(database_identity)
        if database_identity != identity:
            raise ValueError("Vault marker and database identity mismatch")
        if not verify_vault_audit_chain(connection):
            raise ValueError("Vault audit chain verification failed")
        return OpenedVault(identity=identity, root=root, database_path=database_path, connection=connection)
    except Exception:
        connection.close()
        raise
