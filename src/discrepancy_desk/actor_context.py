from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_id: str
    actor_class: str
    vault_account_id: str
    correlation_id: str
    authentication_source: str
    allowed_operation_class: str

    def require_human(self) -> None:
        if self.actor_class != "human":
            raise PermissionError("operation requires an active human actor")


def resolve_actor_context(
    connection: sqlite3.Connection,
    *,
    vault_account_id: str,
    actor_id: str,
    correlation_id: str,
    authentication_source: str,
    allowed_operation_class: str,
    require_actor_class: str | None = None,
) -> ActorContext:
    row = connection.execute(
        """SELECT actor_class, status, authority_profile
        FROM actors WHERE vault_account_id=? AND id=?""",
        (vault_account_id, actor_id),
    ).fetchone()
    if row is None:
        raise PermissionError("unknown actor")
    actor_class, status, authority_profile = str(row[0]), str(row[1]), str(row[2])
    if status != "active":
        raise PermissionError("actor is not active")
    if require_actor_class is not None and actor_class != require_actor_class:
        raise PermissionError(f"operation requires actor class {require_actor_class}")
    allowed = {value.strip() for value in authority_profile.split(",") if value.strip()}
    if allowed_operation_class not in allowed and "*" not in allowed:
        raise PermissionError("actor authority profile does not permit this operation class")
    return ActorContext(
        actor_id=actor_id,
        actor_class=actor_class,
        vault_account_id=vault_account_id,
        correlation_id=correlation_id,
        authentication_source=authentication_source,
        allowed_operation_class=allowed_operation_class,
    )
