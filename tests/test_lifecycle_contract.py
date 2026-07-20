from __future__ import annotations

from discrepancy_desk.persistence import LEGAL_TRANSITIONS

EXPECTED_TRANSITIONS = {
    "captured": {"research_needed", "research_ready", "drafting", "withdrawn"},
    "research_needed": {"research_ready", "withdrawn"},
    "research_ready": {"drafting", "withdrawn"},
    "drafting": {"human_review_needed", "withdrawn"},
    "human_review_needed": {"approved", "rejected", "drafting", "evidence_blocked"},
    "approved": {"manual_ready", "human_review_needed", "evidence_blocked", "withdrawn"},
    "manual_ready": {
        "published",
        "human_review_needed",
        "publication_mismatch",
        "evidence_blocked",
        "withdrawn",
    },
    "published": set(),
    "rejected": {"drafting"},
    "withdrawn": {"drafting"},
    "publication_mismatch": {"human_review_needed"},
    "evidence_blocked": {"human_review_needed", "drafting"},
}


def test_implemented_lifecycle_contract_is_exact() -> None:
    assert LEGAL_TRANSITIONS == EXPECTED_TRANSITIONS


def test_generic_transition_table_does_not_admit_dead_publication_recovery() -> None:
    assert "published" not in LEGAL_TRANSITIONS["publication_mismatch"]
