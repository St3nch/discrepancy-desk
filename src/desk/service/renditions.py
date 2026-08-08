"""propose_rendition / update_rendition / approve_rendition (tickets 12–13).

Ticket 12: executor composition under a claimed run (MCP). Backend never calls
a model. Eligibility is angle-scoped confirmed claims (D2).

Ticket 13: human clears exact ordered content. Approval is an append-only
snapshot (history is never the projection alone). Whether a clearance still
stands is **derived** by comparing current unit bodies (in order) to the
snapshot — never an is_valid flag (D20 lesson). The snapshot binds the whole
sequence; reorder / add / remove invalidates even when individual bodies match.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, delete, func, insert, select, update

from desk.db.schema import (
    angles,
    claims,
    rendition_approval_units,
    rendition_approvals,
    rendition_unit_claims,
    rendition_units,
    renditions,
    runs,
)
from desk.refusals import DeskRefusal
from desk.service.angles import list_rendition_eligible_claims
from desk.service.evidence import ALLOWED_RENDITION_PLATFORM_FORMATS
from desk.service.lease import validate_and_refresh_claim
from desk.service.models import (
    ApprovalInvalidation,
    ApprovalSnapshotUnit,
    ApproveRenditionInput,
    ApproveRenditionResult,
    ClaimRecord,
    ProposeRenditionInput,
    ProposeRenditionResult,
    RenditionApprovalRecord,
    RenditionEligibleClaimsInput,
    RenditionRecord,
    RenditionUnitInput,
    RenditionUnitRecord,
    UpdateRenditionInput,
    UpdateRenditionResult,
)

# Statuses that may still be edited or re-cleared. published/rejected are later tickets.
_EDITABLE_STATUSES = frozenset({"draft", "cleared"})
_APPROVABLE_STATUSES = frozenset({"draft", "cleared"})


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _load_approval(conn: Connection, approval_id: int) -> RenditionApprovalRecord | None:
    row = conn.execute(
        select(
            rendition_approvals.c.id,
            rendition_approvals.c.rendition_id,
            rendition_approvals.c.sequence,
            rendition_approvals.c.actor,
            rendition_approvals.c.approved_at,
        ).where(rendition_approvals.c.id == approval_id)
    ).one_or_none()
    if row is None:
        return None
    unit_rows = conn.execute(
        select(
            rendition_approval_units.c.ordinal,
            rendition_approval_units.c.body,
        )
        .where(rendition_approval_units.c.approval_id == approval_id)
        .order_by(rendition_approval_units.c.ordinal.asc())
    ).all()
    return RenditionApprovalRecord(
        approval_id=int(row.id),
        rendition_id=int(row.rendition_id),
        sequence=int(row.sequence),
        actor=str(row.actor),
        approved_at=str(row.approved_at),
        units=[ApprovalSnapshotUnit(ordinal=int(u.ordinal), body=str(u.body)) for u in unit_rows],
    )


def _list_approvals_for_rendition(
    conn: Connection, rendition_id: int
) -> list[RenditionApprovalRecord]:
    ids = conn.execute(
        select(rendition_approvals.c.id)
        .where(rendition_approvals.c.rendition_id == rendition_id)
        .order_by(rendition_approvals.c.sequence.asc())
    ).all()
    out: list[RenditionApprovalRecord] = []
    for r in ids:
        rec = _load_approval(conn, int(r.id))
        if rec is not None:
            out.append(rec)
    return out


def describe_content_divergence(
    current_bodies: list[str],
    snapshot_bodies: list[str],
) -> list[str]:
    """Human-readable change list when current ordered bodies ≠ snapshot.

    Pure function — unit-tested. Order is part of the artifact: same multiset in
    a different sequence is a change even if no body string was edited.
    """
    if current_bodies == snapshot_bodies:
        return []

    notes: list[str] = []
    if (
        len(current_bodies) == len(snapshot_bodies)
        and sorted(current_bodies) == sorted(snapshot_bodies)
        and current_bodies != snapshot_bodies
    ):
        notes.append("unit order changed (same bodies as a multiset, different sequence)")
        return notes

    if len(current_bodies) != len(snapshot_bodies):
        notes.append(
            f"unit count changed (cleared {len(snapshot_bodies)}, now {len(current_bodies)})"
        )

    n = max(len(current_bodies), len(snapshot_bodies))
    for i in range(n):
        if i >= len(current_bodies):
            notes.append(f"unit at position {i} was removed after clearance")
        elif i >= len(snapshot_bodies):
            notes.append(f"unit at position {i} was added after clearance")
        elif current_bodies[i] != snapshot_bodies[i]:
            notes.append(f"unit at position {i} text differs from the cleared snapshot")
    return notes


def _derive_standing(
    current_bodies: list[str],
    approval: RenditionApprovalRecord | None,
) -> tuple[bool, ApprovalInvalidation | None]:
    if approval is None:
        return False, None
    snap = [u.body for u in sorted(approval.units, key=lambda u: u.ordinal)]
    if current_bodies == snap:
        return True, None
    changes = describe_content_divergence(current_bodies, snap)
    detail = "; ".join(changes) if changes else "content diverged from cleared snapshot"
    # Tag categories for clients that switch on them.
    tags: list[str] = []
    joined = " ".join(changes).lower()
    if "order" in joined:
        tags.append("order")
    if "count" in joined or "removed" in joined or "added" in joined:
        tags.append("membership")
    if "text differs" in joined:
        tags.append("text")
    if not tags:
        tags.append("content")
    return False, ApprovalInvalidation(
        approval_id=approval.approval_id,
        changes=tags,
        detail=detail,
    )


def _load_units(conn: Connection, rendition_id: int) -> list[RenditionUnitRecord]:
    unit_rows = conn.execute(
        select(
            rendition_units.c.id,
            rendition_units.c.ordinal,
            rendition_units.c.body,
        )
        .where(rendition_units.c.rendition_id == rendition_id)
        .order_by(rendition_units.c.ordinal.asc())
    ).all()
    units: list[RenditionUnitRecord] = []
    for u in unit_rows:
        cite_rows = conn.execute(
            select(rendition_unit_claims.c.claim_id)
            .where(rendition_unit_claims.c.unit_id == int(u.id))
            .order_by(rendition_unit_claims.c.ordinal.asc())
        ).all()
        units.append(
            RenditionUnitRecord(
                unit_id=int(u.id),
                ordinal=int(u.ordinal),
                body=str(u.body),
                claim_ids=[int(c.claim_id) for c in cite_rows],
            )
        )
    return units


def _load_rendition(conn: Connection, rendition_id: int) -> RenditionRecord | None:
    row = conn.execute(
        select(
            renditions.c.id,
            renditions.c.case_id,
            renditions.c.angle_id,
            renditions.c.run_id,
            renditions.c.platform,
            renditions.c.format,
            renditions.c.status,
            renditions.c.rubric_version,
            renditions.c.created_at,
            renditions.c.current_approval_id,
        ).where(renditions.c.id == rendition_id)
    ).one_or_none()
    if row is None:
        return None

    units = _load_units(conn, rendition_id)
    bodies = [u.body for u in units]
    approvals = _list_approvals_for_rendition(conn, rendition_id)

    current_approval_id = (
        int(row.current_approval_id) if row.current_approval_id is not None else None
    )
    current_approval: RenditionApprovalRecord | None = None
    if current_approval_id is not None:
        current_approval = _load_approval(conn, current_approval_id)
        if current_approval is None and approvals:
            # Pointer stale — fall back to latest in history for derivation.
            current_approval = approvals[-1]
            current_approval_id = current_approval.approval_id
    elif approvals:
        # Pre-pointer legacy or pointer null: still derive against latest clearance.
        current_approval = approvals[-1]
        current_approval_id = current_approval.approval_id

    stands, invalidation = _derive_standing(bodies, current_approval)

    return RenditionRecord(
        rendition_id=int(row.id),
        case_id=int(row.case_id),
        angle_id=int(row.angle_id),
        run_id=int(row.run_id),
        platform=str(row.platform),
        format=str(row.format),
        status=str(row.status),
        rubric_version=str(row.rubric_version),
        created_at=str(row.created_at),
        units=units,
        current_approval_id=current_approval_id,
        approval_stands=stands,
        approval_invalidation=invalidation,
        current_approval=current_approval,
        approvals=approvals,
    )


def list_renditions_for_case(conn: Connection, case_id: int) -> list[RenditionRecord]:
    """All renditions on a case, oldest first."""
    ids = conn.execute(
        select(renditions.c.id)
        .where(renditions.c.case_id == case_id)
        .order_by(renditions.c.id.asc())
    ).all()
    out: list[RenditionRecord] = []
    for r in ids:
        rec = _load_rendition(conn, int(r.id))
        if rec is not None:
            out.append(rec)
    return out


def _eligible_claim_map(conn: Connection, angle_id: int) -> tuple[int, dict[int, ClaimRecord]]:
    """Return (case_id, claim_id → ClaimRecord) for the angle's confirmed set."""
    result = list_rendition_eligible_claims(conn, RenditionEligibleClaimsInput(angle_id=angle_id))
    return result.case_id, {c.claim_id: c for c in result.claims}


def _prepare_units(
    conn: Connection,
    *,
    case_id: int,
    angle_id: int,
    units: list[RenditionUnitInput],
    refuse_preserved: str,
) -> list[tuple[str, list[int]]]:
    """Validate units for write; return (body, claim_ids) list in order."""
    _, eligible = _eligible_claim_map(conn, angle_id)
    if not eligible:
        raise DeskRefusal(
            code="ANGLE_NO_ELIGIBLE_CLAIMS",
            what_happened=(
                f"Angle {angle_id} has no confirmed linked claims; nothing is rendition-eligible."
            ),
            what_was_preserved=refuse_preserved,
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Link and confirm claims on this angle, then retry.",
        )

    if not units:
        raise DeskRefusal(
            code="RENDITION_UNITS_EMPTY",
            what_happened="units was empty; a rendition needs at least one ordered unit.",
            what_was_preserved=refuse_preserved,
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Provide one or more units with body text and claim_ids.",
        )

    prepared: list[tuple[str, list[int]]] = []
    for idx, unit in enumerate(units):
        body = unit.body
        if not body.strip():
            raise DeskRefusal(
                code="RENDITION_UNIT_BODY_EMPTY",
                what_happened=f"Unit at index {idx} has an empty body after trimming.",
                what_was_preserved=refuse_preserved,
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Provide non-empty body text for every unit.",
            )
        claim_ids = list(unit.claim_ids or [])
        if not claim_ids:
            raise DeskRefusal(
                code="RENDITION_UNIT_CLAIMS_EMPTY",
                what_happened=(
                    f"Unit at index {idx} cites no claims. Every unit must rest on "
                    "at least one angle-eligible confirmed claim."
                ),
                what_was_preserved=refuse_preserved,
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Pass claim_ids drawn from the angle's confirmed set.",
            )
        seen: set[int] = set()
        for cid in claim_ids:
            if cid in seen:
                raise DeskRefusal(
                    code="RENDITION_UNIT_CLAIM_DUPLICATE",
                    what_happened=(f"Unit at index {idx} cites claim {cid} more than once."),
                    what_was_preserved=refuse_preserved,
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do="Cite each claim at most once per unit.",
                )
            seen.add(cid)

            if cid in eligible:
                cl = eligible[cid]
                qual = cl.qualification.strip()
                if qual and qual not in body:
                    raise DeskRefusal(
                        code="QUALIFICATION_MISSING_FROM_UNIT",
                        what_happened=(
                            f"Unit at index {idx} cites claim {cid}, which requires "
                            f"qualification language {qual!r}, but that text is not "
                            "present in the unit body."
                        ),
                        what_was_preserved=refuse_preserved,
                        what_was_not_changed="The Record is unchanged.",
                        what_you_can_do=(
                            "Include the claim's exact qualification language in the "
                            "unit body, or do not cite that claim in this unit."
                        ),
                    )
                continue

            crow = conn.execute(
                select(
                    claims.c.id,
                    claims.c.case_id,
                    claims.c.confirmation_status,
                ).where(claims.c.id == cid)
            ).one_or_none()
            if crow is None:
                raise DeskRefusal(
                    code="CLAIM_NOT_FOUND",
                    what_happened=f"Cited claim {cid} does not exist.",
                    what_was_preserved=refuse_preserved,
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do="Cite claim ids from the angle's eligible set.",
                )
            if int(crow.case_id) != case_id:
                raise DeskRefusal(
                    code="CLAIM_WRONG_CASE",
                    what_happened=(
                        f"Cited claim {cid} belongs to another case; composition "
                        "stays within the run's case."
                    ),
                    what_was_preserved=refuse_preserved,
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do="Cite claims from this case only.",
                )
            if str(crow.confirmation_status) != "confirmed":
                raise DeskRefusal(
                    code="CLAIM_UNCONFIRMED",
                    what_happened=(
                        f"Cited claim {cid} is {crow.confirmation_status!r}; "
                        "a unit may only cite confirmed claims."
                    ),
                    what_was_preserved=refuse_preserved,
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do=(
                        "Confirm the claim by linking it into this angle (or the "
                        "public question / quotation shelf), then retry."
                    ),
                )
            raise DeskRefusal(
                code="CLAIM_NOT_ON_ANGLE",
                what_happened=(
                    f"Cited claim {cid} is confirmed but not linked to angle "
                    f"{angle_id}. Eligibility is angle-scoped (D2); "
                    "composition must not widen it back to case-wide."
                ),
                what_was_preserved=refuse_preserved,
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do=(
                    "Link the claim to this angle, or cite only claims already "
                    "on the angle's confirmed set "
                    f"(eligible: {sorted(eligible.keys())})."
                ),
            )
        prepared.append((body, claim_ids))
    return prepared


def _write_units(
    conn: Connection,
    *,
    rendition_id: int,
    prepared: list[tuple[str, list[int]]],
) -> None:
    """Replace all units for a rendition with the prepared sequence."""
    existing = conn.execute(
        select(rendition_units.c.id).where(rendition_units.c.rendition_id == rendition_id)
    ).all()
    for row in existing:
        conn.execute(
            delete(rendition_unit_claims).where(rendition_unit_claims.c.unit_id == int(row.id))
        )
    conn.execute(delete(rendition_units).where(rendition_units.c.rendition_id == rendition_id))

    for ordinal, (body, claim_ids) in enumerate(prepared):
        ures = conn.execute(
            insert(rendition_units).values(
                rendition_id=rendition_id,
                ordinal=ordinal,
                body=body,
            )
        )
        upk = ures.inserted_primary_key
        if upk is None or upk[0] is None:
            raise RuntimeError("insert into rendition_units did not return a primary key")
        unit_id = int(upk[0])
        for c_ord, cid in enumerate(claim_ids):
            conn.execute(
                insert(rendition_unit_claims).values(
                    unit_id=unit_id,
                    claim_id=cid,
                    ordinal=c_ord,
                )
            )


def propose_rendition(conn: Connection, params: ProposeRenditionInput) -> ProposeRenditionResult:
    """Verify eligibility and qualification, then insert a draft rendition."""
    validate_and_refresh_claim(conn, params.run_id, params.claim_token)

    run_row = conn.execute(
        select(
            runs.c.id,
            runs.c.case_id,
            runs.c.status,
            runs.c.rubric_version,
        ).where(runs.c.id == params.run_id)
    ).one_or_none()
    if run_row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Claim a run via claim_next_run, then propose_rendition.",
        )

    run_case_id = int(run_row.case_id)
    rubric_version = str(run_row.rubric_version)

    platform = (params.platform or "").strip().lower()
    fmt = (params.format or "").strip().lower()
    if (platform, fmt) not in ALLOWED_RENDITION_PLATFORM_FORMATS:
        raise DeskRefusal(
            code="RENDITION_PLATFORM_FORMAT_UNSUPPORTED",
            what_happened=(
                f"platform={platform!r} format={fmt!r} is not supported. "
                "Destination supports x/thread only."
            ),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Pass platform='x' and format='thread'.",
        )

    angle_row = conn.execute(
        select(
            angles.c.id,
            angles.c.case_id,
            angles.c.status,
            angles.c.title,
        ).where(angles.c.id == params.angle_id)
    ).one_or_none()
    if angle_row is None:
        raise DeskRefusal(
            code="ANGLE_NOT_FOUND",
            what_happened=f"No angle exists with id {params.angle_id}.",
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Pass an existing angle_id on this case.",
        )
    if int(angle_row.case_id) != run_case_id:
        raise DeskRefusal(
            code="ANGLE_WRONG_CASE",
            what_happened=(
                f"Angle {params.angle_id} belongs to case {angle_row.case_id}, "
                f"but run {params.run_id} is on case {run_case_id}."
            ),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Compose against an angle on the run's case.",
        )
    if str(angle_row.status) != "chosen":
        raise DeskRefusal(
            code="ANGLE_NOT_CHOSEN",
            what_happened=(
                f"Angle {params.angle_id} has status {angle_row.status!r}; "
                "composition requires a chosen angle."
            ),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Operator must choose this angle before composition.",
        )

    prepared = _prepare_units(
        conn,
        case_id=run_case_id,
        angle_id=params.angle_id,
        units=params.units,
        refuse_preserved="No rendition was written.",
    )

    now = _utc_now()
    result = conn.execute(
        insert(renditions).values(
            case_id=run_case_id,
            angle_id=params.angle_id,
            run_id=params.run_id,
            platform=platform,
            format=fmt,
            status="draft",
            rubric_version=rubric_version,
            created_at=now,
            current_approval_id=None,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into renditions did not return a primary key")
    rendition_id = int(pk[0])
    _write_units(conn, rendition_id=rendition_id, prepared=prepared)

    loaded = _load_rendition(conn, rendition_id)
    if loaded is None:
        raise RuntimeError(f"rendition {rendition_id} missing immediately after insert")
    return ProposeRenditionResult(**loaded.model_dump())


def update_rendition(conn: Connection, params: UpdateRenditionInput) -> UpdateRenditionResult:
    """Human-only: replace ordered units (complete model). Approval history untouched."""
    row = conn.execute(
        select(
            renditions.c.id,
            renditions.c.case_id,
            renditions.c.angle_id,
            renditions.c.status,
        ).where(renditions.c.id == params.rendition_id)
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="RENDITION_NOT_FOUND",
            what_happened=f"No rendition exists with id {params.rendition_id}.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Pass an existing rendition_id from the case projection.",
        )
    status = str(row.status)
    if status not in _EDITABLE_STATUSES:
        raise DeskRefusal(
            code="RENDITION_NOT_EDITABLE",
            what_happened=(
                f"Rendition {params.rendition_id} has status {status!r}; "
                "only draft or cleared renditions can be edited."
            ),
            what_was_preserved="Existing units and approvals are unchanged.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Edit before publish/reject, or compose a new rendition.",
        )

    prepared = _prepare_units(
        conn,
        case_id=int(row.case_id),
        angle_id=int(row.angle_id),
        units=params.units,
        refuse_preserved="Existing units and approvals are unchanged.",
    )
    _write_units(conn, rendition_id=params.rendition_id, prepared=prepared)

    # Do not flip status back to draft and do not clear current_approval_id —
    # standing is derived; silent revert would hide the clearance history.
    loaded = _load_rendition(conn, params.rendition_id)
    if loaded is None:
        raise RuntimeError(f"rendition {params.rendition_id} missing after update")
    return UpdateRenditionResult(**loaded.model_dump())


def approve_rendition(conn: Connection, params: ApproveRenditionInput) -> ApproveRenditionResult:
    """Human-only: append a clearance snapshot of the current ordered units.

    Revalidates at the moment of clearance (not only on the last write to the
    rendition). Ticket 11 permits re-confirmation of claims: a cited claim can
    gain stricter required qualification without anyone editing the draft. A
    clearance asserts publishability under VISION §14 — every current required
    qualification must still appear in the citing unit body — so we fail closed
    against *current* claim state rather than trusting an earlier _prepare_units
    call. Same lesson as coverage staleness (D20): the material underneath can
    change without a write on this object.
    """
    row = conn.execute(
        select(
            renditions.c.id,
            renditions.c.case_id,
            renditions.c.angle_id,
            renditions.c.status,
        ).where(renditions.c.id == params.rendition_id)
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="RENDITION_NOT_FOUND",
            what_happened=f"No rendition exists with id {params.rendition_id}.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Pass an existing rendition_id from the case projection.",
        )
    status = str(row.status)
    if status not in _APPROVABLE_STATUSES:
        raise DeskRefusal(
            code="RENDITION_NOT_APPROVABLE",
            what_happened=(
                f"Rendition {params.rendition_id} has status {status!r}; "
                "only draft or cleared renditions can be cleared."
            ),
            what_was_preserved="Existing approvals are unchanged.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Clear content before publish/reject, or compose a new rendition.",
        )

    units = _load_units(conn, params.rendition_id)
    if not units:
        raise DeskRefusal(
            code="RENDITION_UNITS_EMPTY",
            what_happened="Rendition has no units; nothing to clear.",
            what_was_preserved="No approval was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Add units via update_rendition, then approve.",
        )

    # Revalidate against current claim state (eligibility, confirmation, qualifications).
    # _prepare_units names claim id and qualification text on QUALIFICATION_MISSING_FROM_UNIT.
    _prepare_units(
        conn,
        case_id=int(row.case_id),
        angle_id=int(row.angle_id),
        units=[RenditionUnitInput(body=u.body, claim_ids=list(u.claim_ids)) for u in units],
        refuse_preserved=(
            "No approval was written; existing units and prior clearances are unchanged."
        ),
    )

    max_seq = conn.execute(
        select(func.max(rendition_approvals.c.sequence)).where(
            rendition_approvals.c.rendition_id == params.rendition_id
        )
    ).scalar_one()
    next_seq = int(max_seq) + 1 if max_seq is not None else 1
    actor = (params.actor or "").strip() or "operator"
    now = _utc_now()

    ares = conn.execute(
        insert(rendition_approvals).values(
            rendition_id=params.rendition_id,
            sequence=next_seq,
            actor=actor,
            approved_at=now,
        )
    )
    apk = ares.inserted_primary_key
    if apk is None or apk[0] is None:
        raise RuntimeError("insert into rendition_approvals did not return a primary key")
    approval_id = int(apk[0])

    for u in units:
        conn.execute(
            insert(rendition_approval_units).values(
                approval_id=approval_id,
                ordinal=u.ordinal,
                body=u.body,
            )
        )

    conn.execute(
        update(renditions)
        .where(renditions.c.id == params.rendition_id)
        .values(status="cleared", current_approval_id=approval_id)
    )

    loaded = _load_rendition(conn, params.rendition_id)
    if loaded is None:
        raise RuntimeError(f"rendition {params.rendition_id} missing after approve")
    if not loaded.approval_stands:
        raise RuntimeError(
            "approval snapshot does not match current content immediately after write"
        )
    return ApproveRenditionResult(**loaded.model_dump())
