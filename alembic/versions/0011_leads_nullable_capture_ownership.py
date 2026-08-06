"""leads table; captures.run_id and case_id nullable (ticket 09 / D18)

Revision ID: 0011_leads
Revises: 0010_run_close
Create Date: 2026-08-05

A lead has no run. Capture ownership becomes optional so lead drops and run
captures share one Vault path. Lead material is unexamined; identity-only
leads hold no capture row.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_leads"
down_revision: str | None = "0010_run_close"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATERIAL = ("captured", "identity_only")
_INBOX = ("open", "attached", "promoted", "disposed")


def upgrade() -> None:
    # SQLite: rebuild captures so run_id / case_id may be NULL (lead captures).
    op.execute(
        """
        CREATE TABLE captures_new (
            id INTEGER PRIMARY KEY NOT NULL,
            run_id INTEGER REFERENCES runs(id),
            case_id INTEGER REFERENCES cases(id),
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
        INSERT INTO captures_new (
            id, run_id, case_id, url, sha256, content_type,
            byte_size, vault_relpath, status, created_at
        )
        SELECT
            id, run_id, case_id, url, sha256, content_type,
            byte_size, vault_relpath, status, created_at
        FROM captures
        """
    )
    op.execute("DROP TABLE captures")
    op.execute("ALTER TABLE captures_new RENAME TO captures")

    materials = ", ".join(f"'{m}'" for m in _MATERIAL)
    inboxes = ", ".join(f"'{s}'" for s in _INBOX)
    op.execute(
        f"""
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY NOT NULL,
            url TEXT NOT NULL,
            note TEXT NOT NULL,
            summary TEXT,
            material_status TEXT NOT NULL CHECK (
                material_status IN ({materials})
            ),
            capture_id INTEGER REFERENCES captures(id),
            inbox_status TEXT NOT NULL CHECK (
                inbox_status IN ({inboxes})
            ),
            case_id INTEGER REFERENCES cases(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                (
                    material_status = 'captured'
                    AND capture_id IS NOT NULL
                )
                OR (
                    material_status = 'identity_only'
                    AND capture_id IS NULL
                )
            ),
            CHECK (
                (
                    inbox_status IN ('open', 'disposed')
                    AND case_id IS NULL
                )
                OR (
                    inbox_status IN ('attached', 'promoted')
                    AND case_id IS NOT NULL
                )
            )
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS leads")
    # Cannot restore NOT NULL on run_id/case_id without data loss if nulls exist.
    # Leave captures nullable on downgrade.
