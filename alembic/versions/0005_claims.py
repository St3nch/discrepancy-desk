"""claims and quote/inference bindings

Revision ID: 0005_claims
Revises: 0004_captures
Create Date: 2026-08-05

Evidence dimension CHECKs (F-21): full VISION §11 vocabulary at the storage layer,
matching desk.service.evidence frozensets — same standard as runs.status.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_claims"
down_revision: str | None = "0004_captures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in lockstep with desk.service.evidence — tests reconcile via sqlite_master.
_SOURCE_BASIS = (
    "contemporaneous_record",
    "contemporaneous_report",
    "direct_participant_recollection",
    "later_retrospective_claim",
    "scholarly_interpretation",
    "technical_inference",
    "desk_inference",
    "other",
)
_CORROBORATION = (
    "unassessed",
    "single_source",
    "multi_source_dependent",
    "independently_corroborated",
    "contradicted",
)
_CERTAINTY = (
    "unassessed",
    "established",
    "probable",
    "contested",
    "speculative",
    "unknown",
)
_POSTURE = (
    "factual_assertion",
    "interpretation",
    "participant_account",
    "allegation",
    "disputed_assertion",
    "research_lead",
    "pattern_candidate",
)
_PUBLICATION_RISK = (
    "unknown",
    "living_private",
    "public_official_official_capacity",
    "public_figure",
    "deceased",
    "institution",
    "not_applicable",
)


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE claims (
            id INTEGER PRIMARY KEY NOT NULL,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            run_id INTEGER NOT NULL REFERENCES runs(id),
            proposition TEXT NOT NULL,
            confirmation_status TEXT NOT NULL CHECK (
                confirmation_status IN ('unconfirmed', 'confirmed')
            ),
            source_basis TEXT NOT NULL CHECK (
                source_basis IN ({_in_list(_SOURCE_BASIS)})
            ),
            corroboration TEXT NOT NULL CHECK (
                corroboration IN ({_in_list(_CORROBORATION)})
            ),
            certainty TEXT NOT NULL CHECK (
                certainty IN ({_in_list(_CERTAINTY)})
            ),
            posture TEXT NOT NULL CHECK (
                posture IN ({_in_list(_POSTURE)})
            ),
            qualification TEXT NOT NULL,
            publication_risk TEXT NOT NULL CHECK (
                publication_risk IN ({_in_list(_PUBLICATION_RISK)})
            ),
            rubric_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE claim_quote_bindings (
            id INTEGER PRIMARY KEY NOT NULL,
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            capture_id INTEGER NOT NULL REFERENCES captures(id),
            locator TEXT NOT NULL,
            quoted_text TEXT NOT NULL,
            ordinal INTEGER NOT NULL
        ) STRICT
        """
    )
    op.execute(
        """
        CREATE TABLE claim_inference_citations (
            id INTEGER PRIMARY KEY NOT NULL,
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            cited_claim_id INTEGER NOT NULL REFERENCES claims(id),
            ordinal INTEGER NOT NULL
        ) STRICT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claim_inference_citations")
    op.execute("DROP TABLE IF EXISTS claim_quote_bindings")
    op.execute("DROP TABLE IF EXISTS claims")
