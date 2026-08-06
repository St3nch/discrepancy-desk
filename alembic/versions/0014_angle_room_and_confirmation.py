"""Angle Room, claim confirmation history, quotation shelf (ticket 11)

Revision ID: 0014_angles
Revises: 0013_coverage
Create Date: 2026-08-06

Angle Room: angles and public questions link claims; confirmation attaches at
use (ADR 2) with durable claim_confirmations (VISION §18). Quotation shelf is
operator-selected. Dismissals are durable.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_angles"
down_revision: str | None = "0013_coverage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ANGLE_STATUSES = ("active", "chosen", "dismissed")


def upgrade() -> None:
    # Downgrade leaves confirmed_at in place (SQLite column drop is a rebuild).
    # Re-upgrade after that must not fail on duplicate column.
    conn = op.get_bind()
    cols = {
        str(row[1])
        for row in conn.exec_driver_sql("PRAGMA table_info(claims)").fetchall()
    }
    if "confirmed_at" not in cols:
        op.execute("ALTER TABLE claims ADD COLUMN confirmed_at TEXT")

    op.execute(
        """
        CREATE TABLE claim_confirmations (
            id INTEGER PRIMARY KEY NOT NULL,
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            proposed_source_basis TEXT NOT NULL,
            proposed_corroboration TEXT NOT NULL,
            proposed_certainty TEXT NOT NULL,
            proposed_posture TEXT NOT NULL,
            proposed_qualification TEXT NOT NULL,
            proposed_publication_risk TEXT NOT NULL,
            confirmed_source_basis TEXT NOT NULL,
            confirmed_corroboration TEXT NOT NULL,
            confirmed_certainty TEXT NOT NULL,
            confirmed_posture TEXT NOT NULL,
            confirmed_qualification TEXT NOT NULL,
            confirmed_publication_risk TEXT NOT NULL,
            actor TEXT NOT NULL,
            confirmed_at TEXT NOT NULL
        ) STRICT
        """
    )

    statuses = ", ".join(f"'{s}'" for s in _ANGLE_STATUSES)
    op.execute(
        f"""
        CREATE TABLE angles (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ({statuses})),
            dismissal_reason TEXT,
            dismissed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                (
                    status = 'dismissed'
                    AND dismissal_reason IS NOT NULL
                    AND dismissed_at IS NOT NULL
                )
                OR (
                    status IN ('active', 'chosen')
                    AND dismissal_reason IS NULL
                    AND dismissed_at IS NULL
                )
            )
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE angle_claims (
            id INTEGER PRIMARY KEY NOT NULL,
            angle_id INTEGER NOT NULL REFERENCES angles(id),
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            ordinal INTEGER NOT NULL,
            linked_at TEXT NOT NULL,
            UNIQUE (angle_id, claim_id)
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE public_questions (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            question_text TEXT NOT NULL,
            circulating_version TEXT NOT NULL,
            where_asked TEXT NOT NULL,
            origin TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE public_question_claims (
            id INTEGER PRIMARY KEY NOT NULL,
            public_question_id INTEGER NOT NULL REFERENCES public_questions(id),
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            ordinal INTEGER NOT NULL,
            linked_at TEXT NOT NULL,
            UNIQUE (public_question_id, claim_id)
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE quotation_shelf_entries (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            capture_id INTEGER NOT NULL REFERENCES captures(id),
            locator TEXT NOT NULL,
            quoted_text TEXT NOT NULL,
            speaker TEXT NOT NULL,
            attribution_frame TEXT NOT NULL,
            actor TEXT NOT NULL,
            added_at TEXT NOT NULL
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS quotation_shelf_entries")
    op.execute("DROP TABLE IF EXISTS public_question_claims")
    op.execute("DROP TABLE IF EXISTS public_questions")
    op.execute("DROP TABLE IF EXISTS angle_claims")
    op.execute("DROP TABLE IF EXISTS angles")
    op.execute("DROP TABLE IF EXISTS claim_confirmations")
    # SQLite: leave confirmed_at column.
