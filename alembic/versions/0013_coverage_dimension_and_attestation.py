"""run coverage_dimension (nullable) + coverage_attestations (ticket 10 / D20)

Revision ID: 0013_coverage
Revises: 0012_unsupported
Create Date: 2026-08-05

Operator sets coverage_dimension at dispatch. Additive column — no rebuild of
runs on upgrade (runs is referenced by captures, claims, suspensions, open
questions, low-confidence). Existing rows stay NULL (pre-D20; no fabricated
judgement). create_run always sets a non-null value.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0013_coverage"
down_revision: str | None = "0012_unsupported"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAGES = (
    "official_foundation",
    "public_question",
    "deep_context",
    "story_intelligence",
    "editorial_development",
    "composition",
)

_RUN_STATUSES = (
    "draft",
    "approved",
    "claimed",
    "suspended",
    "complete",
    "abandoned",
    "cancelled",
)


def _sqlite_rebuild_drop_column(
    *,
    table: str,
    create_sql: str,
    columns: Sequence[str],
) -> None:
    """Drop a column from a referenced SQLite table (FK-safe rebuild).

    SQLite refuses DROP COLUMN when the column appears in a table CHECK.
    Procedure: foreign_keys OFF for the duration, rebuild, copy, drop, rename,
    foreign_key_check before commit, foreign_keys ON.

    Any future rebuild of a table that other tables reference must use this
    pattern — empty-DB upgrades never exercise FK enforcement.
    """
    bind = op.get_bind()
    cols = ", ".join(columns)
    bind.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        bind.execute(text(create_sql))
        bind.execute(text(f"INSERT INTO {table}_new ({cols}) SELECT {cols} FROM {table}"))
        bind.execute(text(f"DROP TABLE {table}"))
        bind.execute(text(f"ALTER TABLE {table}_new RENAME TO {table}"))
        violations = bind.execute(text("PRAGMA foreign_key_check")).fetchall()
        if violations:
            raise RuntimeError(f"foreign_key_check failed after rebuilding {table}: {violations}")
    finally:
        bind.execute(text("PRAGMA foreign_keys=ON"))


def upgrade() -> None:
    stages = ", ".join(f"'{s}'" for s in _STAGES)
    # Additive only — no DEFAULT. Existing rows receive NULL (pre-D20).
    # CHECK is on the column; enum test parses it from sqlite_master.
    op.execute(
        f"""
        ALTER TABLE runs ADD COLUMN coverage_dimension TEXT
            CHECK (
                coverage_dimension IS NULL
                OR coverage_dimension IN ({stages})
            )
        """
    )
    op.execute(
        f"""
        CREATE TABLE coverage_attestations (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            stage TEXT NOT NULL CHECK (stage IN ({stages})),
            actor TEXT NOT NULL,
            attested_at TEXT NOT NULL
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS coverage_attestations")
    statuses = ", ".join(f"'{s}'" for s in _RUN_STATUSES)
    # DROP COLUMN fails because coverage_dimension is in a CHECK — rebuild.
    create_sql = f"""
        CREATE TABLE runs_new (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            status TEXT NOT NULL CHECK (status IN ({statuses})),
            question TEXT NOT NULL,
            scope TEXT NOT NULL,
            rubric_version TEXT NOT NULL,
            rubric_text TEXT NOT NULL,
            capture_budget INTEGER NOT NULL DEFAULT 20,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            lease_expires_at TEXT,
            claim_token TEXT,
            suspension_question TEXT,
            suspension_uncertainty TEXT,
            suspension_default_action TEXT,
            suspended_at TEXT,
            human_answer TEXT,
            answered_at TEXT
        ) STRICT
    """
    columns = (
        "id",
        "case_id",
        "status",
        "question",
        "scope",
        "rubric_version",
        "rubric_text",
        "capture_budget",
        "created_at",
        "updated_at",
        "lease_expires_at",
        "claim_token",
        "suspension_question",
        "suspension_uncertainty",
        "suspension_default_action",
        "suspended_at",
        "human_answer",
        "answered_at",
    )
    _sqlite_rebuild_drop_column(
        table="runs",
        create_sql=create_sql,
        columns=columns,
    )
