from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from .db import begin_write, connect_existing
from .migration_spec import MigrationSpec
from .parser_service import install_under_test_parser_candidate
from .srt_service import install_under_test_srt_candidate
from .vtt_service import install_under_test_vtt_candidate
from .persistence import append_audit, existing_operation, record_operation
from .vault_identity import create_vault, resolve_vault_root
from .vault_persistence import request_hash
from .vault_registry import (
    append_central_vault_receipt,
    bind_owned_account,
    create_vault_account,
    get_vault,
    record_registry_audit,
    register_vault,
)


def _record_reconciliation_required(
    connection: sqlite3.Connection,
    *,
    correlation_id: str,
    vault_id: str,
    request_sha256: str,
    actor_id: str,
    reason: str,
) -> None:
    begin_write(connection)
    try:
        append_central_vault_receipt(
            connection,
            correlation_id=correlation_id,
            operation_type="provision_vault",
            vault_id=vault_id,
            stage="reconciliation_required",
            request_sha256=request_sha256,
            detail={"reason": reason},
        )
        append_audit(
            connection,
            actor_type="system",
            actor_id="vault-reconciliation",
            operation="vault_reconciliation_required",
            record_type="vault_account",
            record_id=vault_id,
            payload={"correlation_id": correlation_id, "reason": reason, "requested_by": actor_id},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def provision_vault(
    connection: sqlite3.Connection,
    *,
    vault_base: Path,
    migration_spec: MigrationSpec,
    display_name: str,
    relative_root: str,
    owner_actor_id: str,
    operation_key: str,
    owned_account_ids: tuple[str, ...] = (),
) -> str:
    normalized_root, _ = resolve_vault_root(
        vault_base, relative_root, must_exist=False
    )
    request = {
        "display_name": display_name,
        "relative_root": normalized_root,
        "owner_actor_id": owner_actor_id,
        "owned_account_ids": sorted(owned_account_ids),
    }
    request_sha256 = request_hash(request)
    existing = existing_operation(connection, "provision_vault", operation_key, request_sha256)
    if existing is not None:
        try:
            get_vault(connection, existing)
        except ValueError as exc:
            raise RuntimeError("prior provisioning operation requires reconciliation") from exc
        return existing
    for account_id in owned_account_ids:
        row = connection.execute(
            "SELECT owned FROM owned_accounts WHERE id=?", (account_id,)
        ).fetchone()
        if row is None or int(row[0]) != 1:
            raise ValueError("owned account binding requires a current owned account")
    vault_id = f"vault-{uuid4()}"
    correlation_id = f"vault-create-{uuid4()}"
    begin_write(connection)
    try:
        create_vault_account(
            connection, vault_id=vault_id, display_name=display_name, actor_id=owner_actor_id
        )
        append_central_vault_receipt(
            connection,
            correlation_id=correlation_id,
            operation_type="provision_vault",
            vault_id=vault_id,
            stage="started",
            request_sha256=request_sha256,
            detail={"relative_root": normalized_root, "owned_account_ids": sorted(owned_account_ids)},
        )
        record_operation(
            connection,
            operation_type="provision_vault",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=vault_id,
        )
        record_registry_audit(
            connection,
            actor_id=owner_actor_id,
            operation="vault_provision_started",
            vault_id=vault_id,
            payload={"correlation_id": correlation_id, "relative_root": normalized_root},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    try:
        identity = create_vault(
            vault_base=vault_base,
            relative_root=normalized_root,
            vault_account_id=vault_id,
            owner_actor_id=owner_actor_id,
            migration_spec=migration_spec,
            operation_id=correlation_id,
            correlation_id=correlation_id,
            request_sha256=request_sha256,
        )
        if migration_spec.expected_head in {"V0003", "V0004"}:
            _, created_root = resolve_vault_root(
                vault_base, normalized_root, must_exist=True
            )
            vault_connection = connect_existing(
                created_root / "database" / "vault.sqlite3"
            )
            try:
                install_under_test_parser_candidate(
                    vault_connection,
                    actor_id=owner_actor_id,
                    project_root=migration_spec.migrations_root.parent,
                )
                if migration_spec.expected_head == "V0004":
                    install_under_test_srt_candidate(
                        vault_connection,
                        actor_id=owner_actor_id,
                        project_root=migration_spec.migrations_root.parent,
                    )
                    install_under_test_vtt_candidate(
                        vault_connection,
                        actor_id=owner_actor_id,
                        project_root=migration_spec.migrations_root.parent,
                    )
            finally:
                vault_connection.close()
    except Exception as exc:
        _record_reconciliation_required(
            connection,
            correlation_id=correlation_id,
            vault_id=vault_id,
            request_sha256=request_sha256,
            actor_id=owner_actor_id,
            reason=f"physical Vault creation failed: {type(exc).__name__}",
        )
        raise
    try:
        begin_write(connection)
        register_vault(
            connection,
            vault_id=vault_id,
            relative_root=normalized_root,
            vault_instance_id=identity.vault_instance_id,
            identity_fingerprint=identity.identity_fingerprint,
            actor_id=owner_actor_id,
        )
        for account_id in owned_account_ids:
            bind_owned_account(
                connection,
                vault_id=vault_id,
                owned_account_id=account_id,
                actor_id=owner_actor_id,
            )
        append_central_vault_receipt(
            connection,
            correlation_id=correlation_id,
            operation_type="provision_vault",
            vault_id=vault_id,
            stage="vault_committed",
            request_sha256=request_sha256,
            result_sha256=identity.identity_fingerprint,
            detail={"vault_instance_id": identity.vault_instance_id},
        )
        append_central_vault_receipt(
            connection,
            correlation_id=correlation_id,
            operation_type="provision_vault",
            vault_id=vault_id,
            stage="completed",
            request_sha256=request_sha256,
            result_sha256=identity.identity_fingerprint,
            detail={"bindings": sorted(owned_account_ids)},
        )
        record_registry_audit(
            connection,
            actor_id=owner_actor_id,
            operation="vault_provision_completed",
            vault_id=vault_id,
            payload={"correlation_id": correlation_id, "identity": identity.marker()},
        )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        _record_reconciliation_required(
            connection,
            correlation_id=correlation_id,
            vault_id=vault_id,
            request_sha256=request_sha256,
            actor_id=owner_actor_id,
            reason=f"central registry completion failed: {type(exc).__name__}",
        )
        raise
    return vault_id


def verify_provisioning_receipts(
    central_connection: sqlite3.Connection,
    vault_connection: sqlite3.Connection,
    *,
    correlation_id: str,
) -> bool:
    central_rows = central_connection.execute(
        """SELECT stage, request_sha256, result_sha256
        FROM vault_operation_receipts WHERE correlation_id=? ORDER BY occurred_at, id""",
        (correlation_id,),
    ).fetchall()
    vault_rows = vault_connection.execute(
        """SELECT stage, request_sha256, result_sha256
        FROM cross_database_operation_receipts WHERE correlation_id=? ORDER BY occurred_at, id""",
        (correlation_id,),
    ).fetchall()
    central = {str(row[0]): (str(row[1]), str(row[2]) if row[2] is not None else None) for row in central_rows}
    vault = {str(row[0]): (str(row[1]), str(row[2]) if row[2] is not None else None) for row in vault_rows}
    required_central = {"started", "vault_committed", "completed"}
    required_vault = {"central_started", "vault_committed"}
    if not required_central.issubset(central) or not required_vault.issubset(vault):
        raise ValueError("provisioning receipts are incomplete")
    request_hashes = {
        central["started"][0],
        central["vault_committed"][0],
        central["completed"][0],
        vault["central_started"][0],
        vault["vault_committed"][0],
    }
    if len(request_hashes) != 1:
        raise ValueError("provisioning request receipt hashes do not reconcile")
    result_hashes = {
        central["vault_committed"][1],
        central["completed"][1],
        vault["vault_committed"][1],
    }
    if None in result_hashes or len(result_hashes) != 1:
        raise ValueError("provisioning result receipt hashes do not reconcile")
    if "reconciliation_required" in central:
        raise ValueError("provisioning remains reconciliation-required")
    return True
