from __future__ import annotations

import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from uuid import UUID, uuid4

from .actor_context import ActorContext
from .db import connect_existing
from .vault_filesystem import (
    copy_regular_no_overwrite,
    object_relative_path,
    reject_reparse_chain,
    sha256_file,
)
from .vault_ingestion import verify_artifact_inventory
from .vault_persistence import (
    append_vault_audit,
    canonical_json,
    existing_vault_operation,
    record_vault_operation,
    request_hash,
    sha256_bytes,
    utc_now,
    verify_vault_audit_chain,
)


@dataclass(frozen=True, slots=True)
class VaultBackupResult:
    generation_id: str
    generation_root: Path
    manifest_path: Path
    manifest_sha256: str


@dataclass(frozen=True, slots=True)
class RestoreProof:
    generation_id: str
    proof_root: Path
    vault_account_id: str
    vault_instance_id: str
    artifact_count: int
    manifest_sha256: str


MAX_BACKUP_OPERATION_KEY_CHARS = 256


def _require_backup_actor(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    vault_account_id: str,
) -> None:
    actor.require_human()
    if actor.vault_account_id != vault_account_id:
        raise PermissionError("backup actor belongs to another Vault")
    row = connection.execute(
        """SELECT actor_class, status, authority_profile
        FROM actors WHERE vault_account_id=? AND id=?""",
        (vault_account_id, actor.actor_id),
    ).fetchone()
    if row is None or str(row[0]) != "human" or str(row[1]) != "active":
        raise PermissionError("backup requires an active human actor")
    authorities = {value.strip() for value in str(row[2]).split(",") if value.strip()}
    if "vault_admin" not in authorities and "*" not in authorities:
        raise PermissionError("actor is not authorized for Vault backup")


def _git_sha() -> str:
    import subprocess

    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _identity(connection: sqlite3.Connection) -> tuple[str, str, str]:
    row = connection.execute(
        "SELECT vault_account_id, vault_instance_id, identity_fingerprint FROM vault_metadata WHERE singleton_id=1"
    ).fetchone()
    if row is None:
        raise ValueError("Vault metadata singleton is missing")
    return str(row[0]), str(row[1]), str(row[2])


def _ensure_backup_ready(
    connection: sqlite3.Connection,
    vault_root: Path,
    *,
    vault_account_id: str,
) -> None:
    unresolved = connection.execute(
        "SELECT 1 FROM reconciliation_work WHERE state IN ('required','under_review','blocked') LIMIT 1"
    ).fetchone()
    if unresolved is not None:
        raise ValueError("Vault has unresolved reconciliation work")
    temp_root = vault_root / "temp"
    if any(path.is_file() for path in temp_root.rglob("*")):
        raise ValueError("Vault has unresolved temporary intake bytes")
    verify_artifact_inventory(
        connection,
        vault_root=vault_root,
        vault_account_id=vault_account_id,
    )


def _file_entry(path: Path, generation_root: Path, *, family: str, authority: str, required: bool) -> dict[str, object]:
    return {
        "path": path.relative_to(generation_root).as_posix(),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
        "file_family": family,
        "authority_class": authority,
        "required": required,
    }


def _safe_manifest_relative(relative: str) -> Path:
    windows = PureWindowsPath(relative)
    if windows.is_absolute() or windows.drive or windows.root:
        raise ValueError("backup manifest contains an unsafe path")
    if not windows.parts or any(part in {"", ".", ".."} for part in windows.parts):
        raise ValueError("backup manifest contains an unsafe path")
    return Path(*windows.parts)


def create_vault_generation(
    connection: sqlite3.Connection,
    *,
    vault_root: Path,
    actor: ActorContext,
    migration_head: str = "V0002",
    application_commit: str | None = None,
) -> VaultBackupResult:
    vault_account_id, vault_instance_id, identity_fingerprint = _identity(connection)
    _require_backup_actor(
        connection,
        actor=actor,
        vault_account_id=vault_account_id,
    )
    _ensure_backup_ready(
        connection,
        vault_root,
        vault_account_id=vault_account_id,
    )
    reject_reparse_chain(vault_root)
    operation_key = actor.correlation_id.strip()
    if not operation_key:
        raise ValueError("backup operation key is required")
    if len(operation_key) > MAX_BACKUP_OPERATION_KEY_CHARS:
        raise ValueError("backup operation key exceeds its admitted length")
    commit = application_commit or _git_sha()
    request = {
        "vault_account_id": vault_account_id,
        "vault_instance_id": vault_instance_id,
        "migration_head": migration_head,
        "application_commit": commit,
    }
    request_sha256 = request_hash(request)
    existing = existing_vault_operation(
        connection,
        actor=actor,
        operation_type="create_vault_backup",
        operation_key=operation_key,
        request_sha256=request_sha256,
    )
    if existing is not None:
        row = connection.execute(
            """SELECT lifecycle_state, manifest_sha256
            FROM backup_generations WHERE vault_account_id=? AND id=?""",
            (vault_account_id, existing),
        ).fetchone()
        generation_root = vault_root / "backups" / existing
        manifest_path = generation_root / "manifest.json"
        if (
            row is None
            or str(row[0]) != "complete"
            or row[1] is None
            or not manifest_path.is_file()
            or sha256_file(manifest_path) != str(row[1])
        ):
            raise RuntimeError("prior backup operation requires reconciliation")
        return VaultBackupResult(existing, generation_root, manifest_path, str(row[1]))

    generation_id = f"vault-backup-{uuid4()}"
    correlation_id = actor.correlation_id
    backup_root = vault_root / "backups"
    reject_reparse_chain(backup_root, stop=vault_root)
    generation_root = backup_root / generation_id
    generation_root.mkdir(parents=False, exist_ok=False)
    reject_reparse_chain(generation_root, stop=vault_root)
    now = utc_now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """INSERT INTO backup_generations
            (id, vault_account_id, vault_instance_id, correlation_id, lifecycle_state,
             started_at, completed_at, migration_head, application_commit,
             manifest_sha256, completion_marker_sha256, actor_id, failure_code)
            VALUES (?, ?, ?, ?, 'started', ?, NULL, ?, ?, NULL, NULL, ?, NULL)""",
            (
                generation_id,
                vault_account_id,
                vault_instance_id,
                correlation_id,
                now,
                migration_head,
                commit,
                actor.actor_id,
            ),
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="backup_generation",
            record_id=generation_id,
            payload={"state": "started", **request},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        shutil.rmtree(generation_root, ignore_errors=True)
        raise

    files: list[dict[str, object]] = []
    try:
        database_dir = generation_root / "database"
        database_dir.mkdir()
        backup_database = database_dir / "vault.sqlite3"
        target = sqlite3.connect(backup_database)
        try:
            connection.backup(target)
        finally:
            target.close()
        files.append(
            _file_entry(
                backup_database,
                generation_root,
                family="database",
                authority="canonical",
                required=True,
            )
        )
        object_rows = connection.execute(
            """SELECT storage_relative_path, sha256, byte_size
            FROM artifact_objects WHERE vault_account_id=? ORDER BY storage_relative_path""",
            (vault_account_id,),
        ).fetchall()
        for row in object_rows:
            relative = str(row[0])
            if relative != object_relative_path(str(row[1])):
                raise ValueError("artifact object path is outside the canonical content address")
            source = vault_root / _safe_manifest_relative(relative)
            reject_reparse_chain(source, stop=vault_root)
            if source.stat().st_size != int(row[2]) or sha256_file(source) != str(row[1]):
                raise ValueError("artifact object bytes do not match Vault authority")
            destination = generation_root / Path(relative)
            copy_regular_no_overwrite(source, destination, root=generation_root)
            files.append(
                _file_entry(
                    destination,
                    generation_root,
                    family="object",
                    authority="canonical",
                    required=True,
                )
            )
        manifest = {
            "schema_version": 1,
            "generation_id": generation_id,
            "vault_account_id": vault_account_id,
            "vault_instance_id": vault_instance_id,
            "identity_fingerprint": identity_fingerprint,
            "migration_head": migration_head,
            "application_commit": commit,
            "created_at": now,
            "derived_state_authoritative": False,
            "files": files,
        }
        manifest_path = generation_root / "manifest.json"
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        with manifest_path.open("xb") as stream:
            stream.write(manifest_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        manifest_sha256 = sha256_bytes(manifest_bytes)
        complete_path = generation_root / "COMPLETE"
        complete_bytes = canonical_json(
            {
                "generation_id": generation_id,
                "manifest_sha256": manifest_sha256,
                "vault_account_id": vault_account_id,
                "vault_instance_id": vault_instance_id,
            }
        ) + b"\n"
        with complete_path.open("xb") as stream:
            stream.write(complete_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        completion_sha256 = sha256_bytes(complete_bytes)
        completed_at = utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            for entry in files:
                connection.execute(
                    """INSERT INTO backup_generation_files
                    (id, vault_account_id, generation_id, relative_path, file_family,
                     sha256, byte_size, authority_class, required)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"backup-file-{uuid4()}",
                        vault_account_id,
                        generation_id,
                        entry["path"],
                        entry["file_family"],
                        entry["sha256"],
                        entry["byte_size"],
                        entry["authority_class"],
                        1 if entry["required"] else 0,
                    ),
                )
            updated = connection.execute(
                """UPDATE backup_generations
                SET lifecycle_state='complete', completed_at=?, manifest_sha256=?,
                    completion_marker_sha256=?
                WHERE vault_account_id=? AND id=? AND lifecycle_state='started'""",
                (
                    completed_at,
                    manifest_sha256,
                    completion_sha256,
                    vault_account_id,
                    generation_id,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("backup generation state changed during finalization")
            record_vault_operation(
                connection,
                actor=actor,
                operation_type="create_vault_backup",
                operation_key=operation_key,
                request_sha256=request_sha256,
                result_ref=generation_id,
            )
            append_vault_audit(
                connection,
                actor=actor,
                authority_operation="vault_admin",
                request_sha256=request_sha256,
                record_type="backup_generation",
                record_id=generation_id,
                payload={
                    "state": "complete",
                    "manifest_sha256": manifest_sha256,
                    "completion_marker_sha256": completion_sha256,
                    "file_count": len(files),
                },
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return VaultBackupResult(generation_id, generation_root, manifest_path, manifest_sha256)
    except Exception as exc:
        connection.rollback()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """UPDATE backup_generations
                SET lifecycle_state='reconciliation_required', completed_at=?, failure_code=?
                WHERE vault_account_id=? AND id=? AND lifecycle_state='started'""",
                (utc_now(), type(exc).__name__, vault_account_id, generation_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
        raise


def verify_vault_generation(
    generation_root: Path,
    *,
    expected_vault_account_id: str | None = None,
    expected_vault_instance_id: str | None = None,
    expected_migration_head: str = "V0002",
    authority_connection: sqlite3.Connection | None = None,
) -> dict[str, object]:
    reject_reparse_chain(generation_root)
    manifest_path = generation_root / "manifest.json"
    complete_path = generation_root / "COMPLETE"
    if not manifest_path.is_file() or not complete_path.is_file():
        raise ValueError("backup generation is incomplete")
    manifest_bytes = manifest_path.read_bytes()
    complete_bytes = complete_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    complete = json.loads(complete_bytes.decode("utf-8"))
    manifest_sha256 = sha256_bytes(manifest_bytes)
    completion_sha256 = sha256_bytes(complete_bytes)
    if complete.get("manifest_sha256") != manifest_sha256:
        raise ValueError("backup completion marker does not match the manifest")
    if manifest.get("generation_id") != generation_root.name or complete.get("generation_id") != generation_root.name:
        raise ValueError("backup generation identity mismatch")
    vault_account_id = str(manifest.get("vault_account_id", ""))
    vault_instance_id = str(manifest.get("vault_instance_id", ""))
    if (
        complete.get("vault_account_id") != vault_account_id
        or complete.get("vault_instance_id") != vault_instance_id
    ):
        raise ValueError("backup completion identity does not match the manifest")
    if expected_vault_account_id is not None and vault_account_id != expected_vault_account_id:
        raise ValueError("backup belongs to another Vault account")
    if expected_vault_instance_id is not None and vault_instance_id != expected_vault_instance_id:
        raise ValueError("backup belongs to another Vault instance")
    if manifest.get("migration_head") != expected_migration_head:
        raise ValueError("backup migration head is not admitted")
    expected_paths: set[str] = set()
    for entry in manifest.get("files", []):
        relative = str(entry["path"])
        relative_path = _safe_manifest_relative(relative)
        if relative in expected_paths:
            raise ValueError("backup manifest contains a duplicate path")
        candidate = generation_root / relative_path
        reject_reparse_chain(candidate, stop=generation_root)
        if not candidate.is_file():
            raise ValueError(f"backup file missing: {relative}")
        if candidate.stat().st_size != int(entry["byte_size"]):
            raise ValueError(f"backup file size mismatch: {relative}")
        if sha256_file(candidate) != str(entry["sha256"]):
            raise ValueError(f"backup file hash mismatch: {relative}")
        expected_paths.add(relative)
    if authority_connection is not None:
        generation_row = authority_connection.execute(
            """SELECT lifecycle_state, vault_instance_id, migration_head,
                      manifest_sha256, completion_marker_sha256
            FROM backup_generations WHERE vault_account_id=? AND id=?""",
            (vault_account_id, generation_root.name),
        ).fetchone()
        if generation_row is None or str(generation_row[0]) not in {"complete", "verified"}:
            raise ValueError("backup generation is not complete in Vault authority")
        if (
            str(generation_row[1]) != vault_instance_id
            or str(generation_row[2]) != expected_migration_head
            or str(generation_row[3]) != manifest_sha256
            or str(generation_row[4]) != completion_sha256
        ):
            raise ValueError("backup generation authority does not match filesystem evidence")
        recorded_files = {
            str(row[0]): (str(row[1]), int(row[2]), str(row[3]), str(row[4]), bool(row[5]))
            for row in authority_connection.execute(
                """SELECT relative_path, sha256, byte_size, file_family,
                          authority_class, required
                FROM backup_generation_files
                WHERE vault_account_id=? AND generation_id=?""",
                (vault_account_id, generation_root.name),
            )
        }
        manifest_files = {
            str(entry["path"]): (
                str(entry["sha256"]),
                int(entry["byte_size"]),
                str(entry["file_family"]),
                str(entry["authority_class"]),
                bool(entry["required"]),
            )
            for entry in manifest.get("files", [])
        }
        if recorded_files != manifest_files:
            raise ValueError("backup generation file receipts do not match the manifest")
    database_path = generation_root / "database" / "vault.sqlite3"
    connection = connect_existing(database_path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("backup SQLite integrity check failed")
        head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        if head is None or str(head[0]) != expected_migration_head:
            raise ValueError("backup database migration head mismatch")
        metadata = connection.execute(
            "SELECT vault_account_id, vault_instance_id, identity_fingerprint FROM vault_metadata WHERE singleton_id=1"
        ).fetchone()
        if metadata is None or str(metadata[0]) != vault_account_id or str(metadata[1]) != vault_instance_id:
            raise ValueError("backup database identity mismatch")
        if str(metadata[2]) != str(manifest.get("identity_fingerprint", "")):
            raise ValueError("backup identity fingerprint mismatch")
        if not verify_vault_audit_chain(connection):
            raise ValueError("backup audit chain verification failed")
        object_rows = connection.execute(
            "SELECT storage_relative_path, sha256, byte_size FROM artifact_objects ORDER BY storage_relative_path"
        ).fetchall()
        authoritative = {str(row[0]): (str(row[1]), int(row[2])) for row in object_rows}
        manifest_objects = {
            str(entry["path"]): (str(entry["sha256"]), int(entry["byte_size"]))
            for entry in manifest.get("files", [])
            if entry.get("file_family") == "object"
        }
        if authoritative != manifest_objects:
            raise ValueError("backup artifact manifest does not reconcile with SQLite authority")
    finally:
        connection.close()
    actual = {
        path.relative_to(generation_root).as_posix()
        for path in generation_root.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "COMPLETE"}
    }
    if actual != expected_paths:
        raise ValueError("backup generation contains unmanifested or missing files")
    return {
        "generation_id": generation_root.name,
        "vault_account_id": vault_account_id,
        "vault_instance_id": vault_instance_id,
        "manifest_sha256": manifest_sha256,
        "file_count": len(expected_paths),
        "artifact_count": sum(1 for entry in manifest.get("files", []) if entry.get("file_family") == "object"),
    }


def restore_generation_disposable(
    generation_root: Path,
    proof_root: Path,
    *,
    expected_vault_account_id: str,
    expected_vault_instance_id: str,
    authority_connection: sqlite3.Connection | None = None,
) -> RestoreProof:
    if proof_root.exists() and any(proof_root.iterdir()):
        raise ValueError("disposable restore target is not empty")
    verification = verify_vault_generation(
        generation_root,
        expected_vault_account_id=expected_vault_account_id,
        expected_vault_instance_id=expected_vault_instance_id,
        authority_connection=authority_connection,
    )
    proof_root.mkdir(parents=True, exist_ok=True)
    if any(proof_root.iterdir()):
        raise ValueError("disposable restore target changed before restore")
    for source in sorted(path for path in generation_root.rglob("*") if path.is_file()):
        relative = source.relative_to(generation_root)
        if relative.as_posix() in {"manifest.json", "COMPLETE"}:
            continue
        destination = proof_root / relative
        copy_regular_no_overwrite(source, destination, root=proof_root)
    restored_db = proof_root / "database" / "vault.sqlite3"
    connection = connect_existing(restored_db)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("disposable restore integrity check failed")
        if not verify_vault_audit_chain(connection):
            raise ValueError("disposable restore audit chain verification failed")
    finally:
        connection.close()
    return RestoreProof(
        generation_id=str(verification["generation_id"]),
        proof_root=proof_root,
        vault_account_id=expected_vault_account_id,
        vault_instance_id=expected_vault_instance_id,
        artifact_count=int(verification["artifact_count"]),
        manifest_sha256=str(verification["manifest_sha256"]),
    )


def _validate_generation_id(generation_id: str) -> str:
    normalized = generation_id.strip()
    prefix = "vault-backup-"
    if not normalized.startswith(prefix) or len(normalized) > 64:
        raise ValueError("backup generation ID is invalid")
    try:
        UUID(normalized.removeprefix(prefix))
    except ValueError as exc:
        raise ValueError("backup generation ID is invalid") from exc
    return normalized


def verify_and_restore_generation(
    connection: sqlite3.Connection,
    *,
    vault_root: Path,
    actor: ActorContext,
    generation_id: str,
    proof_root: Path,
    expected_migration_head: str = "V0002",
) -> RestoreProof:
    vault_account_id, vault_instance_id, _ = _identity(connection)
    _require_backup_actor(
        connection,
        actor=actor,
        vault_account_id=vault_account_id,
    )
    operation_key = actor.correlation_id.strip()
    if not operation_key or len(operation_key) > MAX_BACKUP_OPERATION_KEY_CHARS:
        raise ValueError("backup verification operation key is invalid")
    normalized_generation = _validate_generation_id(generation_id)
    request_sha256 = request_hash(
        {
            "vault_account_id": vault_account_id,
            "vault_instance_id": vault_instance_id,
            "generation_id": normalized_generation,
            "expected_migration_head": expected_migration_head,
        }
    )
    generation_root = vault_root / "backups" / normalized_generation
    proof = restore_generation_disposable(
        generation_root,
        proof_root,
        expected_vault_account_id=vault_account_id,
        expected_vault_instance_id=vault_instance_id,
        authority_connection=connection,
    )
    existing = existing_vault_operation(
        connection,
        actor=actor,
        operation_type="verify_vault_backup",
        operation_key=operation_key,
        request_sha256=request_sha256,
    )
    if existing is not None:
        if existing != normalized_generation:
            raise RuntimeError("prior backup verification result is invalid")
        return proof

    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            """SELECT lifecycle_state FROM backup_generations
            WHERE vault_account_id=? AND id=?""",
            (vault_account_id, normalized_generation),
        ).fetchone()
        if row is None or str(row[0]) not in {"complete", "verified"}:
            raise ValueError("backup generation is not eligible for verification")
        if str(row[0]) == "complete":
            connection.execute(
                """UPDATE backup_generations SET lifecycle_state='verified'
                WHERE vault_account_id=? AND id=? AND lifecycle_state='complete'""",
                (vault_account_id, normalized_generation),
            )
        record_vault_operation(
            connection,
            actor=actor,
            operation_type="verify_vault_backup",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=normalized_generation,
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="backup_generation",
            record_id=normalized_generation,
            payload={
                "state": "verified",
                "artifact_count": proof.artifact_count,
            },
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return proof
