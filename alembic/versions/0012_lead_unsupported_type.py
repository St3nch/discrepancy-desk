"""leads.material_status: unsupported_type (ticket 09a / D19)

Revision ID: 0012_unsupported
Revises: 0011_leads
Create Date: 2026-08-05

Park URL-only leads when the fetch succeeded but the content type cannot be
parsed. Same shape as identity_only for capture_id (must be NULL). The CHECK
is rewritten deliberately — both non-capture statuses forbid a capture_id;
captured requires one. retain_capture_from_bytes is not changed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_unsupported"
down_revision: str | None = "0011_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATERIAL = ("captured", "identity_only", "unsupported_type")
_INBOX = ("open", "attached", "promoted", "disposed")


def upgrade() -> None:
    materials = ", ".join(f"'{m}'" for m in _MATERIAL)
    inboxes = ", ".join(f"'{s}'" for s in _INBOX)
    # SQLite: rebuild leads so CHECK vocabulary and capture_id rule update.
    op.execute(
        f"""
        CREATE TABLE leads_new (
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
                    material_status IN ('identity_only', 'unsupported_type')
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
    op.execute(
        """
        INSERT INTO leads_new (
            id, url, note, summary, material_status, capture_id,
            inbox_status, case_id, created_at, updated_at
        )
        SELECT
            id, url, note, summary, material_status, capture_id,
            inbox_status, case_id, created_at, updated_at
        FROM leads
        """
    )
    op.execute("DROP TABLE leads")
    op.execute("ALTER TABLE leads_new RENAME TO leads")


def downgrade() -> None:
    # Rows with unsupported_type cannot survive a reverse CHECK without data loss.
    op.execute("DELETE FROM leads WHERE material_status = 'unsupported_type'")
    materials = ", ".join(f"'{m}'" for m in ("captured", "identity_only"))
    inboxes = ", ".join(f"'{s}'" for s in _INBOX)
    op.execute(
        f"""
        CREATE TABLE leads_old (
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
    op.execute(
        """
        INSERT INTO leads_old (
            id, url, note, summary, material_status, capture_id,
            inbox_status, case_id, created_at, updated_at
        )
        SELECT
            id, url, note, summary, material_status, capture_id,
            inbox_status, case_id, created_at, updated_at
        FROM leads
        """
    )
    op.execute("DROP TABLE leads")
    op.execute("ALTER TABLE leads_old RENAME TO leads")
