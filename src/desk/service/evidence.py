"""Six evidence dimensions — full VISION.md §11 vocabulary (no local subset)."""

from __future__ import annotations

from typing import Final

# Source basis
SOURCE_BASIS: Final[frozenset[str]] = frozenset(
    {
        "contemporaneous_record",
        "contemporaneous_report",
        "direct_participant_recollection",
        "later_retrospective_claim",
        "scholarly_interpretation",
        "technical_inference",
        "desk_inference",
        "other",
    }
)

CORROBORATION: Final[frozenset[str]] = frozenset(
    {
        "unassessed",
        "single_source",
        "multi_source_dependent",
        "independently_corroborated",
        "contradicted",
    }
)

CERTAINTY: Final[frozenset[str]] = frozenset(
    {
        "unassessed",
        "established",
        "probable",
        "contested",
        "speculative",
        "unknown",
    }
)

POSTURE: Final[frozenset[str]] = frozenset(
    {
        "factual_assertion",
        "interpretation",
        "participant_account",
        "allegation",
        "disputed_assertion",
        "research_lead",
        "pattern_candidate",
    }
)

# Required qualification is free text (exact language), not an enum.

PUBLICATION_RISK: Final[frozenset[str]] = frozenset(
    {
        "unknown",
        "living_private",
        "public_official_official_capacity",
        "public_figure",
        "deceased",
        "institution",
        "not_applicable",
    }
)

# Postures that require non-empty qualification (ADR 9 step 5).
QUALIFICATION_REQUIRED_POSTURES: Final[frozenset[str]] = frozenset(
    {
        "allegation",
        "participant_account",
    }
)

# Inference claims cite other claims, not captures (source_basis desk_inference).
INFERENCE_SOURCE_BASIS: Final[str] = "desk_inference"

CONFIRMATION_STATUSES: Final[frozenset[str]] = frozenset({"unconfirmed", "confirmed"})
