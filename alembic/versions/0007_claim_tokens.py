"""claim_token on runs — opaque claim identity (F-25b)

Revision ID: 0007_claim_tokens
Revises: 0006_leases
Create Date: 2026-08-05

Identifies a *claim instance*, not an executor (ADR 8). Cleared on reclaim.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_claim_tokens"
down_revision: str | None = "0006_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE runs ADD COLUMN claim_token TEXT")


def downgrade() -> None:
    pass
