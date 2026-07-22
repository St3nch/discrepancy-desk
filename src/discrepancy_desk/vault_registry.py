from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from .persistence import append_audit, utc_now


@dataclass(frozen=True, slots=True)
class VaultRegistryRecord:
    vault_id: str
    display_name: str
    relative_root: str
    vault_instance_id: str
    expected_identity_fingerprint: str
    registry_state: str


def append_central_vault_receipt(
    connection: sqlite3.Connection,
    *,
    correlation_id: str,
    operation_type: str,
    vault_id: str | None,
    stage: str,
    request_sha256: str,
    result_sha256: str | None = None,
    detail: object | None = None,
) -> str:
    receipt_id = str(uuid4())
    connection.execute(
        """INSERT INTO vault_operation_receipts
        (id, correlation_id, operation_type, vault_id, stage, request_sha256,
         result_sha256, occurred_at, detail_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            receipt_id,
            correlation_id,
            operation_type,
            vault_id,
            stage,
            request_sha256,
            result_sha256,
            utc_now(),
            json.dumps(detail or {}, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        ),
    )
    return receipt_id


def create_vault_account(
    connection: sqlite3.Connection,
    *,
    vault_id: str,
    display_name: str,
    actor_id: str,
) -> None:
    connection.execute(
        "INSERT INTO vault_accounts VALUES (?, ?, 'active', ?, ?)",
        (vault_id, display_name, utc_now(), actor_id),
    )


def register_vault(
    connection: sqlite3.Connection,
    *,
    vault_id: str,
    relative_root: str,
    vault_instance_id: str,
    identity_fingerprint: str,
    actor_id: str,
) -> None:
    connection.execute(
        """INSERT INTO vault_registry
        (vault_id, relative_root, vault_instance_id, expected_identity_fingerprint,
         registry_state, registered_at, registered_by_actor_id)
        VALUES (?, ?, ?, ?, 'registered', ?, ?)""",
        (vault_id, relative_root, vault_instance_id, identity_fingerprint, utc_now(), actor_id),
    )


def bind_owned_account(
    connection: sqlite3.Connection,
    *,
    vault_id: str,
    owned_account_id: str,
    actor_id: str,
) -> None:
    connection.execute(
        """INSERT INTO vault_account_owned_accounts
        (vault_id, owned_account_id, binding_state, bound_at, bound_by_actor_id)
        VALUES (?, ?, 'active', ?, ?)""",
        (vault_id, owned_account_id, utc_now(), actor_id),
    )


def list_vaults(connection: sqlite3.Connection) -> list[VaultRegistryRecord]:
    return [
        VaultRegistryRecord(
            vault_id=str(row[0]),
            display_name=str(row[1]),
            relative_root=str(row[2]),
            vault_instance_id=str(row[3]),
            expected_identity_fingerprint=str(row[4]),
            registry_state=str(row[5]),
        )
        for row in connection.execute(
            """SELECT a.id, a.display_name, r.relative_root, r.vault_instance_id,
                      r.expected_identity_fingerprint, r.registry_state
            FROM vault_accounts a JOIN vault_registry r ON r.vault_id=a.id
            ORDER BY a.display_name, a.id"""
        )
    ]


def get_vault(connection: sqlite3.Connection, vault_id: str) -> VaultRegistryRecord:
    row = connection.execute(
        """SELECT a.id, a.display_name, r.relative_root, r.vault_instance_id,
                  r.expected_identity_fingerprint, r.registry_state
        FROM vault_accounts a JOIN vault_registry r ON r.vault_id=a.id
        WHERE a.id=?""",
        (vault_id,),
    ).fetchone()
    if row is None:
        raise ValueError("unknown Vault")
    return VaultRegistryRecord(
        vault_id=str(row[0]), display_name=str(row[1]), relative_root=str(row[2]),
        vault_instance_id=str(row[3]), expected_identity_fingerprint=str(row[4]),
        registry_state=str(row[5]),
    )


def require_active_binding(
    connection: sqlite3.Connection, *, vault_id: str, owned_account_id: str
) -> None:
    row = connection.execute(
        """SELECT 1 FROM vault_account_owned_accounts
        WHERE vault_id=? AND owned_account_id=? AND binding_state='active'""",
        (vault_id, owned_account_id),
    ).fetchone()
    if row is None:
        raise ValueError("platform account is not actively bound to the selected Vault")


def record_registry_audit(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    operation: str,
    vault_id: str,
    payload: object,
) -> None:
    append_audit(
        connection,
        actor_type="human",
        actor_id=actor_id,
        operation=operation,
        record_type="vault_account",
        record_id=vault_id,
        payload=payload,
    )
