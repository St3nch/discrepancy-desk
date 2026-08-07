"""Renditions and units (ticket 12)

Revision ID: 0015_renditions
Revises: 0014_angles
Create Date: 2026-08-06

Composition is executor-proposed under a run (same shape as propose_claim).
A rendition belongs to one case via one angle (D2). Units are ordered posts
within a thread. Status starts at draft; cleared/published/rejected arrive
in tickets 13–14. Only draft is writable in this ticket.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_renditions"
down_revision: str | None = "0014_angles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RENDITION_STATUSES = ("draft", "cleared", "published", "rejected")
_PLATFORMS = ("x",)
_FORMATS = ("thread",)


def upgrade() -> None:
    statuses = ", ".join(f"'{s}'" for s in _RENDITION_STATUSES)
    platforms = ", ".join(f"'{p}'" for p in _PLATFORMS)
    formats = ", ".join(f"'{f}'" for f in _FORMATS)
    op.execute(
        f"""
        CREATE TABLE renditions (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            angle_id INTEGER NOT NULL REFERENCES angles(id),
            run_id INTEGER NOT NULL REFERENCES runs(id),
            platform TEXT NOT NULL CHECK (platform IN ({platforms})),
            format TEXT NOT NULL CHECK (format IN ({formats})),
            status TEXT NOT NULL CHECK (status IN ({statuses})),
            rubric_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE rendition_units (
            id INTEGER PRIMARY KEY NOT NULL,
            rendition_id INTEGER NOT NULL REFERENCES renditions(id),
            ordinal INTEGER NOT NULL,
            body TEXT NOT NULL,
            UNIQUE (rendition_id, ordinal)
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE rendition_unit_claims (
            id INTEGER PRIMARY KEY NOT NULL,
            unit_id INTEGER NOT NULL REFERENCES rendition_units(id),
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            ordinal INTEGER NOT NULL,
            UNIQUE (unit_id, claim_id)
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rendition_unit_claims")
    op.execute("DROP TABLE IF EXISTS rendition_units")
    op.execute("DROP TABLE IF EXISTS renditions")
