"""propose_claim — five-step fail-closed verification (ADR 9).

D21 / F-24: if any cited claim is unknown or living_private, the inference must
also be (categorical non-publishable set — no severity ladder). Early refusal at
proposal; binding check is at confirmation against authoritative values.

Soft reclassification among publishable publication-risk categories (e.g.
deceased → institution) is permitted deliberately (D21) — that is operator
judgement, not a hole. Do not reintroduce a severity ladder to "fix" it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select, update

from desk.db.schema import (
    captures,
    claim_inference_citations,
    claim_quote_bindings,
    claims,
    document_versions,
    elements,
    runs,
)
from desk.refusals import DeskRefusal
from desk.service.confirmation import assert_inference_publication_risk_allowed
from desk.service.evidence import (
    CERTAINTY,
    CORROBORATION,
    INFERENCE_SOURCE_BASIS,
    POSTURE,
    PUBLICATION_RISK,
    QUALIFICATION_REQUIRED_POSTURES,
    SOURCE_BASIS,
)
from desk.service.lease import validate_and_refresh_claim
from desk.service.models import (
    ClaimRecord,
    EvidenceDimensions,
    ProposeClaimInput,
    ProposeClaimResult,
    QuoteBindingInput,
    QuoteBindingRecord,
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize_bindings(params: ProposeClaimInput) -> list[QuoteBindingInput]:
    bindings: list[QuoteBindingInput] = []
    if params.quote_bindings:
        bindings.extend(params.quote_bindings)
    if (
        params.capture_id is not None
        or params.locator is not None
        or params.quoted_text is not None
    ):
        if params.capture_id is None or params.locator is None or params.quoted_text is None:
            raise DeskRefusal(
                code="QUOTE_BINDING_INCOMPLETE",
                what_happened=(
                    "Single-quote path requires capture_id, locator, and quoted_text together."
                ),
                what_was_preserved="No claim was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Provide all three fields, or use quote_bindings.",
            )
        bindings.append(
            QuoteBindingInput(
                capture_id=params.capture_id,
                locator=params.locator,
                quoted_text=params.quoted_text,
            )
        )
    return bindings


def _validate_dimensions(dims: EvidenceDimensions) -> None:
    checks = (
        ("source_basis", dims.source_basis, SOURCE_BASIS),
        ("corroboration", dims.corroboration, CORROBORATION),
        ("certainty", dims.certainty, CERTAINTY),
        ("posture", dims.posture, POSTURE),
        ("publication_risk", dims.publication_risk, PUBLICATION_RISK),
    )
    for name, value, allowed in checks:
        if not value or not str(value).strip():
            raise DeskRefusal(
                code="DIMENSION_INVALID",
                what_happened=f"Evidence dimension {name!r} is missing or empty.",
                what_was_preserved="No claim was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do=f"Provide a valid {name} from the VISION §11 vocabulary.",
            )
        if value not in allowed:
            raise DeskRefusal(
                code="DIMENSION_INVALID",
                what_happened=(f"Evidence dimension {name}={value!r} is not a valid enum value."),
                what_was_preserved="No claim was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do=(
                    f"Use one of the allowed {name} values; see CONTEXT.md / VISION §11."
                ),
            )


# e/{ordinal} — whole element; e/{ordinal}/r/{start}-{end} — char range in element (F-22).
_LOCATOR_FULL = re.compile(r"^e/(\d+)$")
_LOCATOR_REGION = re.compile(r"^e/(\d+)/r/(\d+)-(\d+)$")


def _resolve_quotation_surface(conn: Connection, capture_id: int, locator: str) -> str:
    """Resolve locator to the exact quotation surface string (F-13 / F-22).

    - ``e/N`` → full ``elements.text`` for that ordinal
    - ``e/N/r/START-END`` → ``elements.text[START:END]`` (Python slice; END exclusive)

    Verification compares quoted_text with exact equality to this surface — never
    fuzzy, never raw Vault bytes.
    """
    m_region = _LOCATOR_REGION.match(locator)
    m_full = _LOCATOR_FULL.match(locator)
    if m_region:
        ordinal = int(m_region.group(1))
        start = int(m_region.group(2))
        end = int(m_region.group(3))
        element_locator = f"e/{ordinal}"
    elif m_full:
        ordinal = int(m_full.group(1))
        start = None
        end = None
        element_locator = f"e/{ordinal}"
    else:
        raise DeskRefusal(
            code="LOCATOR_UNRESOLVED",
            what_happened=(
                f"Locator {locator!r} is not a valid form "
                f"(expected e/{{n}} or e/{{n}}/r/{{start}}-{{end}})."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Use e/{{ordinal}} for a full element or "
                "e/{{ordinal}}/r/{{start}}-{{end}} for a character range inside it."
            ),
        )

    dv = conn.execute(
        select(document_versions.c.id)
        .where(document_versions.c.capture_id == capture_id)
        .order_by(document_versions.c.version_number.desc())
        .limit(1)
    ).one_or_none()
    if dv is None:
        raise DeskRefusal(
            code="LOCATOR_UNRESOLVED",
            what_happened=(
                f"Capture {capture_id} has no document_version; locator {locator!r} cannot resolve."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Re-capture the URL or use a capture that has been parsed.",
        )
    row = conn.execute(
        select(elements.c.text).where(
            elements.c.document_version_id == int(dv.id),
            elements.c.locator == element_locator,
        )
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="LOCATOR_UNRESOLVED",
            what_happened=(
                f"Locator {locator!r} does not resolve inside capture {capture_id} "
                f"(no element {element_locator!r})."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=("Use a locator from capture_url / read_capture for this capture."),
        )
    element_text = str(row.text)
    if start is None or end is None:
        return element_text
    if not (0 <= start < end <= len(element_text)):
        raise DeskRefusal(
            code="LOCATOR_UNRESOLVED",
            what_happened=(
                f"Region {start}-{end} is out of range for element {element_locator!r} "
                f"(length {len(element_text)}) on capture {capture_id}."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Choose start/end within the element text (end exclusive, like a slice)."
            ),
        )
    return element_text[start:end]


def _verify_quote_binding(
    conn: Connection,
    *,
    case_id: int,
    binding: QuoteBindingInput,
) -> None:
    """Steps 1–3 for one capture/locator/quote triple."""
    cap = conn.execute(
        select(captures.c.id, captures.c.case_id).where(captures.c.id == binding.capture_id)
    ).one_or_none()
    if cap is None:
        raise DeskRefusal(
            code="CAPTURE_NOT_FOUND",
            what_happened=f"No capture exists with id {binding.capture_id}.",
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Call capture_url first, then propose_claim with that capture_id.",
        )
    # Lead captures have case_id null until attach; refuse citing them until then.
    if cap.case_id is None or int(cap.case_id) != case_id:
        owned = (
            "no case (unattached lead material)" if cap.case_id is None else str(int(cap.case_id))
        )
        raise DeskRefusal(
            code="CAPTURE_WRONG_CASE",
            what_happened=(
                f"Capture {binding.capture_id} belongs to case {owned}, "
                f"not the run's case {case_id}."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Cite a capture that belongs to this run's case. "
                "Unattached lead material must be attached by the operator first."
            ),
        )

    surface = _resolve_quotation_surface(conn, binding.capture_id, binding.locator)
    # Exact equality against the resolved surface — never fuzzy/normalised.
    if binding.quoted_text != surface:
        raise DeskRefusal(
            code="QUOTE_MISMATCH",
            what_happened=(
                f"quoted_text does not exactly match the quotation surface at locator "
                f"{binding.locator!r} on capture {binding.capture_id}."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Copy quoted_text exactly from the element text (e/n) or from the "
                "character range e/n/r/start-end (end exclusive); not from an "
                "independent page read."
            ),
        )


def propose_claim(conn: Connection, params: ProposeClaimInput) -> ProposeClaimResult:
    """Verify fail-closed in order, then insert unconfirmed claim (ADR 2, ADR 9)."""
    proposition = params.proposition.strip()
    if not proposition:
        raise DeskRefusal(
            code="PROPOSITION_EMPTY",
            what_happened="proposition was empty after trimming.",
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Provide a non-empty proposition.",
        )

    validate_and_refresh_claim(conn, params.run_id, params.claim_token)

    run_row = conn.execute(
        select(
            runs.c.id,
            runs.c.case_id,
            runs.c.status,
            runs.c.question,
            runs.c.rubric_version,
        ).where(runs.c.id == params.run_id)
    ).one_or_none()
    if run_row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Claim a run via claim_next_run, then propose_claim.",
        )

    case_id = int(run_row.case_id)
    source_run_question = str(run_row.question)
    dims = params.dimensions
    is_inference = dims.source_basis == INFERENCE_SOURCE_BASIS
    bindings = _normalize_bindings(params)
    cited = list(params.cited_claim_ids or [])

    if is_inference:
        if not cited:
            raise DeskRefusal(
                code="INFERENCE_CITATIONS_REQUIRED",
                what_happened=(
                    "source_basis desk_inference requires cited_claim_ids (claims, not captures)."
                ),
                what_was_preserved="No claim was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Pass one or more claim ids this inference reasons over.",
            )
        if bindings:
            raise DeskRefusal(
                code="INFERENCE_MUST_NOT_QUOTE_CAPTURE",
                what_happened=(
                    "desk_inference claims cite other claims only; capture quote "
                    "bindings are not allowed on this path."
                ),
                what_was_preserved="No claim was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Omit capture/locator/quote; use cited_claim_ids only.",
            )
        cited_risks: list[str] = []
        for cid in cited:
            crow = conn.execute(
                select(claims.c.id, claims.c.case_id, claims.c.publication_risk).where(
                    claims.c.id == cid
                )
            ).one_or_none()
            if crow is None:
                raise DeskRefusal(
                    code="CITED_CLAIM_NOT_FOUND",
                    what_happened=f"Cited claim {cid} does not exist.",
                    what_was_preserved="No claim was written.",
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do="Cite claim ids that already exist in this case.",
                )
            if int(crow.case_id) != case_id:
                raise DeskRefusal(
                    code="CITED_CLAIM_WRONG_CASE",
                    what_happened=(
                        f"Cited claim {cid} belongs to another case; inference "
                        "must stay within the run's case."
                    ),
                    what_was_preserved="No claim was written.",
                    what_was_not_changed="The Record is unchanged.",
                    what_you_can_do="Cite claims from this case only.",
                )
            cited_risks.append(str(crow.publication_risk))
        # D21 early refusal against proposed values; binding check is at confirmation.
        assert_inference_publication_risk_allowed(
            inference_risk=dims.publication_risk,
            cited_risks=cited_risks,
        )
    else:
        if not bindings:
            raise DeskRefusal(
                code="QUOTE_BINDING_REQUIRED",
                what_happened=(
                    "Non-inference claims require at least one capture/locator/quoted_text binding."
                ),
                what_was_preserved="No claim was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do=(
                    "Provide capture_id, locator, and quoted_text (or quote_bindings)."
                ),
            )
        # Steps 1–3 for each binding, in order (fail closed on first failure).
        for binding in bindings:
            _verify_quote_binding(conn, case_id=case_id, binding=binding)

    # Step 4 — all six dimensions present and valid (qualification is separate text).
    _validate_dimensions(dims)

    # Step 5 — qualification non-empty for allegation / participant_account.
    qualification = params.qualification  # preserve intentional whitespace? strip ends
    qual_stripped = qualification.strip()
    if dims.posture in QUALIFICATION_REQUIRED_POSTURES and not qual_stripped:
        raise DeskRefusal(
            code="QUALIFICATION_REQUIRED",
            what_happened=(f"Posture {dims.posture!r} requires non-empty qualification language."),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Provide the exact qualification language that must accompany any use "
                "of this claim."
            ),
        )

    now = _utc_now()
    stored_qualification = (
        qual_stripped if dims.posture in QUALIFICATION_REQUIRED_POSTURES else qualification
    )
    result = conn.execute(
        insert(claims).values(
            case_id=case_id,
            run_id=params.run_id,
            proposition=proposition,
            confirmation_status="unconfirmed",
            source_basis=dims.source_basis,
            corroboration=dims.corroboration,
            certainty=dims.certainty,
            posture=dims.posture,
            qualification=stored_qualification,
            publication_risk=dims.publication_risk,
            rubric_version=str(run_row.rubric_version),
            created_at=now,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into claims did not return a primary key")
    claim_id = int(pk[0])

    quote_records: list[QuoteBindingRecord] = []
    for ordinal, binding in enumerate(bindings):
        conn.execute(
            insert(claim_quote_bindings).values(
                claim_id=claim_id,
                capture_id=binding.capture_id,
                locator=binding.locator,
                quoted_text=binding.quoted_text,
                ordinal=ordinal,
            )
        )
        # Promotion by use: capture becomes cited when a claim binds to it.
        conn.execute(
            update(captures).where(captures.c.id == binding.capture_id).values(status="cited")
        )
        quote_records.append(
            QuoteBindingRecord(
                capture_id=binding.capture_id,
                locator=binding.locator,
                quoted_text=binding.quoted_text,
                ordinal=ordinal,
            )
        )

    for ordinal, cited_id in enumerate(cited):
        conn.execute(
            insert(claim_inference_citations).values(
                claim_id=claim_id,
                cited_claim_id=cited_id,
                ordinal=ordinal,
            )
        )

    return ProposeClaimResult(
        claim_id=claim_id,
        case_id=case_id,
        run_id=params.run_id,
        proposition=proposition,
        confirmation_status="unconfirmed",
        source_basis=dims.source_basis,
        corroboration=dims.corroboration,
        certainty=dims.certainty,
        posture=dims.posture,
        qualification=stored_qualification,
        publication_risk=dims.publication_risk,
        rubric_version=str(run_row.rubric_version),
        quote_bindings=quote_records,
        cited_claim_ids=cited,
        created_at=now,
        confirmed_at=None,
        source_run_question=source_run_question,
    )


def list_claims_for_case(conn: Connection, case_id: int) -> list[ClaimRecord]:
    """All claims for a case, oldest first (unconfirmed included — loud in UI)."""
    rows = conn.execute(
        select(
            claims.c.id,
            claims.c.case_id,
            claims.c.run_id,
            claims.c.proposition,
            claims.c.confirmation_status,
            claims.c.source_basis,
            claims.c.corroboration,
            claims.c.certainty,
            claims.c.posture,
            claims.c.qualification,
            claims.c.publication_risk,
            claims.c.rubric_version,
            claims.c.created_at,
            claims.c.confirmed_at,
            runs.c.question.label("source_run_question"),
        )
        .select_from(claims.join(runs, claims.c.run_id == runs.c.id))
        .where(claims.c.case_id == case_id)
        .order_by(claims.c.id.asc())
    ).all()
    out: list[ClaimRecord] = []
    for row in rows:
        claim_id = int(row.id)
        qrows = conn.execute(
            select(
                claim_quote_bindings.c.capture_id,
                claim_quote_bindings.c.locator,
                claim_quote_bindings.c.quoted_text,
                claim_quote_bindings.c.ordinal,
            )
            .where(claim_quote_bindings.c.claim_id == claim_id)
            .order_by(claim_quote_bindings.c.ordinal.asc())
        ).all()
        irows = conn.execute(
            select(claim_inference_citations.c.cited_claim_id)
            .where(claim_inference_citations.c.claim_id == claim_id)
            .order_by(claim_inference_citations.c.ordinal.asc())
        ).all()
        confirmed_at = row.confirmed_at
        out.append(
            ClaimRecord(
                claim_id=claim_id,
                case_id=int(row.case_id),
                run_id=int(row.run_id),
                source_run_question=str(row.source_run_question),
                proposition=str(row.proposition),
                confirmation_status=str(row.confirmation_status),
                source_basis=str(row.source_basis),
                corroboration=str(row.corroboration),
                certainty=str(row.certainty),
                posture=str(row.posture),
                qualification=str(row.qualification),
                publication_risk=str(row.publication_risk),
                rubric_version=str(row.rubric_version),
                quote_bindings=[
                    QuoteBindingRecord(
                        capture_id=int(q.capture_id),
                        locator=str(q.locator),
                        quoted_text=str(q.quoted_text),
                        ordinal=int(q.ordinal),
                    )
                    for q in qrows
                ],
                cited_claim_ids=[int(i.cited_claim_id) for i in irows],
                created_at=str(row.created_at),
                confirmed_at=None if confirmed_at is None else str(confirmed_at),
            )
        )
    return out


def list_claims_for_run(conn: Connection, run_id: int) -> list[ClaimRecord]:
    """Claims introduced by one run, oldest first."""
    rows = conn.execute(
        select(
            claims.c.id,
            claims.c.case_id,
            claims.c.run_id,
            claims.c.proposition,
            claims.c.confirmation_status,
            claims.c.source_basis,
            claims.c.corroboration,
            claims.c.certainty,
            claims.c.posture,
            claims.c.qualification,
            claims.c.publication_risk,
            claims.c.rubric_version,
            claims.c.created_at,
            claims.c.confirmed_at,
            runs.c.question.label("source_run_question"),
        )
        .select_from(claims.join(runs, claims.c.run_id == runs.c.id))
        .where(claims.c.run_id == run_id)
        .order_by(claims.c.id.asc())
    ).all()
    out: list[ClaimRecord] = []
    for row in rows:
        claim_id = int(row.id)
        qrows = conn.execute(
            select(
                claim_quote_bindings.c.capture_id,
                claim_quote_bindings.c.locator,
                claim_quote_bindings.c.quoted_text,
                claim_quote_bindings.c.ordinal,
            )
            .where(claim_quote_bindings.c.claim_id == claim_id)
            .order_by(claim_quote_bindings.c.ordinal.asc())
        ).all()
        irows = conn.execute(
            select(claim_inference_citations.c.cited_claim_id)
            .where(claim_inference_citations.c.claim_id == claim_id)
            .order_by(claim_inference_citations.c.ordinal.asc())
        ).all()
        confirmed_at = row.confirmed_at
        out.append(
            ClaimRecord(
                claim_id=claim_id,
                case_id=int(row.case_id),
                run_id=int(row.run_id),
                source_run_question=str(row.source_run_question),
                proposition=str(row.proposition),
                confirmation_status=str(row.confirmation_status),
                source_basis=str(row.source_basis),
                corroboration=str(row.corroboration),
                certainty=str(row.certainty),
                posture=str(row.posture),
                qualification=str(row.qualification),
                publication_risk=str(row.publication_risk),
                rubric_version=str(row.rubric_version),
                quote_bindings=[
                    QuoteBindingRecord(
                        capture_id=int(q.capture_id),
                        locator=str(q.locator),
                        quoted_text=str(q.quoted_text),
                        ordinal=int(q.ordinal),
                    )
                    for q in qrows
                ],
                cited_claim_ids=[int(i.cited_claim_id) for i in irows],
                created_at=str(row.created_at),
                confirmed_at=None if confirmed_at is None else str(confirmed_at),
            )
        )
    return out
