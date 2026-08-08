"""Rendition approvals — exact-content snapshot (ticket 13)

Revision ID: 0016_rendition_approvals
Revises: 0015_renditions
Create Date: 2026-08-07

Approval is an append-only record carrying the ordered unit bodies as cleared.
The rendition holds status and current_approval_id for projection; whether an
approval still stands is derived by comparing current content to the snapshot
(no is_valid flag — D20 lesson).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_rendition_approvals"
down_revision: str | None = "0015_renditions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Projection pointer only — not a FK (circular with approvals → renditions).
    op.execute(
        """
        ALTER TABLE renditions ADD COLUMN current_approval_id INTEGER NULL
        """
    )
    op.execute(
        """
        CREATE TABLE rendition_approvals (
            id INTEGER PRIMARY KEY NOT NULL,
            rendition_id INTEGER NOT NULL REFERENCES renditions(id),
            sequence INTEGER NOT NULL,
            actor TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            UNIQUE (rendition_id, sequence)
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE rendition_approval_units (
            id INTEGER PRIMARY KEY NOT NULL,
            approval_id INTEGER NOT NULL REFERENCES rendition_approvals(id),
            ordinal INTEGER NOT NULL,
            body TEXT NOT NULL,
            UNIQUE (approval_id, ordinal)
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rendition_approval_units")
    op.execute("DROP TABLE IF EXISTS rendition_approvals")
    # SQLite cannot DROP COLUMN portably before 3.35; leave column on downgrade path.
