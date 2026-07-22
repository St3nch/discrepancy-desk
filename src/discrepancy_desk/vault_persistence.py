from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from .actor_context import ActorContext


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_hash(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def append_vault_audit(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    authority_operation: str,
    request_sha256: str,
    record_type: str,
    record_id: str,
    payload: object,
) -> str:
    if actor.allowed_operation_class not in {authority_operation, "vault_admin", "system_operation", "read"}:
        raise PermissionError("actor context is not bound to the requested authority operation")
    previous = connection.execute(
        "SELECT chain_sha256 FROM audit_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    previous_hash = str(previous[0]) if previous else None
    event_id = str(uuid4())
    occurred_at = utc_now()
    payload_bytes = canonical_json(payload)
    material = canonical_json(
        {
            "id": event_id,
            "vault_account_id": actor.vault_account_id,
            "occurred_at": occurred_at,
            "actor_class": actor.actor_class,
            "actor_id": actor.actor_id,
            "authority_operation": authority_operation,
            "correlation_id": actor.correlation_id,
            "request_sha256": request_sha256,
            "record_type": record_type,
            "record_id": record_id,
            "payload_sha256": sha256_bytes(payload_bytes),
            "previous_chain_sha256": previous_hash,
        }
    )
    event_hash = sha256_bytes(material)
    chain_hash = sha256_bytes(((previous_hash or "") + event_hash).encode("ascii"))
    connection.execute(
        """INSERT INTO audit_events
        (id, vault_account_id, occurred_at, actor_class, actor_id, authority_operation,
         correlation_id, request_sha256, record_type, record_id, payload_json,
         previous_chain_sha256, event_sha256, chain_sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            actor.vault_account_id,
            occurred_at,
            actor.actor_class,
            actor.actor_id,
            authority_operation,
            actor.correlation_id,
            request_sha256,
            record_type,
            record_id,
            payload_bytes,
            previous_hash,
            event_hash,
            chain_hash,
        ),
    )
    return event_id


def verify_vault_audit_chain(connection: sqlite3.Connection) -> bool:
    previous: str | None = None
    rows = connection.execute("SELECT * FROM audit_events ORDER BY sequence")
    for row in rows:
        payload_hash = sha256_bytes(bytes(row[11]))
        material = canonical_json(
            {
                "id": row[1],
                "vault_account_id": row[2],
                "occurred_at": row[3],
                "actor_class": row[4],
                "actor_id": row[5],
                "authority_operation": row[6],
                "correlation_id": row[7],
                "request_sha256": row[8],
                "record_type": row[9],
                "record_id": row[10],
                "payload_sha256": payload_hash,
                "previous_chain_sha256": previous,
            }
        )
        event_hash = sha256_bytes(material)
        chain_hash = sha256_bytes(((previous or "") + event_hash).encode("ascii"))
        if row[12] != previous or row[13] != event_hash or row[14] != chain_hash:
            return False
        previous = chain_hash
    return True


def existing_vault_operation(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    operation_type: str,
    operation_key: str,
    request_sha256: str,
) -> str | None:
    row = connection.execute(
        """SELECT vault_account_id, actor_id, actor_class, correlation_id,
                  request_sha256, result_ref
        FROM operation_keys WHERE operation_type=? AND operation_key=?""",
        (operation_type, operation_key),
    ).fetchone()
    if row is None:
        return None
    if (
        str(row[0]) != actor.vault_account_id
        or str(row[1]) != actor.actor_id
        or str(row[2]) != actor.actor_class
        or str(row[3]) != actor.correlation_id
        or str(row[4]) != request_sha256
    ):
        raise ValueError("idempotency key reused with conflicting actor, Vault, or request")
    return str(row[5])


def record_vault_operation(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    operation_type: str,
    operation_key: str,
    request_sha256: str,
    result_ref: str,
) -> None:
    connection.execute(
        """INSERT INTO operation_keys
        (operation_type, operation_key, vault_account_id, actor_id, actor_class,
         correlation_id, request_sha256, result_ref, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            operation_type,
            operation_key,
            actor.vault_account_id,
            actor.actor_id,
            actor.actor_class,
            actor.correlation_id,
            request_sha256,
            result_ref,
            utc_now(),
        ),
    )


def append_cross_database_receipt(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    correlation_id: str,
    operation_type: str,
    stage: str,
    request_sha256: str,
    result_sha256: str | None,
    detail: object,
) -> str:
    receipt_id = str(uuid4())
    connection.execute(
        """INSERT INTO cross_database_operation_receipts
        (id, vault_account_id, correlation_id, external_database, operation_type,
         stage, request_sha256, result_sha256, occurred_at, detail_json)
        VALUES (?, ?, ?, 'central-control-room', ?, ?, ?, ?, ?, ?)""",
        (
            receipt_id,
            vault_account_id,
            correlation_id,
            operation_type,
            stage,
            request_sha256,
            result_sha256,
            utc_now(),
            canonical_json(detail),
        ),
    )
    return receipt_id
