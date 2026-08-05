"""probe tables (temporary ticket 01 skeleton)

Revision ID: 0001_probe
Revises:
Create Date: 2026-08-05

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_probe"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # STRICT tables: SQLite enforces declared column types.
    # FK: REFERENCES + PRAGMA foreign_keys=ON on every connection.
    op.execute(
        """
        CREATE TABLE probe_parents (
            id INTEGER PRIMARY KEY NOT NULL,
            parent_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE probe_notes (
            id INTEGER PRIMARY KEY NOT NULL,
            parent_id INTEGER NOT NULL REFERENCES probe_parents(id),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS probe_notes")
    op.execute("DROP TABLE IF EXISTS probe_parents")
