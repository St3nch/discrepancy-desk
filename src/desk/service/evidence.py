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

# D21 / VISION §13: non-publishable states. Categorical — not a severity ladder.
# If any cited claim is in this set, the inference must also be.
NON_PUBLISHABLE_PUBLICATION_RISKS: Final[frozenset[str]] = frozenset({"unknown", "living_private"})

ANGLE_STATUSES: Final[frozenset[str]] = frozenset({"active", "chosen", "dismissed"})

# Rendition lifecycle (ticket 12 writes draft only; 13 clears; 14 publishes/rejects).
RENDITION_STATUSES: Final[frozenset[str]] = frozenset({"draft", "cleared", "published", "rejected"})

# Destination platform/format pairs. Extend deliberately — not free text.
RENDITION_PLATFORMS: Final[frozenset[str]] = frozenset({"x"})
RENDITION_FORMATS: Final[frozenset[str]] = frozenset({"thread"})
ALLOWED_RENDITION_PLATFORM_FORMATS: Final[frozenset[tuple[str, str]]] = frozenset({("x", "thread")})

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

# Capture examination states (ADR 1 / ticket 04–08). Examined is set only by
# explicit executor report at close_run (F-32), never inferred from uncited-ness.
CAPTURE_STATUSES: Final[frozenset[str]] = frozenset({"unexamined", "examined", "cited"})

# Lead material admission (ticket 09 / 09a / ADR 7 / D19).
# captured — Vault row exists (capture_id required).
# identity_only — status-code wall 401/402/403; no bytes (capture_id NULL).
# unsupported_type — fetched but unparseable; URL parked, no Vault (capture_id NULL).
LEAD_MATERIAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"captured", "identity_only", "unsupported_type"}
)

# Lead inbox lifecycle. open until operator attaches, promotes, or disposes.
LEAD_INBOX_STATUSES: Final[frozenset[str]] = frozenset({"open", "attached", "promoted", "disposed"})

# list_leads filter only — not a stored inbox_status value.
LIST_LEADS_ALL: Final[str] = "all"
