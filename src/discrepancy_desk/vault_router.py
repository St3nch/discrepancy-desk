from __future__ import annotations

import sqlite3
from pathlib import Path

from .migration_spec import MigrationSpec
from .vault_identity import OpenedVault, open_existing_vault
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
            return {
                "vault_id": vault_id,
                "status": "healthy",
                "sqlite_integrity": "ok",
                "migration": migration_spec.expected_head,
                "identity_fingerprint": opened.identity.identity_fingerprint,
                "audit_chain": "valid",
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
