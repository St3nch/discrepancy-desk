from __future__ import annotations

import sqlite3
from pathlib import Path

from .actor_context import ActorContext, resolve_actor_context
from .migration_runner import run_guarded_upgrade
from .migration_spec import MigrationSpec
from .parser_service import install_under_test_parser_candidate
from .vault_filesystem import ArtifactIntegrityError
from .vault_identity import OpenedVault, open_existing_vault
from .vault_ingestion import verify_artifact_inventory
from .vault_persistence import (
    append_vault_audit,
    existing_vault_operation,
    record_vault_operation,
    request_hash,
)
from .vault_registry import get_vault, list_vaults


def open_registered_vault(
    central_connection: sqlite3.Connection,
    *,
    vault_base: Path,
    vault_id: str,
    migration_spec: MigrationSpec,
) -> OpenedVault:
    registry = get_vault(central_connection, vault_id)
    return open_existing_vault(
        vault_base=vault_base,
        registry=registry,
        migration_spec=migration_spec,
    )


def _migration_actor(
    connection: sqlite3.Connection,
    *,
    vault_id: str,
    actor_id: str,
    operation_id: str,
) -> ActorContext:
    return resolve_actor_context(
        connection,
        vault_account_id=vault_id,
        actor_id=actor_id,
        correlation_id=operation_id,
        authentication_source="desktop-loopback-server-resolved",
        allowed_operation_class="vault_admin",
        require_actor_class="human",
    )


def _complete_migration_audit(
    opened: OpenedVault,
    *,
    actor: ActorContext,
    operation_id: str,
    request_sha256: str,
    target_head: str,
) -> None:
    completed = opened.connection.execute(
        """SELECT count(*) FROM audit_events
        WHERE vault_account_id=? AND record_type='vault_migration'
          AND record_id=? AND authority_operation='vault_admin'""",
        (actor.vault_account_id, operation_id),
    ).fetchone()[0]
    if int(completed) >= 2:
        return
    opened.connection.execute("BEGIN IMMEDIATE")
    try:
        append_vault_audit(
            opened.connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="vault_migration",
            record_id=operation_id,
            payload={"state": "completed", "target_head": target_head},
        )
        opened.connection.commit()
    except Exception:
        opened.connection.rollback()
        raise


def upgrade_registered_vault(
    central_connection: sqlite3.Connection,
    *,
    vault_base: Path,
    vault_id: str,
    migration_spec: MigrationSpec,
    operation_id: str,
    actor_id: str,
) -> OpenedVault:
    normalized_operation = operation_id.strip()
    if not normalized_operation or len(normalized_operation) > 256:
        raise ValueError("Vault migration operation key is invalid")
    registry = get_vault(central_connection, vault_id)
    current_error_message: str | None = None
    try:
        current = open_existing_vault(
            vault_base=vault_base,
            registry=registry,
            migration_spec=migration_spec,
        )
    except ValueError as exc:
        current_error_message = str(exc)
        current = None
    if current is not None:
        actor = _migration_actor(
            current.connection,
            vault_id=vault_id,
            actor_id=actor_id,
            operation_id=normalized_operation,
        )
        request_sha256 = request_hash(
            {
                "vault_id": vault_id,
                "identity_fingerprint": current.identity.identity_fingerprint,
                "target_head": migration_spec.expected_head,
            }
        )
        existing = existing_vault_operation(
            current.connection,
            actor=actor,
            operation_type="upgrade_vault_schema",
            operation_key=normalized_operation,
            request_sha256=request_sha256,
        )
        if existing != migration_spec.expected_head:
            current.close()
            raise ValueError("Vault is already at the expected migration head")
        if migration_spec.expected_head == "V0003":
            install_under_test_parser_candidate(
                current.connection,
                actor_id=actor_id,
                project_root=migration_spec.migrations_root.parent,
            )
        _complete_migration_audit(
            current,
            actor=actor,
            operation_id=normalized_operation,
            request_sha256=request_sha256,
            target_head=migration_spec.expected_head,
        )
        return current

    previous_head = "V0002" if migration_spec.expected_head == "V0003" else "V0001"
    previous = MigrationSpec(
        config_path=migration_spec.config_path,
        migrations_root=migration_spec.migrations_root,
        manifest_path=migration_spec.manifest_path,
        expected_head=previous_head,
        schema_name=migration_spec.schema_name,
        version_table=migration_spec.version_table,
    )
    try:
        previous_opened = open_existing_vault(
            vault_base=vault_base,
            registry=registry,
            migration_spec=previous,
        )
    except Exception as exc:
        raise ValueError(
            current_error_message or "Vault migration source head is not admitted"
        ) from exc
    with previous_opened as opened:
        database_path = opened.database_path
        identity = opened.identity.marker()
        actor = _migration_actor(
            opened.connection,
            vault_id=vault_id,
            actor_id=actor_id,
            operation_id=normalized_operation,
        )
        request_sha256 = request_hash(
            {
                "vault_id": vault_id,
                "identity_fingerprint": opened.identity.identity_fingerprint,
                "target_head": migration_spec.expected_head,
            }
        )
        existing = existing_vault_operation(
            opened.connection,
            actor=actor,
            operation_type="upgrade_vault_schema",
            operation_key=normalized_operation,
            request_sha256=request_sha256,
        )
        if existing is None:
            opened.connection.execute("BEGIN IMMEDIATE")
            try:
                record_vault_operation(
                    opened.connection,
                    actor=actor,
                    operation_type="upgrade_vault_schema",
                    operation_key=normalized_operation,
                    request_sha256=request_sha256,
                    result_ref=migration_spec.expected_head,
                )
                append_vault_audit(
                    opened.connection,
                    actor=actor,
                    authority_operation="vault_admin",
                    request_sha256=request_sha256,
                    record_type="vault_migration",
                    record_id=normalized_operation,
                    payload={"state": "requested", "target_head": migration_spec.expected_head},
                )
                opened.connection.commit()
            except Exception:
                opened.connection.rollback()
                raise
        elif existing != migration_spec.expected_head:
            raise RuntimeError("prior Vault migration operation has an invalid result")

    run_guarded_upgrade(
        database_path,
        migration_spec,
        operation_id=normalized_operation,
        allow_create=False,
        identity=identity,
    )
    upgraded = open_existing_vault(
        vault_base=vault_base,
        registry=registry,
        migration_spec=migration_spec,
    )
    upgraded_actor = _migration_actor(
        upgraded.connection,
        vault_id=vault_id,
        actor_id=actor_id,
        operation_id=normalized_operation,
    )
    if migration_spec.expected_head == "V0003":
        install_under_test_parser_candidate(
            upgraded.connection,
            actor_id=actor_id,
            project_root=migration_spec.migrations_root.parent,
        )
    _complete_migration_audit(
        upgraded,
        actor=upgraded_actor,
        operation_id=normalized_operation,
        request_sha256=request_sha256,
        target_head=migration_spec.expected_head,
    )
    return upgraded


def registry_snapshot(connection: sqlite3.Connection) -> list[dict[str, str]]:
    return [
        {
            "vault_id": row.vault_id,
            "display_name": row.display_name,
            "relative_root": row.relative_root,
            "registry_state": row.registry_state,
        }
        for row in list_vaults(connection)
    ]


def selected_vault_health(
    central_connection: sqlite3.Connection,
    *,
    vault_base: Path,
    vault_id: str,
    migration_spec: MigrationSpec,
) -> dict[str, object]:
    try:
        with open_registered_vault(
            central_connection,
            vault_base=vault_base,
            vault_id=vault_id,
            migration_spec=migration_spec,
        ) as opened:
            unresolved = opened.connection.execute(
                """SELECT count(*) FROM reconciliation_work
                WHERE state IN ('required','under_review','blocked')"""
            ).fetchone()[0]
            if int(unresolved):
                return {
                    "vault_id": vault_id,
                    "status": "blocked",
                    "reason_code": "vault_reconciliation_required",
                    "reason": "Vault reconciliation is required.",
                }
            if any(path.is_file() for path in (opened.root / "temp").rglob("*")):
                return {
                    "vault_id": vault_id,
                    "status": "blocked",
                    "reason_code": "vault_temporary_state_unresolved",
                    "reason": "Vault temporary intake state is unresolved.",
                }
            artifact_count = verify_artifact_inventory(
                opened.connection,
                vault_root=opened.root,
                vault_account_id=vault_id,
            )
            return {
                "vault_id": vault_id,
                "status": "healthy",
                "sqlite_integrity": "ok",
                "migration": migration_spec.expected_head,
                "identity_fingerprint": opened.identity.identity_fingerprint,
                "audit_chain": "valid",
                "artifact_count": artifact_count,
            }
    except FileNotFoundError:
        reason_code = "vault_resource_unavailable"
        reason = "Vault resources are unavailable."
    except PermissionError:
        reason_code = "vault_access_refused"
        reason = "Vault access is not permitted."
    except sqlite3.DatabaseError:
        reason_code = "vault_database_verification_failed"
        reason = "Vault database verification failed."
    except ArtifactIntegrityError:
        reason_code = "vault_artifact_integrity_failed"
        reason = "Vault artifact integrity verification failed."
    except (RuntimeError, ValueError):
        reason_code = "vault_verification_failed"
        reason = "Vault verification failed."
    except Exception:
        reason_code = "vault_health_blocked"
        reason = "Vault health verification could not complete."
    return {
        "vault_id": vault_id,
        "status": "blocked",
        "reason_code": reason_code,
        "reason": reason,
    }
