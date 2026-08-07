"""propose_rendition — executor composition under a claimed run (ticket 12 / D7).

The backend never calls a model. A rendition is proposed through MCP the same
way a claim is: the executor supplies units; the service verifies eligibility
and stores the draft.

Eligibility is angle-scoped confirmed claims (ticket 11 / D2). Citing an
unconfirmed claim or a claim confirmed only on a different angle is refused.
Required qualification language on a cited claim must appear in that unit's body.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select

from desk.db.schema import (
    angles,
    claims,
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
    ClaimRecord,
    ProposeRenditionInput,
    ProposeRenditionResult,
    RenditionEligibleClaimsInput,
    RenditionRecord,
    RenditionUnitRecord,
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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
        ).where(renditions.c.id == rendition_id)
    ).one_or_none()
    if row is None:
        return None
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

    if not params.units:
        raise DeskRefusal(
            code="RENDITION_UNITS_EMPTY",
            what_happened="units was empty; a rendition needs at least one ordered unit.",
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Provide one or more units with body text and claim_ids.",
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

    _, eligible = _eligible_claim_map(conn, params.angle_id)
    if not eligible:
        raise DeskRefusal(
            code="ANGLE_NO_ELIGIBLE_CLAIMS",
            what_happened=(
                f"Angle {params.angle_id} has no confirmed linked claims; "
                "nothing is rendition-eligible."
            ),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Link and confirm claims on this angle, then retry.",
        )

    # Pre-validate every unit before any write.
    prepared: list[tuple[str, list[int]]] = []
    for idx, unit in enumerate(params.units):
        body = unit.body  # preserve internal whitespace; strip ends for empty check
        if not body.strip():
            raise DeskRefusal(
                code="RENDITION_UNIT_BODY_EMPTY",
                what_happened=f"Unit at index {idx} has an empty body after trimming.",
                what_was_preserved="No rendition was written.",
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
                what_was_preserved="No rendition was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Pass claim_ids drawn from the angle's confirmed set.",
            )
        seen: set[int] = set()
        for cid in claim_ids:
            if cid in seen:
                raise DeskRefusal(
                    code="RENDITION_UNIT_CLAIM_DUPLICATE",
                    what_happened=(f"Unit at index {idx} cites claim {cid} more than once."),
                    what_was_preserved="No rendition was written.",
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
                        what_was_preserved="No rendition was written.",
                        what_was_not_changed="The Record is unchanged.",
                        what_you_can_do=(
                            "Include the claim's exact qualification language in the "
                            "unit body, or do not cite that claim in this unit."
                        ),
                    )
                continue

            # Not eligible — distinguish unconfirmed / wrong angle / missing.
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
                    what_was_preserved="No rendition was written.",
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do="Cite claim ids from the angle's eligible set.",
                )
            if int(crow.case_id) != run_case_id:
                raise DeskRefusal(
                    code="CLAIM_WRONG_CASE",
                    what_happened=(
                        f"Cited claim {cid} belongs to another case; composition "
                        "stays within the run's case."
                    ),
                    what_was_preserved="No rendition was written.",
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
                    what_was_preserved="No rendition was written.",
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do=(
                        "Confirm the claim by linking it into this angle (or the "
                        "public question / quotation shelf), then retry."
                    ),
                )
            # Confirmed on the case but not linked to this angle.
            raise DeskRefusal(
                code="CLAIM_NOT_ON_ANGLE",
                what_happened=(
                    f"Cited claim {cid} is confirmed but not linked to angle "
                    f"{params.angle_id}. Eligibility is angle-scoped (D2); "
                    "composition must not widen it back to case-wide."
                ),
                what_was_preserved="No rendition was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do=(
                    "Link the claim to this angle, or cite only claims already "
                    "on the angle's confirmed set "
                    f"(eligible: {sorted(eligible.keys())})."
                ),
            )
        prepared.append((body, claim_ids))

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
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into renditions did not return a primary key")
    rendition_id = int(pk[0])

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

    loaded = _load_rendition(conn, rendition_id)
    if loaded is None:
        raise RuntimeError(f"rendition {rendition_id} missing immediately after insert")
    return ProposeRenditionResult(**loaded.model_dump())
