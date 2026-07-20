"""Add M04 editorial organization and scheduling contract.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE editorial_profiles (
        work_item_id TEXT PRIMARY KEY REFERENCES work_items(id) ON DELETE RESTRICT,
        account_id TEXT NOT NULL REFERENCES owned_accounts(id) ON DELETE RESTRICT,
        lane TEXT NOT NULL CHECK (lane IN ('archive','docket','flash_release')),
        topic TEXT CHECK (topic IS NULL OR (length(trim(topic)) BETWEEN 1 AND 200)),
        priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
        operator_notes BLOB,
        is_dormant INTEGER NOT NULL DEFAULT 0 CHECK (is_dormant IN (0,1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE work_item_tags (
        work_item_id TEXT NOT NULL REFERENCES work_items(id) ON DELETE RESTRICT,
        tag TEXT NOT NULL CHECK (length(tag) BETWEEN 1 AND 64 AND tag=lower(trim(tag))),
        PRIMARY KEY(work_item_id, tag)
    ) STRICT;
    """)
    op.execute("""
    CREATE TABLE schedule_slots (
        id TEXT PRIMARY KEY,
        work_item_id TEXT NOT NULL REFERENCES work_items(id) ON DELETE RESTRICT,
        account_id TEXT NOT NULL REFERENCES owned_accounts(id) ON DELETE RESTRICT,
        approved_revision_id TEXT REFERENCES revisions(id) ON DELETE RESTRICT,
        scheduled_for TEXT,
        preferred_window_start TEXT,
        preferred_window_end TEXT,
        earliest_useful_at TEXT,
        stale_after TEXT,
        hard_deadline_at TEXT,
        is_evergreen INTEGER NOT NULL DEFAULT 0 CHECK (is_evergreen IN (0,1)),
        status TEXT NOT NULL CHECK (status IN ('active','unscheduled','superseded')),
        supersedes_schedule_id TEXT REFERENCES schedule_slots(id) ON DELETE RESTRICT,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        operation_key TEXT NOT NULL,
        CHECK (supersedes_schedule_id IS NULL OR supersedes_schedule_id <> id),
        CHECK (preferred_window_start IS NULL OR preferred_window_end IS NULL OR preferred_window_end >= preferred_window_start),
        CHECK (earliest_useful_at IS NULL OR stale_after IS NULL OR stale_after >= earliest_useful_at),
        CHECK (earliest_useful_at IS NULL OR hard_deadline_at IS NULL OR hard_deadline_at >= earliest_useful_at)
    ) STRICT;
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_schedule_slots_active_work_item
    ON schedule_slots(work_item_id) WHERE status='active';
    """)
    op.execute("CREATE INDEX ix_schedule_slots_account_time ON schedule_slots(account_id, scheduled_for)")
    op.execute("""
    CREATE TABLE editorial_targets (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES owned_accounts(id) ON DELETE RESTRICT,
        target_kind TEXT NOT NULL CHECK (length(trim(target_kind)) BETWEEN 1 AND 80),
        window_days INTEGER NOT NULL CHECK (window_days BETWEEN 1 AND 366),
        target_value INTEGER NOT NULL CHECK (target_value >= 0),
        effective_from TEXT NOT NULL,
        effective_until TEXT,
        source_note TEXT NOT NULL CHECK (length(trim(source_note)) BETWEEN 1 AND 500),
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL,
        CHECK (effective_until IS NULL OR effective_until >= effective_from)
    ) STRICT;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS editorial_targets")
    op.execute("DROP INDEX IF EXISTS ix_schedule_slots_account_time")
    op.execute("DROP INDEX IF EXISTS uq_schedule_slots_active_work_item")
    op.execute("DROP TABLE IF EXISTS schedule_slots")
    op.execute("DROP TABLE IF EXISTS work_item_tags")
    op.execute("DROP TABLE IF EXISTS editorial_profiles")
