"""Claim confirmation at use (ADR 2 / VISION §12 / D21).

Confirmation attaches when a claim is linked into Angle Room work — not at
storage. A durable confirmation row records prior values vs confirmed values;
claims columns remain the current-value projection (F-28: history is never the
projection alone).

Re-confirmation is allowed: each act appends a claim_confirmations row and
updates the projection. That is how §10's correction-rate is measurable across
decisions, not only inside a single first confirmation.

D21:
- desk_inference checks run against the *confirmed* source_basis (not the
  proposal). Crossing the inference / non-inference boundary at confirmation
  is refused — support structure was built at proposal; reclassifying kind is
  not a strength correction.
- Confirming an inference requires every cited claim already confirmed.
- Publication-risk inheritance is categorical (non-publishable set), not ranked.
- Re-confirming a claim to non-publishable risk is refused while a confirmed
  inference cites it (name the blockers; no invalidation of dependents).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select, update

from desk.db.schema import claim_confirmations, claim_inference_citations, claims
from desk.refusals import DeskRefusal
from desk.service.evidence import (
    CERTAINTY,
    CORROBORATION,
    INFERENCE_SOURCE_BASIS,
    NON_PUBLISHABLE_PUBLICATION_RISKS,
    POSTURE,
    PUBLICATION_RISK,
    QUALIFICATION_REQUIRED_POSTURES,
    SOURCE_BASIS,
)
from desk.service.models import LinkClaimDimensions


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def validate_dimensions_payload(dims: LinkClaimDimensions) -> None:
    pairs = (
        ("source_basis", dims.source_basis, SOURCE_BASIS),
        ("corroboration", dims.corroboration, CORROBORATION),
        ("certainty", dims.certainty, CERTAINTY),
        ("posture", dims.posture, POSTURE),
        ("publication_risk", dims.publication_risk, PUBLICATION_RISK),
    )
    for name, value, allowed in pairs:
        if value not in allowed:
            raise DeskRefusal(
                code="DIMENSION_INVALID",
                what_happened=f"{name} value {value!r} is not in the vocabulary.",
                what_was_preserved="Nothing was written.",
                what_was_not_changed="Claims and Angle Room objects are unchanged.",
                what_you_can_do=f"Use a value from {sorted(allowed)}.",
            )
    if dims.posture in QUALIFICATION_REQUIRED_POSTURES and not dims.qualification.strip():
        raise DeskRefusal(
            code="QUALIFICATION_REQUIRED",
            what_happened=f"Posture {dims.posture!r} requires non-empty qualification.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="Claims and Angle Room objects are unchanged.",
            what_you_can_do="Provide qualification language for this posture.",
        )


def assert_inference_publication_risk_allowed(
    *,
    inference_risk: str,
    cited_risks: list[str],
) -> None:
    """D21: if any cited risk is non-publishable, inference must be too.

    No severity ladder — categories are not ordered (D21). Soft reclassification
    among *publishable* categories (e.g. deceased → institution) is permitted
    deliberately; that is operator judgement, not a laundering hole.
    """
    cited_nonpub = [r for r in cited_risks if r in NON_PUBLISHABLE_PUBLICATION_RISKS]
    if not cited_nonpub:
        return
    if inference_risk not in NON_PUBLISHABLE_PUBLICATION_RISKS:
        raise DeskRefusal(
            code="INFERENCE_PUBLICATION_RISK_LAUNDER",
            what_happened=(
                f"Inference publication_risk {inference_risk!r} is publishable, but "
                f"cited claim(s) carry non-publishable risk {sorted(set(cited_nonpub))!r} "
                "(D21 / VISION §13). unknown and living_private fail closed."
            ),
            what_was_preserved="No claim was written or confirmed.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Set publication_risk to unknown or living_private to match the "
                "non-publishable cited material."
            ),
        )


def _dims_match_current(dims: LinkClaimDimensions, *, current: dict[str, str], qual: str) -> bool:
    return (
        dims.source_basis == current["source_basis"]
        and dims.corroboration == current["corroboration"]
        and dims.certainty == current["certainty"]
        and dims.posture == current["posture"]
        and dims.publication_risk == current["publication_risk"]
        and qual == current["qualification"]
    )


def _confirmed_inferences_citing(conn: Connection, claim_id: int) -> list[int]:
    """Return claim ids of confirmed desk_inference claims that cite claim_id."""
    rows = conn.execute(
        select(claims.c.id)
        .select_from(
            claim_inference_citations.join(
                claims,
                claim_inference_citations.c.claim_id == claims.c.id,
            )
        )
        .where(claim_inference_citations.c.cited_claim_id == claim_id)
        .where(claims.c.confirmation_status == "confirmed")
        .where(claims.c.source_basis == INFERENCE_SOURCE_BASIS)
    ).all()
    return [int(r.id) for r in rows]


def confirm_claim_for_use(
    conn: Connection,
    *,
    claim_id: int,
    case_id: int,
    dimensions: LinkClaimDimensions | None,
    actor: str = "operator",
) -> None:
    """Confirm or re-confirm a claim for Angle Room use.

    - Unconfirmed + no dimensions → refuse (CONFIRMATION_DIMENSIONS_REQUIRED).
    - Confirmed + no dimensions → no-op (link without re-confirming).
    - Confirmed + dimensions equal to current projection → no-op (nothing discarded).
    - Confirmed + different dimensions → re-confirm (new history row + projection).
    - Unconfirmed + dimensions → first confirmation.

    Inference checks use the *confirmed* source_basis. Crossing the inference /
    non-inference boundary is refused. Re-confirming to non-publishable risk
    while a confirmed inference cites this claim is refused (D21 durability).
    """
    row = conn.execute(
        select(
            claims.c.id,
            claims.c.case_id,
            claims.c.confirmation_status,
            claims.c.source_basis,
            claims.c.corroboration,
            claims.c.certainty,
            claims.c.posture,
            claims.c.qualification,
            claims.c.publication_risk,
        ).where(claims.c.id == claim_id)
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="CLAIM_NOT_FOUND",
            what_happened=f"No claim exists with id {claim_id}.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="Angle Room objects are unchanged.",
            what_you_can_do="Use a claim_id from this case.",
        )
    if int(row.case_id) != case_id:
        raise DeskRefusal(
            code="CLAIM_WRONG_CASE",
            what_happened=f"Claim {claim_id} does not belong to case {case_id}.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="Angle Room objects are unchanged.",
            what_you_can_do="Link claims from this case only.",
        )

    already_confirmed = str(row.confirmation_status) == "confirmed"
    prior = {
        "source_basis": str(row.source_basis),
        "corroboration": str(row.corroboration),
        "certainty": str(row.certainty),
        "posture": str(row.posture),
        "qualification": str(row.qualification),
        "publication_risk": str(row.publication_risk),
    }

    if dimensions is None:
        if already_confirmed:
            return
        raise DeskRefusal(
            code="CONFIRMATION_DIMENSIONS_REQUIRED",
            what_happened=(
                f"Claim {claim_id} is unconfirmed; Angle Room use requires "
                "authoritative evidence dimensions (accept or correct the proposal)."
            ),
            what_was_preserved="Nothing was written.",
            what_was_not_changed="Claim remains unconfirmed; no link was written.",
            what_you_can_do="Pass dimensions with the link or shelf add.",
        )

    validate_dimensions_payload(dimensions)
    qual = (
        dimensions.qualification.strip()
        if dimensions.posture in QUALIFICATION_REQUIRED_POSTURES
        else dimensions.qualification
    )
    if already_confirmed and _dims_match_current(dimensions, current=prior, qual=qual):
        # Same values — not F-42 (nothing different was accepted and discarded).
        return

    # Authoritative kind is what is being written, not what was proposed.
    prior_is_inference = prior["source_basis"] == INFERENCE_SOURCE_BASIS
    confirmed_is_inference = dimensions.source_basis == INFERENCE_SOURCE_BASIS
    if prior_is_inference != confirmed_is_inference:
        raise DeskRefusal(
            code="SOURCE_BASIS_KIND_MISMATCH",
            what_happened=(
                f"Cannot confirm claim {claim_id} as source_basis "
                f"{dimensions.source_basis!r}: the claim was proposed as "
                f"{prior['source_basis']!r}. Crossing the inference / non-inference "
                "boundary would leave the authoritative kind disagreeing with the "
                "support structure built at proposal (D14 escape valve is for "
                "desk_inference only). Correcting strength is allowed; reclassifying "
                "what the claim is is not."
            ),
            what_was_preserved=(
                "Claim confirmation status and dimensions are unchanged."
                if already_confirmed
                else "Claim remains unconfirmed."
            ),
            what_was_not_changed="Nothing was written.",
            what_you_can_do=(
                "Keep source_basis as desk_inference if this is an inference "
                "(with claim citations), or keep the non-inference basis if it "
                "quotes captures. Changing kind requires a new claim with matching "
                "support structure — not a confirmation correction."
            ),
        )

    if confirmed_is_inference:
        cited_rows = conn.execute(
            select(
                claims.c.id,
                claims.c.confirmation_status,
                claims.c.publication_risk,
            )
            .select_from(
                claim_inference_citations.join(
                    claims,
                    claim_inference_citations.c.cited_claim_id == claims.c.id,
                )
            )
            .where(claim_inference_citations.c.claim_id == claim_id)
        ).all()
        unconfirmed_cited = [
            int(r.id) for r in cited_rows if str(r.confirmation_status) != "confirmed"
        ]
        if unconfirmed_cited:
            raise DeskRefusal(
                code="INFERENCE_CITATIONS_UNCONFIRMED",
                what_happened=(
                    f"Cannot confirm inference claim {claim_id}: cited claim(s) "
                    f"{unconfirmed_cited} are still unconfirmed (D21). Confirmation "
                    "is bottom-up — review the basis before the inference."
                ),
                what_was_preserved=(
                    "Claim confirmation is unchanged."
                    if already_confirmed
                    else "Claim remains unconfirmed."
                ),
                what_was_not_changed="Nothing was written.",
                what_you_can_do=(
                    "Confirm each cited claim (link it into Angle Room work) first, "
                    "then confirm this inference."
                ),
            )
        cited_risks = [str(r.publication_risk) for r in cited_rows]
        assert_inference_publication_risk_allowed(
            inference_risk=dimensions.publication_risk,
            cited_risks=cited_risks,
        )

    # D21 durability: refuse making a cited claim non-publishable while a
    # confirmed inference still cites it — name blockers, no invalidation.
    if (
        dimensions.publication_risk in NON_PUBLISHABLE_PUBLICATION_RISKS
        and prior["publication_risk"] not in NON_PUBLISHABLE_PUBLICATION_RISKS
    ):
        blockers = _confirmed_inferences_citing(conn, claim_id)
        if blockers:
            raise DeskRefusal(
                code="CONFIRMATION_BLOCKED_BY_INFERENCE",
                what_happened=(
                    f"Cannot confirm claim {claim_id} to publication_risk "
                    f"{dimensions.publication_risk!r}: confirmed inference claim(s) "
                    f"{blockers} cite it. Making the basis non-publishable would "
                    "leave those inferences stale without invalidating them (D21)."
                ),
                what_was_preserved="Claim confirmation and citing inferences are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do=(
                    f"Re-confirm or rework inference claim(s) {blockers} first "
                    "(e.g. set them to unknown or living_private), then re-confirm "
                    "this claim."
                ),
            )

    now = _utc_now()
    confirmed = {
        "source_basis": dimensions.source_basis,
        "corroboration": dimensions.corroboration,
        "certainty": dimensions.certainty,
        "posture": dimensions.posture,
        "qualification": qual,
        "publication_risk": dimensions.publication_risk,
    }
    actor_name = (actor or "").strip() or "operator"

    # History: prior values (model proposal on first confirm; previous authoritative
    # on re-confirm) vs values written by this confirmation act.
    conn.execute(
        insert(claim_confirmations).values(
            claim_id=claim_id,
            proposed_source_basis=prior["source_basis"],
            proposed_corroboration=prior["corroboration"],
            proposed_certainty=prior["certainty"],
            proposed_posture=prior["posture"],
            proposed_qualification=prior["qualification"],
            proposed_publication_risk=prior["publication_risk"],
            confirmed_source_basis=confirmed["source_basis"],
            confirmed_corroboration=confirmed["corroboration"],
            confirmed_certainty=confirmed["certainty"],
            confirmed_posture=confirmed["posture"],
            confirmed_qualification=confirmed["qualification"],
            confirmed_publication_risk=confirmed["publication_risk"],
            actor=actor_name,
            confirmed_at=now,
        )
    )
    conn.execute(
        update(claims)
        .where(claims.c.id == claim_id)
        .values(
            confirmation_status="confirmed",
            source_basis=confirmed["source_basis"],
            corroboration=confirmed["corroboration"],
            certainty=confirmed["certainty"],
            posture=confirmed["posture"],
            qualification=confirmed["qualification"],
            publication_risk=confirmed["publication_risk"],
            confirmed_at=now,
        )
    )
