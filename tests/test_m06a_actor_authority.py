from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from discrepancy_desk.actor_context import ActorContext, resolve_actor_context
from discrepancy_desk.vault_persistence import (
    existing_vault_operation,
    record_vault_operation,
    request_hash,
    verify_vault_audit_chain,
)
from discrepancy_desk.vault_router import open_registered_vault
from discrepancy_desk.vault_service import provision_vault, verify_provisioning_receipts


def _provision(connection, vault_base: Path, vault_spec, *, root: str, key: str) -> str:
    return provision_vault(
        connection,
        vault_base=vault_base,
        migration_spec=vault_spec,
        display_name=root,
        relative_root=root,
        owner_actor_id="owner-local",
        operation_key=key,
    )


def _insert_actor(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    vault_id: str,
    actor_class: str,
    status: str = "active",
    authority_profile: str = "read",
) -> None:
    connection.execute(
        """INSERT INTO actors
        (id, vault_account_id, actor_class, display_name, status,
         authority_profile, created_at, created_by_actor_id)
        VALUES (?, ?, ?, ?, ?, ?, '2026-07-21T00:00:00+00:00', 'owner-local')""",
        (actor_id, vault_id, actor_class, actor_id, status, authority_profile),
    )
    connection.commit()


def test_m06a_ht_009_request_actor_impersonation_rejected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_id = _provision(central, tmp_path / "vaults", m06a_vault_spec, root="actors", key="actors:9")
    with open_registered_vault(
        central,
        vault_base=tmp_path / "vaults",
        vault_id=vault_id,
        migration_spec=m06a_vault_spec,
    ) as opened:
        with pytest.raises(PermissionError, match="unknown actor"):
            resolve_actor_context(
                opened.connection,
                vault_account_id=vault_id,
                actor_id="owner",
                correlation_id="request-body-selected-owner",
                authentication_source="untrusted-request-body",
                allowed_operation_class="human_decision",
                require_actor_class="human",
            )


def test_m06a_ht_010_system_human_authority_rejected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_id = _provision(central, tmp_path / "vaults", m06a_vault_spec, root="system", key="actors:10")
    with open_registered_vault(
        central, vault_base=tmp_path / "vaults", vault_id=vault_id, migration_spec=m06a_vault_spec
    ) as opened:
        _insert_actor(
            opened.connection,
            actor_id="system-worker",
            vault_id=vault_id,
            actor_class="system",
            authority_profile="system_operation",
        )
        with pytest.raises(PermissionError, match="requires actor class human"):
            resolve_actor_context(
                opened.connection,
                vault_account_id=vault_id,
                actor_id="system-worker",
                correlation_id="system-human-attempt",
                authentication_source="service",
                allowed_operation_class="human_decision",
                require_actor_class="human",
            )


def test_m06a_ht_011_model_authority_rejected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_id = _provision(central, tmp_path / "vaults", m06a_vault_spec, root="model", key="actors:11")
    with open_registered_vault(
        central, vault_base=tmp_path / "vaults", vault_id=vault_id, migration_spec=m06a_vault_spec
    ) as opened:
        _insert_actor(
            opened.connection,
            actor_id="model-candidate",
            vault_id=vault_id,
            actor_class="model",
            authority_profile="read",
        )
        with pytest.raises(PermissionError):
            resolve_actor_context(
                opened.connection,
                vault_account_id=vault_id,
                actor_id="model-candidate",
                correlation_id="model-promotion-attempt",
                authentication_source="model-output",
                allowed_operation_class="human_decision",
                require_actor_class="human",
            )


def test_m06a_ht_012_actor_status_and_scope_enforced(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first = _provision(central, vault_base, m06a_vault_spec, root="scope-a", key="actors:12a")
    second = _provision(central, vault_base, m06a_vault_spec, root="scope-b", key="actors:12b")
    with open_registered_vault(
        central, vault_base=vault_base, vault_id=first, migration_spec=m06a_vault_spec
    ) as opened:
        _insert_actor(
            opened.connection,
            actor_id="disabled-human",
            vault_id=first,
            actor_class="human",
            status="disabled",
            authority_profile="human_decision",
        )
        with pytest.raises(PermissionError, match="not active"):
            resolve_actor_context(
                opened.connection,
                vault_account_id=first,
                actor_id="disabled-human",
                correlation_id="disabled",
                authentication_source="desktop-session",
                allowed_operation_class="human_decision",
                require_actor_class="human",
            )
        with pytest.raises(PermissionError, match="unknown actor"):
            resolve_actor_context(
                opened.connection,
                vault_account_id=second,
                actor_id="owner-local",
                correlation_id="wrong-vault",
                authentication_source="desktop-session",
                allowed_operation_class="human_decision",
                require_actor_class="human",
            )


def test_m06a_ht_013_token_is_not_human_identity(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_id = _provision(central, tmp_path / "vaults", m06a_vault_spec, root="token", key="actors:13")
    launch_token = "t" * 64
    with open_registered_vault(
        central,
        vault_base=tmp_path / "vaults",
        vault_id=vault_id,
        migration_spec=m06a_vault_spec,
    ) as opened:
        with pytest.raises(PermissionError, match="unknown actor"):
            resolve_actor_context(
                opened.connection,
                vault_account_id=vault_id,
                actor_id=launch_token,
                correlation_id="desktop-token-only",
                authentication_source="desktop-launch-token",
                allowed_operation_class="human_decision",
                require_actor_class="human",
            )


def test_m06a_ht_014_audit_tamper_detected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_id = _provision(central, tmp_path / "vaults", m06a_vault_spec, root="audit", key="actors:14")
    with open_registered_vault(
        central,
        vault_base=tmp_path / "vaults",
        vault_id=vault_id,
        migration_spec=m06a_vault_spec,
    ) as opened:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            opened.connection.execute("UPDATE audit_events SET record_id='changed'")
        opened.connection.execute("DROP TRIGGER audit_events_no_update")
        opened.connection.execute("UPDATE audit_events SET payload_json=x'7B7D' WHERE sequence=1")
        opened.connection.commit()
        assert verify_vault_audit_chain(opened.connection) is False


def test_m06a_ht_015_idempotency_scope_and_conflict(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_id = _provision(central, tmp_path / "vaults", m06a_vault_spec, root="idempotent", key="actors:15")
    with open_registered_vault(
        central,
        vault_base=tmp_path / "vaults",
        vault_id=vault_id,
        migration_spec=m06a_vault_spec,
    ) as opened:
        actor = resolve_actor_context(
            opened.connection,
            vault_account_id=vault_id,
            actor_id="owner-local",
            correlation_id="correlation-15",
            authentication_source="server-resolved-session",
            allowed_operation_class="vault_admin",
            require_actor_class="human",
        )
        digest = request_hash({"fixture": 15})
        record_vault_operation(
            opened.connection,
            actor=actor,
            operation_type="fixture",
            operation_key="same-key",
            request_sha256=digest,
            result_ref="result-15",
        )
        opened.connection.commit()
        assert existing_vault_operation(
            opened.connection,
            actor=actor,
            operation_type="fixture",
            operation_key="same-key",
            request_sha256=digest,
        ) == "result-15"
        conflicting_actor = ActorContext(
            actor_id=actor.actor_id,
            actor_class=actor.actor_class,
            vault_account_id=actor.vault_account_id,
            correlation_id="different-correlation",
            authentication_source=actor.authentication_source,
            allowed_operation_class=actor.allowed_operation_class,
        )
        with pytest.raises(ValueError, match="conflicting actor, Vault, or request"):
            existing_vault_operation(
                opened.connection,
                actor=conflicting_actor,
                operation_type="fixture",
                operation_key="same-key",
                request_sha256=digest,
            )


def test_m06a_ht_016_cross_database_partial_failure_reconciles(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    (vault_base / "already-exists").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        _provision(
            central,
            vault_base,
            m06a_vault_spec,
            root="already-exists",
            key="partial:16",
        )
    stages = [
        str(row[0])
        for row in central.execute(
            "SELECT stage FROM vault_operation_receipts ORDER BY occurred_at, id"
        )
    ]
    assert stages == ["started", "reconciliation_required"]
    assert central.execute("SELECT count(*) FROM vault_registry").fetchone()[0] == 0


def test_m06a_ht_017_cross_database_receipt_fabrication_rejected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    vault_id = _provision(central, vault_base, m06a_vault_spec, root="receipts", key="receipts:17")
    correlation_id = str(
        central.execute(
            "SELECT correlation_id FROM vault_operation_receipts WHERE vault_id=? AND stage='completed'",
            (vault_id,),
        ).fetchone()[0]
    )
    with open_registered_vault(
        central, vault_base=vault_base, vault_id=vault_id, migration_spec=m06a_vault_spec
    ) as opened:
        assert verify_provisioning_receipts(
            central, opened.connection, correlation_id=correlation_id
        ) is True
        central.execute("DROP TRIGGER vault_operation_receipts_no_update")
        central.execute(
            """UPDATE vault_operation_receipts SET request_sha256=?
            WHERE correlation_id=? AND stage='completed'""",
            ("0" * 64, correlation_id),
        )
        central.commit()
        with pytest.raises(ValueError, match="request receipt hashes"):
            verify_provisioning_receipts(
                central, opened.connection, correlation_id=correlation_id
            )


def test_m06a_ht_097_cross_database_atomicity_is_never_claimed(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    (vault_base / "conflict").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        _provision(central, vault_base, m06a_vault_spec, root="conflict", key="atomicity:97")
    rows = central.execute(
        "SELECT stage FROM vault_operation_receipts ORDER BY occurred_at, id"
    ).fetchall()
    stages = {str(row[0]) for row in rows}
    assert "reconciliation_required" in stages
    assert "completed" not in stages
