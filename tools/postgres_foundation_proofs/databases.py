"""Proof-database lifecycle and the cleanup registry.

Reconciliation section 5 governs this module:

* the supplied VedaOps connection is the maintenance/admin connection;
* ``CREATE DATABASE`` / ``DROP DATABASE`` run on an autocommit connection;
* fail closed if the role cannot create and drop proof databases -- no
  one-database fallback;
* create each proof database immediately before its proof and drop it
  immediately after, rather than creating all three up front;
* create from ``TEMPLATE template0``;
* close runner-owned connections before ``DROP DATABASE ... WITH (FORCE)``;
  FORCE is a cleanup backstop, not a substitute;
* register a created database for cleanup immediately after creation;
* proof-local cleanup plus a process-level backstop sweep;
* any cleanup failure forces the overall result to FAIL/non-zero.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
from psycopg import sql as pgsql

from . import sql as proof_sql
from .dsn import SafeDsn
from .errors import ErrorCategory, ProofRunError

#: Applied to every connection so a stuck TCP connect cannot hang the run.
CONNECT_TIMEOUT_SECONDS = 10


def connect(
    dsn: SafeDsn,
    *,
    dbname: str | None = None,
    autocommit: bool = False,
    application_name: str,
) -> psycopg.Connection:
    """Open a connection derived from the supplied DSN.

    ``dbname`` retargets the connection to a proof database on the *same*
    server. The merged conninfo contains the password, so it is built and
    consumed inside this function and never returned, logged, or stored.
    """
    overrides: dict[str, Any] = {
        "application_name": application_name,
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
    }
    if dbname is not None:
        overrides["dbname"] = dbname
    conninfo = psycopg.conninfo.make_conninfo(dsn.raw_for_connect(), **overrides)
    target = dsn.redacted() if dbname is None else f"{dsn.host}:{dsn.port}/{dbname}"
    try:
        return psycopg.connect(conninfo, autocommit=autocommit)
    except psycopg.Error as exc:
        # The driver message can echo connection parameters, so only the
        # sqlstate is carried through and the target is the redacted form.
        raise ProofRunError(
            ErrorCategory.CONNECT_FAILED,
            f"could not connect to {target} (sqlstate={getattr(exc, 'sqlstate', None)})",
        ) from None


def assert_role_can_manage_databases(conn: psycopg.Connection, *, context: str) -> dict[str, Any]:
    """Fail closed unless the supplied role can create databases."""
    with conn.cursor() as cur:
        cur.execute(proof_sql.SELECT_ROLE_CAPABILITY)
        row = cur.fetchone()
    if row is None:
        raise ProofRunError(
            ErrorCategory.ROLE_CAPABILITY_MISSING,
            f"could not determine role capabilities at {context}",
        )
    rolcreatedb, rolsuper = bool(row[0]), bool(row[1])
    if not (rolcreatedb or rolsuper):
        raise ProofRunError(
            ErrorCategory.ROLE_CAPABILITY_MISSING,
            "the supplied role can neither CREATEDB nor act as superuser; FND-PG01 "
            "requires isolated proof databases and permits no one-database fallback",
        )
    return {"rolcreatedb": rolcreatedb, "rolsuper": rolsuper}


def create_proof_database(conn: psycopg.Connection, name: str) -> None:
    """Create one proof database from the pristine template.

    ``conn`` must be autocommit: PostgreSQL forbids CREATE DATABASE inside a
    transaction block.
    """
    statement = pgsql.SQL("CREATE DATABASE {} TEMPLATE template0").format(pgsql.Identifier(name))
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
    except psycopg.Error as exc:
        raise ProofRunError(
            ErrorCategory.DATABASE_CREATE_FAILED,
            f"could not create proof database {name!r} (sqlstate={getattr(exc, 'sqlstate', None)})",
        ) from None


def drop_proof_database(conn: psycopg.Connection, name: str) -> None:
    """Force-drop one proof database. ``conn`` must be autocommit."""
    statement = pgsql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(pgsql.Identifier(name))
    with conn.cursor() as cur:
        cur.execute(statement)


def assert_database_empty(conn: psycopg.Connection, name: str) -> list[Any]:
    """Fail closed unless the fresh proof database holds no application objects."""
    with conn.cursor() as cur:
        cur.execute(proof_sql.SELECT_NON_SYSTEM_RELATIONS)
        rows = cur.fetchall()
    if rows:
        raise ProofRunError(
            ErrorCategory.DATABASE_NOT_EMPTY,
            f"proof database {name!r} already contains {len(rows)} non-system relation(s); "
            "a proof must begin from an empty database",
        )
    return rows


class ProofDatabaseRegistry:
    """Tracks created proof databases so none can be orphaned silently.

    The drop function is injected so registry behaviour under injected failures
    is deterministically testable without a database.
    """

    def __init__(self, drop_fn: Callable[[str], None]) -> None:
        self._drop_fn = drop_fn
        self._outstanding: list[str] = []
        self.results: list[dict[str, Any]] = []

    @property
    def outstanding(self) -> tuple[str, ...]:
        return tuple(self._outstanding)

    def register(self, name: str) -> None:
        """Record a created database. Called immediately after creation."""
        if name not in self._outstanding:
            self._outstanding.append(name)

    def drop(self, name: str) -> dict[str, Any]:
        """Drop one database, recording the outcome either way."""
        try:
            self._drop_fn(name)
        except Exception as exc:  # noqa: BLE001 - every failure must be recorded, not raised
            result = {
                "database": name,
                "dropped": False,
                "error_category": str(ErrorCategory.CLEANUP_FAILED),
                "message": _cleanup_message(name, exc),
            }
        else:
            result = {"database": name, "dropped": True}
            if name in self._outstanding:
                self._outstanding.remove(name)
        self.results.append(result)
        return result

    def sweep(self) -> list[dict[str, Any]]:
        """Process-level backstop: drop anything still registered."""
        return [self.drop(name) for name in list(self._outstanding)]

    @property
    def all_dropped(self) -> bool:
        return not self._outstanding and all(r.get("dropped") for r in self.results)

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [r for r in self.results if not r.get("dropped")]


def _cleanup_message(name: str, exc: Exception) -> str:
    """Runner-authored cleanup failure text; never an unfiltered driver repr."""
    if isinstance(exc, ProofRunError):
        return f"could not drop proof database {name!r}: {exc.message}"
    sqlstate = getattr(exc, "sqlstate", None)
    return f"could not drop proof database {name!r} (sqlstate={sqlstate})"
