"""cases table — first domain object

Revision ID: 0002_cases
Revises: 0001_probe
Create Date: 2026-08-05

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_cases"
down_revision: str | None = "0001_probe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No complete/closed status column — a Case never completes (CONTEXT.md).
    # No account_id — one brand per deployment (D17); multi-brand is process separation.
    op.execute(
        """
        CREATE TABLE cases (
            id INTEGER PRIMARY KEY NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cases")
