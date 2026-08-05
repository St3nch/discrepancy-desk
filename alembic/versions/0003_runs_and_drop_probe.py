"""runs table; drop temporary probe tables (F-08)

Revision ID: 0003_runs
Revises: 0002_cases
Create Date: 2026-08-05

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_runs"
down_revision: str | None = "0002_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Full run-status vocabulary (ADR 8 / D12). Ticket 03 only transitions
# draft → approved → claimed; others remain reachable in the CHECK only.
_RUN_STATUSES = (
    "draft",
    "approved",
    "claimed",
    "suspended",
    "complete",
    "abandoned",
    "cancelled",
)


def upgrade() -> None:
    statuses = ", ".join(f"'{s}'" for s in _RUN_STATUSES)
    op.execute(
        f"""
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            status TEXT NOT NULL CHECK (status IN ({statuses})),
            question TEXT NOT NULL,
            scope TEXT NOT NULL,
            rubric_version TEXT NOT NULL,
            rubric_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        ) STRICT
        """
    )
    # F-08: probe surface removed with first real MCP tool (claim_next_run).
    op.execute("DROP TABLE IF EXISTS probe_notes")
    op.execute("DROP TABLE IF EXISTS probe_parents")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS runs")
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
