"""Add M06-A Vault registry and binding authority.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE vault_accounts (
        id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('active','suspended','retired')),
        created_at TEXT NOT NULL,
        created_by_actor_id TEXT NOT NULL
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE vault_registry (
        vault_id TEXT PRIMARY KEY REFERENCES vault_accounts(id) ON DELETE RESTRICT,
        relative_root TEXT NOT NULL UNIQUE,
        vault_instance_id TEXT NOT NULL UNIQUE,
        expected_identity_fingerprint TEXT NOT NULL UNIQUE
            CHECK (length(expected_identity_fingerprint)=64),
        registry_state TEXT NOT NULL
            CHECK (registry_state IN ('registered','unavailable','dirty','retired')),
        registered_at TEXT NOT NULL,
        registered_by_actor_id TEXT NOT NULL
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE vault_account_owned_accounts (
        vault_id TEXT NOT NULL REFERENCES vault_accounts(id) ON DELETE RESTRICT,
        owned_account_id TEXT NOT NULL REFERENCES owned_accounts(id) ON DELETE RESTRICT,
        binding_state TEXT NOT NULL CHECK (binding_state IN ('active','superseded','removed')),
        bound_at TEXT NOT NULL,
        bound_by_actor_id TEXT NOT NULL,
        PRIMARY KEY(vault_id, owned_account_id, bound_at)
    ) STRICT;
    """)
    op.execute("""
    CREATE UNIQUE INDEX vault_owned_account_one_active_binding
    ON vault_account_owned_accounts(owned_account_id)
    WHERE binding_state='active';
    """)
    op.execute("""
    CREATE UNIQUE INDEX vault_pair_one_active_binding
    ON vault_account_owned_accounts(vault_id, owned_account_id)
    WHERE binding_state='active';
    """)
    op.execute("""
    CREATE TABLE vault_operation_receipts (
        id TEXT PRIMARY KEY,
        correlation_id TEXT NOT NULL,
        operation_type TEXT NOT NULL,
        vault_id TEXT REFERENCES vault_accounts(id) ON DELETE RESTRICT,
        stage TEXT NOT NULL CHECK (
            stage IN ('started','vault_committed','completed','reconciliation_required','reconciled')
        ),
        request_sha256 TEXT NOT NULL CHECK (length(request_sha256)=64),
        result_sha256 TEXT CHECK (result_sha256 IS NULL OR length(result_sha256)=64),
        occurred_at TEXT NOT NULL,
        detail_json BLOB NOT NULL,
        UNIQUE(correlation_id, stage)
    ) STRICT;
    """)
    for table in ('vault_operation_receipts',):
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
    for table in ('vault_operation_receipts','vault_account_owned_accounts','vault_registry','vault_accounts'):
        if connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is not None:
            raise RuntimeError('refusing to downgrade 0005 with governed Vault rows')
    op.execute('DROP TRIGGER IF EXISTS vault_operation_receipts_no_delete')
    op.execute('DROP TRIGGER IF EXISTS vault_operation_receipts_no_update')
    op.execute('DROP TABLE IF EXISTS vault_operation_receipts')
    op.execute('DROP INDEX IF EXISTS vault_pair_one_active_binding')
    op.execute('DROP INDEX IF EXISTS vault_owned_account_one_active_binding')
    op.execute('DROP TABLE IF EXISTS vault_account_owned_accounts')
    op.execute('DROP TABLE IF EXISTS vault_registry')
    op.execute('DROP TABLE IF EXISTS vault_accounts')
