"""Add append-only revision and publication lineage.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE revisions ADD COLUMN supersedes_revision_id TEXT REFERENCES revisions(id) ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE publications ADD COLUMN replaces_publication_id TEXT REFERENCES publications(id) ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE publications ADD COLUMN resolution_kind TEXT CHECK (resolution_kind IN ('initial','replacement'))"
    )
    op.execute("UPDATE publications SET resolution_kind='initial' WHERE resolution_kind IS NULL")
    op.execute(
        "CREATE UNIQUE INDEX uq_publication_replacement ON publications(replaces_publication_id) WHERE replaces_publication_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_publication_replacement")
    # SQLite does not safely support dropping these columns in all admitted versions.
    # Downgrade remains intentionally non-destructive for governed evidence history.
