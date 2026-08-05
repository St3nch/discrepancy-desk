"""Suspension fields on runs (ticket 07)

Revision ID: 0008_suspensions
Revises: 0007_claim_tokens
Create Date: 2026-08-05

One active suspension per run (overwrite on a later suspend). History of
multiple suspensions is out of scope for this ticket.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_suspensions"
down_revision: str | None = "0007_claim_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Executor-stated question while working a claimed run.
    op.execute("ALTER TABLE runs ADD COLUMN suspension_question TEXT")
    op.execute("ALTER TABLE runs ADD COLUMN suspension_uncertainty TEXT")
    op.execute("ALTER TABLE runs ADD COLUMN suspension_default_action TEXT")
    op.execute("ALTER TABLE runs ADD COLUMN suspended_at TEXT")
    # Human answer; null until the operator resumes the run.
    op.execute("ALTER TABLE runs ADD COLUMN human_answer TEXT")
    op.execute("ALTER TABLE runs ADD COLUMN answered_at TEXT")


def downgrade() -> None:
    pass
