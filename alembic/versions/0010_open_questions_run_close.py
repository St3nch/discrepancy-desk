"""open_questions + run_low_confidence (ticket 08 / D13)

Revision ID: 0010_run_close
Revises: 0009_suspensions_rows
Create Date: 2026-08-05

Agenda items proposed at close_run; operator decides with disposition.
Low-confidence statements are self-reported by the executor at close.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_run_close"
down_revision: str | None = "0009_suspensions_rows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DISPOSITIONS = (
    "unresolved-likely-permanent",
    "unresolved-awaiting-external-development",
    "not-yet-worked",
)
_DECISIONS = ("pending", "approved", "rejected", "replaced")


def upgrade() -> None:
    dispositions = ", ".join(f"'{d}'" for d in _DISPOSITIONS)
    decisions = ", ".join(f"'{d}'" for d in _DECISIONS)
    op.execute(
        f"""
        CREATE TABLE open_questions (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            introduced_by_run_id INTEGER NOT NULL REFERENCES runs(id),
            source_run_question TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            proposed_text TEXT NOT NULL,
            rationale TEXT NOT NULL,
            proposed_scope TEXT NOT NULL,
            agenda_decision TEXT NOT NULL CHECK (agenda_decision IN ({decisions})),
            disposition TEXT CHECK (
                disposition IS NULL OR disposition IN ({dispositions})
            ),
            settled_text TEXT,
            settled_scope TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_open_questions_run_ordinal
        ON open_questions (introduced_by_run_id, ordinal)
        """
    )
    op.execute(
        """
        CREATE TABLE run_low_confidence (
            id INTEGER PRIMARY KEY NOT NULL,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            ordinal INTEGER NOT NULL,
            statement TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_run_low_confidence_run_ordinal
        ON run_low_confidence (run_id, ordinal)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS run_low_confidence")
    op.execute("DROP TABLE IF EXISTS open_questions")
