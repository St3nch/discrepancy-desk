"""Add bounded source references for the operator loop.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE source_records (
        id TEXT PRIMARY KEY,
        work_item_id TEXT NOT NULL REFERENCES work_items(id) ON DELETE RESTRICT,
        source_kind TEXT NOT NULL CHECK (source_kind IN ('url','manual_note','owned_post','api_evidence')),
        locator TEXT,
        note_text BLOB,
        created_at TEXT NOT NULL,
        CHECK (locator IS NOT NULL OR note_text IS NOT NULL),
        UNIQUE(work_item_id, source_kind, locator)
    ) STRICT;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_records")
