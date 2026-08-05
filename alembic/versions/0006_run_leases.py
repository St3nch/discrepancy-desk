"""run lease_expires_at for claim abandonment (ADR 8 / ticket 06)

Revision ID: 0006_leases
Revises: 0005_claims
Create Date: 2026-08-05

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_leases"
down_revision: str | None = "0005_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL when not claimed. ISO-8601 UTC when a claim lease is active.
    op.execute("ALTER TABLE runs ADD COLUMN lease_expires_at TEXT")


def downgrade() -> None:
    # SQLite cannot DROP COLUMN portably without rebuild; leave null column.
    pass
