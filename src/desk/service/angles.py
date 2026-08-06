"""Angle Room and claim confirmation at use (ticket 11 / ADR 2 / D20 / D21).

Angle-start and claim-confirmation paths call assert_official_foundation_complete.
Confirmation attaches when a claim is linked to an angle, public question, or
quotation shelf entry — not at storage. Dismissed angles keep their reason forever.

VISION §7: every Angle Room item links to at least one claim. Empty angles are
drafts; choosing requires ≥1 linked confirmed claim. Public questions take claim
links with the same confirmation-at-use path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select, update

from desk.db.schema import (
    angle_claims,
    angles,
    claim_quote_bindings,
    claims,
    public_question_claims,
    public_questions,
    quotation_shelf_entries,
)
from desk.refusals import DeskRefusal
from desk.service.claims import list_claims_for_case
from desk.service.confirmation import confirm_claim_for_use
from desk.service.coverage import assert_official_foundation_complete
from desk.service.models import (
    AddQuotationShelfInput,
    AddQuotationShelfResult,
    AngleClaimLink,
    AngleRecord,
    AssertOfficialFoundationInput,
    ChooseAngleInput,
    ChooseAngleResult,
    CreateAngleInput,
    CreateAngleResult,
    CreatePublicQuestionInput,
    CreatePublicQuestionResult,
    DismissAngleInput,
    DismissAngleResult,
    LinkClaimToAngleInput,
    LinkClaimToAngleResult,
    LinkClaimToPublicQuestionInput,
    LinkClaimToPublicQuestionResult,
    PublicQuestionClaimLink,
    PublicQuestionRecord,
    QuotationShelfItem,
    RenditionEligibleClaimsInput,
    RenditionEligibleClaimsResult,
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _load_angle(conn: Connection, angle_id: int) -> AngleRecord | None:
    row = conn.execute(
        select(
            angles.c.id,
            angles.c.case_id,
            angles.c.title,
            angles.c.summary,
            angles.c.status,
            angles.c.dismissal_reason,
            angles.c.dismissed_at,
            angles.c.created_at,
            angles.c.updated_at,
        ).where(angles.c.id == angle_id)
    ).one_or_none()
    if row is None:
        return None
    links = conn.execute(
        select(
            angle_claims.c.claim_id,
            angle_claims.c.ordinal,
            angle_claims.c.linked_at,
        )
        .where(angle_claims.c.angle_id == angle_id)
        .order_by(angle_claims.c.ordinal.asc())
    ).all()
    link_recs = [
        AngleClaimLink(
            claim_id=int(r.claim_id),
            ordinal=int(r.ordinal),
            linked_at=str(r.linked_at),
        )
        for r in links
    ]
    return AngleRecord(
        angle_id=int(row.id),
        case_id=int(row.case_id),
        title=str(row.title),
        summary=str(row.summary),
        status=str(row.status),
        dismissal_reason=(None if row.dismissal_reason is None else str(row.dismissal_reason)),
        dismissed_at=None if row.dismissed_at is None else str(row.dismissed_at),
        claim_ids=[lnk.claim_id for lnk in link_recs],
        links=link_recs,
        created_at=str(row.created_at),
        updated_at=str(row.updated_at),
    )


def list_angles_for_case(conn: Connection, case_id: int) -> list[AngleRecord]:
    rows = conn.execute(
        select(angles.c.id).where(angles.c.case_id == case_id).order_by(angles.c.id.asc())
    ).all()
    out: list[AngleRecord] = []
    for r in rows:
        rec = _load_angle(conn, int(r.id))
        if rec is not None:
            out.append(rec)
    return out


def _load_public_question(conn: Connection, public_question_id: int) -> PublicQuestionRecord | None:
    row = conn.execute(
        select(
            public_questions.c.id,
            public_questions.c.case_id,
            public_questions.c.question_text,
            public_questions.c.circulating_version,
            public_questions.c.where_asked,
            public_questions.c.origin,
            public_questions.c.created_at,
        ).where(public_questions.c.id == public_question_id)
    ).one_or_none()
    if row is None:
        return None
    links = conn.execute(
        select(
            public_question_claims.c.claim_id,
            public_question_claims.c.ordinal,
            public_question_claims.c.linked_at,
        )
        .where(public_question_claims.c.public_question_id == public_question_id)
        .order_by(public_question_claims.c.ordinal.asc())
    ).all()
    link_recs = [
        PublicQuestionClaimLink(
            claim_id=int(r.claim_id),
            ordinal=int(r.ordinal),
            linked_at=str(r.linked_at),
        )
        for r in links
    ]
    return PublicQuestionRecord(
        public_question_id=int(row.id),
        case_id=int(row.case_id),
        question_text=str(row.question_text),
        circulating_version=str(row.circulating_version),
        where_asked=str(row.where_asked),
        origin=str(row.origin),
        claim_ids=[lnk.claim_id for lnk in link_recs],
        links=link_recs,
        created_at=str(row.created_at),
    )


def list_public_questions_for_case(conn: Connection, case_id: int) -> list[PublicQuestionRecord]:
    rows = conn.execute(
        select(public_questions.c.id)
        .where(public_questions.c.case_id == case_id)
        .order_by(public_questions.c.id.asc())
    ).all()
    out: list[PublicQuestionRecord] = []
    for r in rows:
        rec = _load_public_question(conn, int(r.id))
        if rec is not None:
            out.append(rec)
    return out


def quotation_shelf_for_case(conn: Connection, case_id: int) -> list[QuotationShelfItem]:
    """Operator-selected shelf entries only — not an auto-dump of quote bindings."""
    rows = conn.execute(
        select(
            quotation_shelf_entries.c.id,
            quotation_shelf_entries.c.case_id,
            quotation_shelf_entries.c.claim_id,
            quotation_shelf_entries.c.capture_id,
            quotation_shelf_entries.c.locator,
            quotation_shelf_entries.c.quoted_text,
            quotation_shelf_entries.c.speaker,
            quotation_shelf_entries.c.attribution_frame,
            quotation_shelf_entries.c.actor,
            quotation_shelf_entries.c.added_at,
            claims.c.confirmation_status,
        )
        .select_from(
            quotation_shelf_entries.join(claims, quotation_shelf_entries.c.claim_id == claims.c.id)
        )
        .where(quotation_shelf_entries.c.case_id == case_id)
        .order_by(quotation_shelf_entries.c.id.asc())
    ).all()
    return [
        QuotationShelfItem(
            shelf_entry_id=int(r.id),
            case_id=int(r.case_id),
            claim_id=int(r.claim_id),
            capture_id=int(r.capture_id),
            locator=str(r.locator),
            quoted_text=str(r.quoted_text),
            speaker=str(r.speaker),
            attribution_frame=str(r.attribution_frame),
            actor=str(r.actor),
            added_at=str(r.added_at),
            confirmation_status=str(r.confirmation_status),
        )
        for r in rows
    ]


def _link_claim_to_angle_row(
    conn: Connection,
    *,
    angle_id: int,
    case_id: int,
    claim_id: int,
    dimensions,
) -> None:
    existing = conn.execute(
        select(angle_claims.c.id)
        .where(angle_claims.c.angle_id == angle_id)
        .where(angle_claims.c.claim_id == claim_id)
    ).one_or_none()
    if existing is not None:
        raise DeskRefusal(
            code="CLAIM_ALREADY_LINKED",
            what_happened=f"Claim {claim_id} is already linked to angle {angle_id}.",
            what_was_preserved="Existing links are unchanged.",
            what_was_not_changed="No new link was written.",
            what_you_can_do="Choose a different claim or a different angle.",
        )
    confirm_claim_for_use(conn, claim_id=claim_id, case_id=case_id, dimensions=dimensions)
    status = conn.execute(
        select(claims.c.confirmation_status).where(claims.c.id == claim_id)
    ).scalar_one()
    if str(status) != "confirmed":
        raise DeskRefusal(
            code="CLAIM_NOT_CONFIRMED",
            what_happened=f"Claim {claim_id} is not confirmed after link attempt.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="Angle links unchanged.",
            what_you_can_do="Provide dimensions for unconfirmed claims.",
        )
    n = int(
        conn.execute(
            select(func.count())
            .select_from(angle_claims)
            .where(angle_claims.c.angle_id == angle_id)
        ).scalar_one()
    )
    conn.execute(
        insert(angle_claims).values(
            angle_id=angle_id,
            claim_id=claim_id,
            ordinal=n,
            linked_at=_utc_now(),
        )
    )


def create_angle(conn: Connection, params: CreateAngleInput) -> CreateAngleResult:
    """Human-only: create an angle (may be empty draft); gate on official foundation."""
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=params.case_id))
    title = params.title.strip()
    if not title:
        raise DeskRefusal(
            code="ANGLE_TITLE_EMPTY",
            what_happened="Angle title was empty after trimming.",
            what_was_preserved="Existing angles are unchanged.",
            what_was_not_changed="No angle was created.",
            what_you_can_do="Provide a non-empty title for the angle.",
        )
    now = _utc_now()
    result = conn.execute(
        insert(angles).values(
            case_id=params.case_id,
            title=title,
            summary=(params.summary or "").strip(),
            status="active",
            dismissal_reason=None,
            dismissed_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into angles did not return a primary key")
    angle_id = int(pk[0])
    for cid in params.claim_ids:
        dims = params.dimensions_by_claim_id.get(cid)
        _link_claim_to_angle_row(
            conn,
            angle_id=angle_id,
            case_id=params.case_id,
            claim_id=cid,
            dimensions=dims,
        )
    rec = _load_angle(conn, angle_id)
    assert rec is not None
    return CreateAngleResult.model_validate(rec.model_dump())


def link_claim_to_angle(conn: Connection, params: LinkClaimToAngleInput) -> LinkClaimToAngleResult:
    """Human-only: link claim; confirms unconfirmed claims; foundation gate."""
    angle = _load_angle(conn, params.angle_id)
    if angle is None:
        raise DeskRefusal(
            code="ANGLE_NOT_FOUND",
            what_happened=f"No angle exists with id {params.angle_id}.",
            what_was_preserved="Existing angles are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Create an angle first.",
        )
    if angle.status == "dismissed":
        raise DeskRefusal(
            code="ANGLE_DISMISSED",
            what_happened=f"Angle {params.angle_id} is dismissed; links cannot be added.",
            what_was_preserved="Dismissal is unchanged.",
            what_was_not_changed="No link was written.",
            what_you_can_do="Create a new angle; dismissed angles are immutable.",
        )
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=angle.case_id))
    _link_claim_to_angle_row(
        conn,
        angle_id=params.angle_id,
        case_id=angle.case_id,
        claim_id=params.claim_id,
        dimensions=params.dimensions,
    )
    conn.execute(update(angles).where(angles.c.id == params.angle_id).values(updated_at=_utc_now()))
    rec = _load_angle(conn, params.angle_id)
    assert rec is not None
    return LinkClaimToAngleResult.model_validate(rec.model_dump())


def dismiss_angle(conn: Connection, params: DismissAngleInput) -> DismissAngleResult:
    """Human-only: durable reasoned dismissal — never deleted or overwritten."""
    angle = _load_angle(conn, params.angle_id)
    if angle is None:
        raise DeskRefusal(
            code="ANGLE_NOT_FOUND",
            what_happened=f"No angle exists with id {params.angle_id}.",
            what_was_preserved="Existing angles are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Dismiss an existing angle_id.",
        )
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=angle.case_id))
    if angle.status == "dismissed":
        raise DeskRefusal(
            code="ANGLE_ALREADY_DISMISSED",
            what_happened=f"Angle {params.angle_id} is already dismissed.",
            what_was_preserved=f"Original reason: {angle.dismissal_reason!r}.",
            what_was_not_changed="Dismissal reason was not overwritten.",
            what_you_can_do="Create a new angle if you need a different line of work.",
        )
    reason = params.reason.strip()
    if not reason:
        raise DeskRefusal(
            code="DISMISSAL_REASON_EMPTY",
            what_happened="Dismissal reason was empty after trimming.",
            what_was_preserved="Angle status is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Provide a non-empty reasoned dismissal.",
        )
    now = _utc_now()
    conn.execute(
        update(angles)
        .where(angles.c.id == params.angle_id)
        .values(
            status="dismissed",
            dismissal_reason=reason,
            dismissed_at=now,
            updated_at=now,
        )
    )
    rec = _load_angle(conn, params.angle_id)
    assert rec is not None
    return DismissAngleResult.model_validate(rec.model_dump())


def choose_angle(conn: Connection, params: ChooseAngleInput) -> ChooseAngleResult:
    """Human-only: mark one angle chosen; requires ≥1 linked confirmed claim (§7)."""
    angle = _load_angle(conn, params.angle_id)
    if angle is None:
        raise DeskRefusal(
            code="ANGLE_NOT_FOUND",
            what_happened=f"No angle exists with id {params.angle_id}.",
            what_was_preserved="Existing angles are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Choose an existing active angle.",
        )
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=angle.case_id))
    if angle.status == "dismissed":
        raise DeskRefusal(
            code="ANGLE_DISMISSED",
            what_happened=f"Angle {params.angle_id} is dismissed and cannot be chosen.",
            what_was_preserved="Dismissal is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Choose a non-dismissed angle.",
        )
    if not angle.claim_ids:
        raise DeskRefusal(
            code="ANGLE_HAS_NO_CLAIMS",
            what_happened=(
                f"Angle {params.angle_id} has no linked claims. VISION §7: every "
                "Angle Room item links to at least one claim — empty angles are drafts."
            ),
            what_was_preserved="Angle remains active (un-chosen).",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Link at least one confirmed claim to this angle, then choose.",
        )
    # Links always confirm at use, so linked claims are confirmed; belt-and-braces.
    confirmed_n = int(
        conn.execute(
            select(func.count())
            .select_from(angle_claims.join(claims, angle_claims.c.claim_id == claims.c.id))
            .where(angle_claims.c.angle_id == params.angle_id)
            .where(claims.c.confirmation_status == "confirmed")
        ).scalar_one()
    )
    if confirmed_n < 1:
        raise DeskRefusal(
            code="ANGLE_HAS_NO_CONFIRMED_CLAIMS",
            what_happened=(f"Angle {params.angle_id} has no confirmed claims linked."),
            what_was_preserved="Angle remains un-chosen.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Link confirmed claims before choosing this angle.",
        )
    now = _utc_now()
    conn.execute(
        update(angles)
        .where(angles.c.case_id == angle.case_id)
        .where(angles.c.status == "chosen")
        .values(status="active", updated_at=now)
    )
    conn.execute(
        update(angles).where(angles.c.id == params.angle_id).values(status="chosen", updated_at=now)
    )
    rec = _load_angle(conn, params.angle_id)
    assert rec is not None
    return ChooseAngleResult.model_validate(rec.model_dump())


def create_public_question(
    conn: Connection, params: CreatePublicQuestionInput
) -> CreatePublicQuestionResult:
    """Human-only: record a public question (discourse observation, not a claim).

    May start with zero claims (draft). Linking claims is a separate governed path
    with confirmation-at-use. Coverage 'worked' requires ≥1 claim link.
    """
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=params.case_id))
    fields = {
        "question_text": params.question_text.strip(),
        "circulating_version": params.circulating_version.strip(),
        "where_asked": params.where_asked.strip(),
        "origin": params.origin.strip(),
    }
    for name, value in fields.items():
        if not value:
            raise DeskRefusal(
                code="PUBLIC_QUESTION_FIELD_EMPTY",
                what_happened=f"{name} was empty after trimming.",
                what_was_preserved="Existing public questions are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do=f"Provide non-empty {name}.",
            )
    now = _utc_now()
    result = conn.execute(
        insert(public_questions).values(
            case_id=params.case_id,
            created_at=now,
            **fields,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into public_questions did not return a primary key")
    pq_id = int(pk[0])
    for cid in params.claim_ids:
        dims = params.dimensions_by_claim_id.get(cid)
        _link_claim_to_public_question_row(
            conn,
            public_question_id=pq_id,
            case_id=params.case_id,
            claim_id=cid,
            dimensions=dims,
        )
    rec = _load_public_question(conn, pq_id)
    assert rec is not None
    return CreatePublicQuestionResult.model_validate(rec.model_dump())


def _link_claim_to_public_question_row(
    conn: Connection,
    *,
    public_question_id: int,
    case_id: int,
    claim_id: int,
    dimensions,
) -> None:
    existing = conn.execute(
        select(public_question_claims.c.id)
        .where(public_question_claims.c.public_question_id == public_question_id)
        .where(public_question_claims.c.claim_id == claim_id)
    ).one_or_none()
    if existing is not None:
        raise DeskRefusal(
            code="CLAIM_ALREADY_LINKED",
            what_happened=(
                f"Claim {claim_id} is already linked to public question {public_question_id}."
            ),
            what_was_preserved="Existing links are unchanged.",
            what_was_not_changed="No new link was written.",
            what_you_can_do="Choose a different claim.",
        )
    confirm_claim_for_use(conn, claim_id=claim_id, case_id=case_id, dimensions=dimensions)
    n = int(
        conn.execute(
            select(func.count())
            .select_from(public_question_claims)
            .where(public_question_claims.c.public_question_id == public_question_id)
        ).scalar_one()
    )
    conn.execute(
        insert(public_question_claims).values(
            public_question_id=public_question_id,
            claim_id=claim_id,
            ordinal=n,
            linked_at=_utc_now(),
        )
    )


def link_claim_to_public_question(
    conn: Connection, params: LinkClaimToPublicQuestionInput
) -> LinkClaimToPublicQuestionResult:
    """Human-only: link claim to public question; confirmation-at-use (VISION §7)."""
    pq = _load_public_question(conn, params.public_question_id)
    if pq is None:
        raise DeskRefusal(
            code="PUBLIC_QUESTION_NOT_FOUND",
            what_happened=f"No public question exists with id {params.public_question_id}.",
            what_was_preserved="Existing public questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Create a public question first.",
        )
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=pq.case_id))
    _link_claim_to_public_question_row(
        conn,
        public_question_id=params.public_question_id,
        case_id=pq.case_id,
        claim_id=params.claim_id,
        dimensions=params.dimensions,
    )
    rec = _load_public_question(conn, params.public_question_id)
    assert rec is not None
    return LinkClaimToPublicQuestionResult.model_validate(rec.model_dump())


def add_quotation_to_shelf(
    conn: Connection, params: AddQuotationShelfInput
) -> AddQuotationShelfResult:
    """Human-only: select a quote binding onto the shelf with speaker + frame."""
    assert_official_foundation_complete(conn, AssertOfficialFoundationInput(case_id=params.case_id))
    speaker = params.speaker.strip()
    frame = params.attribution_frame.strip()
    if not speaker:
        raise DeskRefusal(
            code="SHELF_SPEAKER_EMPTY",
            what_happened="Speaker was empty after trimming.",
            what_was_preserved="Quotation shelf is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Name who said this (or the institutional voice).",
        )
    if not frame:
        raise DeskRefusal(
            code="SHELF_ATTRIBUTION_EMPTY",
            what_happened="Attribution frame was empty after trimming.",
            what_was_preserved="Quotation shelf is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Provide how this quotation should be attributed.",
        )
    binding = conn.execute(
        select(
            claim_quote_bindings.c.claim_id,
            claim_quote_bindings.c.capture_id,
            claim_quote_bindings.c.locator,
            claim_quote_bindings.c.quoted_text,
            claims.c.case_id,
        )
        .select_from(
            claim_quote_bindings.join(claims, claim_quote_bindings.c.claim_id == claims.c.id)
        )
        .where(claim_quote_bindings.c.claim_id == params.claim_id)
        .where(claim_quote_bindings.c.capture_id == params.capture_id)
        .where(claim_quote_bindings.c.locator == params.locator)
    ).one_or_none()
    if binding is None:
        raise DeskRefusal(
            code="QUOTE_BINDING_NOT_FOUND",
            what_happened=(
                f"No quote binding on claim {params.claim_id} for capture "
                f"{params.capture_id} locator {params.locator!r}."
            ),
            what_was_preserved="Quotation shelf is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Use a capture_id/locator pair from the claim's quote_bindings.",
        )
    if int(binding.case_id) != params.case_id:
        raise DeskRefusal(
            code="CLAIM_WRONG_CASE",
            what_happened=f"Claim {params.claim_id} does not belong to case {params.case_id}.",
            what_was_preserved="Quotation shelf is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Add quotations from claims on this case only.",
        )
    if str(binding.quoted_text) != params.quoted_text:
        raise DeskRefusal(
            code="QUOTE_TEXT_MISMATCH",
            what_happened=(
                "quoted_text does not match the stored binding exactly "
                "(capture-then-cite; no fuzzy match)."
            ),
            what_was_preserved="Quotation shelf is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Pass the exact quoted_text from the claim binding.",
        )
    confirm_claim_for_use(
        conn,
        claim_id=params.claim_id,
        case_id=params.case_id,
        dimensions=params.dimensions,
    )
    now = _utc_now()
    actor = (params.actor or "").strip() or "operator"
    result = conn.execute(
        insert(quotation_shelf_entries).values(
            case_id=params.case_id,
            claim_id=params.claim_id,
            capture_id=params.capture_id,
            locator=params.locator,
            quoted_text=params.quoted_text,
            speaker=speaker,
            attribution_frame=frame,
            actor=actor,
            added_at=now,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into quotation_shelf_entries did not return a primary key")
    status = conn.execute(
        select(claims.c.confirmation_status).where(claims.c.id == params.claim_id)
    ).scalar_one()
    return AddQuotationShelfResult(
        shelf_entry_id=int(pk[0]),
        case_id=params.case_id,
        claim_id=params.claim_id,
        capture_id=params.capture_id,
        locator=params.locator,
        quoted_text=params.quoted_text,
        speaker=speaker,
        attribution_frame=frame,
        actor=actor,
        added_at=now,
        confirmation_status=str(status),
    )


def list_rendition_eligible_claims(
    conn: Connection, params: RenditionEligibleClaimsInput
) -> RenditionEligibleClaimsResult:
    """Confirmed claims linked to one angle (D2 / VISION §14) — for ticket 12."""
    angle = _load_angle(conn, params.angle_id)
    if angle is None:
        raise DeskRefusal(
            code="ANGLE_NOT_FOUND",
            what_happened=f"No angle exists with id {params.angle_id}.",
            what_was_preserved="Nothing was written.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Pass an existing angle_id.",
        )
    all_claims = {c.claim_id: c for c in list_claims_for_case(conn, angle.case_id)}
    eligible = []
    for cid in angle.claim_ids:
        cl = all_claims.get(cid)
        if cl is not None and cl.confirmation_status == "confirmed":
            eligible.append(cl)
    return RenditionEligibleClaimsResult(
        angle_id=params.angle_id,
        case_id=angle.case_id,
        claims=eligible,
    )
