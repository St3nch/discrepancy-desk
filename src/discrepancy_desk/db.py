"""PostgreSQL migration, capability, and admission seams."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import Connection, sql

from discrepancy_desk.config import (
    require_admin_database_url,
    require_database_url,
    require_human_database_url,
)
from discrepancy_desk.errors import ConfigurationError, MigrationDriftError

MIGRATION_LOCK_KEY = 72250001
ADMISSION_LOCK_KEY = 72250002
CAPABILITY_ROLES = ("desk_owner", "desk_app", "desk_human_authority")
MIGRATIONS = Path(__file__).with_name("migrations")

_APPEND_TABLES = (
    "record_admission",
    "file",
    "artifact",
    "capture",
    "file_capture",
    "surface",
    "locator",
    "excerpt",
    "observation",
    "file_observation",
    "observation_excerpt",
    "claim",
    "claim_version",
    "file_claim",
    "claim_version_observation_basis",
    "discrepancy",
    "discrepancy_version",
    "discrepancy_observation_ref",
    "discrepancy_claim_ref",
)
_DECISION_TABLES = (
    "record_admission",
    "decision",
    "claim_posture_decision_effect",
    "decision_supersession",
)


def connect_url(database_url: str) -> Connection:
    return psycopg.connect(database_url, autocommit=True)


def connect_runtime() -> Connection:
    return connect_url(require_database_url())


def connect_admin() -> Connection:
    return connect_url(require_admin_database_url())


def connect_human() -> Connection:
    return connect_url(require_human_database_url())


def bootstrap_database(conn: Connection, migrations_dir: Path = MIGRATIONS) -> None:
    """Create non-login capability roles, migrate, and grant exact runtime authority."""
    _ensure_capability_roles(conn)
    apply_migrations(conn, migrations_dir)
    _grant_capabilities(conn)


def _ensure_capability_roles(conn: Connection) -> None:
    unsafe_attributes = (
        "rolsuper",
        "rolinherit",
        "rolcreaterole",
        "rolcreatedb",
        "rolcanlogin",
        "rolreplication",
        "rolbypassrls",
    )
    for role in CAPABILITY_ROLES:
        row = conn.execute(
            """
            SELECT rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
                   rolreplication, rolbypassrls
            FROM pg_roles
            WHERE rolname = %s
            """,
            (role,),
        ).fetchone()
        if row is None:
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(role)))
            continue
        values = dict(zip(unsafe_attributes, row, strict=True))
        allowed = {name: False for name in unsafe_attributes}
        if values != allowed:
            raise ConfigurationError(f"Existing capability role {role} has unsafe attributes")
        memberships = conn.execute(
            """
            SELECT parent.rolname
            FROM pg_auth_members membership
            JOIN pg_roles member ON member.oid = membership.member
            JOIN pg_roles parent ON parent.oid = membership.roleid
            WHERE member.rolname = %s
            """,
            (role,),
        ).fetchall()
        if memberships:
            parents = ", ".join(item[0] for item in memberships)
            raise ConfigurationError(
                f"Existing capability role {role} can assume other roles: {parents}"
            )


def apply_migrations(conn: Connection, migrations_dir: Path = MIGRATIONS) -> None:
    files = sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise ConfigurationError("No Desk migrations were found")

    conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
    try:
        _ensure_migration_ledger(conn)
        for migration in files:
            version = int(migration.name.split("_", 1)[0])
            payload = migration.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            with conn.transaction():
                applied = conn.execute(
                    """
                    SELECT filename, sha256
                    FROM desk_meta.schema_migration
                    WHERE version = %s
                    """,
                    (version,),
                ).fetchone()
                if applied is not None:
                    if applied != (migration.name, digest):
                        raise MigrationDriftError(
                            f"Applied migration {version} does not match {migration.name}"
                        )
                    continue
                conn.execute(payload.decode("utf-8"))
                conn.execute(
                    """
                    INSERT INTO desk_meta.schema_migration
                        (version, filename, sha256)
                    VALUES (%s, %s, %s)
                    """,
                    (version, migration.name, digest),
                )
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))


def _ensure_migration_ledger(conn: Connection) -> None:
    existing = conn.execute(
        """
        SELECT r.rolname
        FROM pg_namespace n
        JOIN pg_roles r ON r.oid = n.nspowner
        WHERE n.nspname = 'desk_meta'
        """
    ).fetchone()
    if existing is not None and existing[0] != "desk_owner":
        raise ConfigurationError("Existing desk_meta schema is not owned by desk_owner")
    with conn.transaction():
        if existing is None:
            conn.execute("CREATE SCHEMA desk_meta AUTHORIZATION desk_owner")
        conn.execute("SET LOCAL ROLE desk_owner")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS desk_meta.schema_migration (
                version integer PRIMARY KEY CHECK (version > 0),
                filename text NOT NULL UNIQUE CHECK (btrim(filename) <> ''),
                sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
            """
        )


def _grant_capabilities(conn: Connection) -> None:
    with conn.transaction():
        conn.execute("REVOKE ALL ON SCHEMA desk FROM PUBLIC")
        conn.execute("REVOKE ALL ON SCHEMA desk FROM desk_app, desk_human_authority")
        conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA desk FROM PUBLIC")
        conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA desk FROM desk_app, desk_human_authority")
        conn.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA desk FROM PUBLIC")
        conn.execute(
            "REVOKE ALL ON ALL SEQUENCES IN SCHEMA desk FROM desk_app, desk_human_authority"
        )
        conn.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA desk FROM PUBLIC")
        conn.execute(
            "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA desk FROM desk_app, desk_human_authority"
        )
        owners = conn.execute(
            """
            SELECT c.relname, owner.rolname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_roles owner ON owner.oid = c.relowner
            WHERE n.nspname = 'desk'
              AND owner.rolname IN ('desk_app', 'desk_human_authority')
            """
        ).fetchall()
        if owners:
            raise ConfigurationError("A runtime capability role owns Desk objects")
        conn.execute("GRANT USAGE ON SCHEMA desk TO desk_app, desk_human_authority")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA desk TO desk_app")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA desk TO desk_human_authority")
        conn.execute(
            sql.SQL("GRANT INSERT ON TABLE {} TO desk_app").format(
                sql.SQL(", ").join(
                    sql.Identifier("desk", table_name) for table_name in _APPEND_TABLES
                )
            )
        )
        conn.execute(
            sql.SQL("GRANT INSERT ON TABLE {} TO desk_human_authority").format(
                sql.SQL(", ").join(
                    sql.Identifier("desk", table_name) for table_name in _DECISION_TABLES
                )
            )
        )
        conn.execute(
            "GRANT USAGE, SELECT ON SEQUENCE desk.record_admission_order_seq "
            "TO desk_app, desk_human_authority"
        )


@contextmanager
def admission(
    conn: Connection,
    *,
    label: str,
    actor_kind: str = "operator",
) -> Iterator[int]:
    if not label.strip():
        raise ValueError("Admission label is required")
    if actor_kind not in {"operator", "system"}:
        raise ValueError("Unsupported admission actor kind")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADMISSION_LOCK_KEY,))
        row = conn.execute(
            """
            INSERT INTO desk.record_admission (admission_order, actor_kind, label)
            VALUES (nextval('desk.record_admission_order_seq'), %s, %s)
            RETURNING admission_order
            """,
            (actor_kind, label),
        ).fetchone()
        assert row is not None
        yield row[0]
