"""Vault captures + element structure; run capture_budget

Revision ID: 0004_captures
Revises: 0003_runs
Create Date: 2026-08-05

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_captures"
down_revision: str | None = "0003_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Budget lives on the run; default for rows created before this column existed.
    op.execute(
        "ALTER TABLE runs ADD COLUMN capture_budget INTEGER NOT NULL DEFAULT 20"
    )

    op.execute(
        """
        CREATE TABLE captures (
            id INTEGER PRIMARY KEY NOT NULL,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            case_id INTEGER NOT NULL REFERENCES cases(id),
            url TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            content_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            vault_relpath TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('unexamined', 'examined', 'cited')
            ),
            created_at TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE document_versions (
            id INTEGER PRIMARY KEY NOT NULL,
            capture_id INTEGER NOT NULL REFERENCES captures(id),
            version_number INTEGER NOT NULL,
            parser_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY NOT NULL,
            document_version_id INTEGER NOT NULL REFERENCES document_versions(id),
            locator TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            element_type TEXT NOT NULL,
            text TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE regions (
            id INTEGER PRIMARY KEY NOT NULL,
            element_id INTEGER NOT NULL REFERENCES elements(id),
            start_offset INTEGER NOT NULL,
            end_offset INTEGER NOT NULL
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regions")
    op.execute("DROP TABLE IF EXISTS elements")
    op.execute("DROP TABLE IF EXISTS document_versions")
    op.execute("DROP TABLE IF EXISTS captures")
    # SQLite cannot DROP COLUMN portably without table rebuild; leave capture_budget.
