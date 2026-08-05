"""Durable run_suspensions rows (F-28)

Revision ID: 0009_suspensions_rows
Revises: 0008_suspensions
Create Date: 2026-08-05

Each mid-flight suspend-and-ask is an ordered row. Projection columns on
runs remain for list rendering of the latest/open suspension; history is
never overwritten away.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_suspensions_rows"
down_revision: str | None = "0008_suspensions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE run_suspensions (
            id INTEGER PRIMARY KEY NOT NULL,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            ordinal INTEGER NOT NULL,
            question TEXT NOT NULL,
            uncertainty TEXT NOT NULL,
            default_action TEXT NOT NULL,
            suspended_at TEXT NOT NULL,
            human_answer TEXT,
            answered_at TEXT
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_run_suspensions_run_ordinal
        ON run_suspensions (run_id, ordinal)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS run_suspensions")
