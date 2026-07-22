"""Create M06-A Vault identity, actor, audit, and reconciliation foundation.

Revision ID: V0001
Revises: None
"""
from alembic import op

revision = "V0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE vault_metadata (
        singleton_id INTEGER PRIMARY KEY CHECK (singleton_id=1),
        vault_account_id TEXT NOT NULL UNIQUE,
        vault_instance_id TEXT NOT NULL UNIQUE,
        vault_schema_name TEXT NOT NULL CHECK (vault_schema_name='m06a-vault'),
        created_at TEXT NOT NULL,
        identity_fingerprint TEXT NOT NULL UNIQUE CHECK (length(identity_fingerprint)=64)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE actors (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        actor_class TEXT NOT NULL CHECK (actor_class IN ('human','system','model','import')),
        display_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active','disabled','revoked')),
        authority_profile TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by_actor_id TEXT,
        UNIQUE(vault_account_id, id)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE actor_status_history (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        prior_status TEXT CHECK (prior_status IS NULL OR prior_status IN ('active','disabled','revoked')),
        new_status TEXT NOT NULL CHECK (new_status IN ('active','disabled','revoked')),
        changed_at TEXT NOT NULL,
        changed_by_actor_id TEXT NOT NULL,
        reason TEXT NOT NULL,
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE operation_keys (
        operation_type TEXT NOT NULL,
        operation_key TEXT NOT NULL,
        vault_account_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        actor_class TEXT NOT NULL CHECK (actor_class IN ('human','system','model','import')),
        correlation_id TEXT NOT NULL,
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
        result_ref TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(operation_type, operation_key),
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE audit_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        vault_account_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        actor_class TEXT NOT NULL CHECK (actor_class IN ('human','system','model','import')),
        actor_id TEXT NOT NULL,
        authority_operation TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
        record_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        payload_json BLOB NOT NULL,
        previous_chain_sha256 TEXT,
        event_sha256 TEXT NOT NULL CHECK (length(event_sha256)=64),
        chain_sha256 TEXT NOT NULL CHECK (length(chain_sha256)=64),
        FOREIGN KEY(vault_account_id, actor_id)
            REFERENCES actors(vault_account_id, id) ON DELETE RESTRICT
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE cross_database_operation_receipts (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        external_database TEXT NOT NULL CHECK (external_database='central-control-room'),
        operation_type TEXT NOT NULL,
        stage TEXT NOT NULL CHECK (
            stage IN ('central_started','vault_committed','central_completed','reconciliation_required','reconciled')
        ),
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
        result_sha256 TEXT CHECK (result_sha256 IS NULL OR length(result_sha256)=64),
        occurred_at TEXT NOT NULL,
        detail_json BLOB NOT NULL,
        UNIQUE(correlation_id, stage)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE reconciliation_work (
        id TEXT PRIMARY KEY,
        vault_account_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL UNIQUE,
        operation_type TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('required','under_review','reconciled','blocked')),
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        resolution_sha256 TEXT CHECK (resolution_sha256 IS NULL OR length(resolution_sha256)=64)
    ) STRICT;
    """)
    for table in ('vault_metadata','actor_status_history','operation_keys','audit_events','cross_database_operation_receipts'):
        op.execute(f"""
        CREATE TRIGGER {table}_no_update
        BEFORE UPDATE ON {table} BEGIN
            SELECT RAISE(ABORT, '{table} is append-only');
        END;
        """)
        op.execute(f"""
        CREATE TRIGGER {table}_no_delete
        BEFORE DELETE ON {table} BEGIN
            SELECT RAISE(ABORT, '{table} is append-only');
        END;
        """)


def downgrade() -> None:
    connection = op.get_bind()
    for table in ('reconciliation_work','cross_database_operation_receipts','audit_events','operation_keys','actor_status_history','actors','vault_metadata'):
        if connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            raise RuntimeError('refusing to downgrade V0001 with governed Vault rows')
    for table in ('cross_database_operation_receipts','audit_events','operation_keys','actor_status_history','vault_metadata'):
        op.execute(f'DROP TRIGGER IF EXISTS {table}_no_delete')
        op.execute(f'DROP TRIGGER IF EXISTS {table}_no_update')
    for table in ('reconciliation_work','cross_database_operation_receipts','audit_events','operation_keys','actor_status_history','actors','vault_metadata'):
        op.execute(f'DROP TABLE IF EXISTS {table}')
