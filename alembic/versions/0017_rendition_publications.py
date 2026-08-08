"""Rendition publication records bound to authorizing clearance (ticket 14)

Revision ID: 0017_rendition_publications
Revises: 0016_rendition_approvals
Create Date: 2026-08-07

One approval authorizes one publication set (VISION §14). Per-unit rows record
what went out externally; approval_id is durable (not the projection pointer).
No account_id — D17 one brand per deployment.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017_rendition_publications"
down_revision: str | None = "0016_rendition_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VERIFICATION = ("unverified", "verified", "failed")
_PLATFORMS = ("x",)


def upgrade() -> None:
    verification = ", ".join(f"'{s}'" for s in _VERIFICATION)
    platforms = ", ".join(f"'{s}'" for s in _PLATFORMS)
    op.execute(
        f"""
        CREATE TABLE rendition_publications (
            id INTEGER PRIMARY KEY NOT NULL,
            rendition_id INTEGER NOT NULL REFERENCES renditions(id),
            approval_id INTEGER NOT NULL REFERENCES rendition_approvals(id),
            actor TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE (rendition_id)
        ) STRICT
        """
    )
    op.execute(
        f"""
        CREATE TABLE rendition_publication_units (
            id INTEGER PRIMARY KEY NOT NULL,
            publication_id INTEGER NOT NULL REFERENCES rendition_publications(id),
            unit_ordinal INTEGER NOT NULL,
            platform TEXT NOT NULL CHECK (platform IN ({platforms})),
            external_post_id TEXT NOT NULL,
            canonical_url TEXT NOT NULL,
            published_at TEXT NOT NULL,
            verification_state TEXT NOT NULL CHECK (verification_state IN ({verification})),
            UNIQUE (publication_id, unit_ordinal)
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rendition_publication_units")
    op.execute("DROP TABLE IF EXISTS rendition_publications")
