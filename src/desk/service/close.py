"""Run close, open-question agenda, and examined captures (ticket 08 / D13).

close_run (MCP): executor proposes agenda + low-confidence areas; run → complete;
explicit examined_capture_ids mark only those uncited captures as examined (F-32).

Agenda decisions (HTTP): operator approves / rejects / replaces each proposal.
Operator may also create open questions with no prior proposal (F-31 / D5).
"""

from __future__ import annotations

from sqlalchemy import Connection, func, insert, select, update

from desk.db.schema import captures, open_questions, run_low_confidence, runs
from desk.refusals import DeskRefusal
from desk.service.claims import list_claims_for_run
from desk.service.lease import format_utc, utc_now, validate_and_refresh_claim
from desk.service.models import (
    OPEN_QUESTION_DISPOSITIONS,
    CaptureCloseRecord,
    CloseRunInput,
    CloseRunResult,
    CreateOperatorOpenQuestionInput,
    CreateOperatorOpenQuestionResult,
    DecideOpenQuestionInput,
    DecideOpenQuestionResult,
    GetRunCloseInput,
    GetRunCloseResult,
    OpenQuestionRecord,
)
from desk.service.runs import _load_run_result

_OPERATOR_DECISIONS = frozenset({"approve", "reject", "replace"})

# Marker rationale for operator-originated rows (no executor proposal).
_OPERATOR_AUTHORED_RATIONALE = "Operator-authored (not proposed by the executor)."


def _utc_now() -> str:
    return format_utc(utc_now())


def _row_to_open_question(row: object) -> OpenQuestionRecord:
    return OpenQuestionRecord(
        open_question_id=int(row.id),  # type: ignore[attr-defined]
        case_id=int(row.case_id),  # type: ignore[attr-defined]
        introduced_by_run_id=int(row.introduced_by_run_id),  # type: ignore[attr-defined]
        source_run_question=str(row.source_run_question),  # type: ignore[attr-defined]
        ordinal=int(row.ordinal),  # type: ignore[attr-defined]
        proposed_text=str(row.proposed_text),  # type: ignore[attr-defined]
        rationale=str(row.rationale),  # type: ignore[attr-defined]
        proposed_scope=str(row.proposed_scope),  # type: ignore[attr-defined]
        agenda_decision=str(row.agenda_decision),  # type: ignore[attr-defined]
        disposition=(
            str(row.disposition) if getattr(row, "disposition", None) is not None else None
        ),
        settled_text=(
            str(row.settled_text) if getattr(row, "settled_text", None) is not None else None
        ),
        settled_scope=(
            str(row.settled_scope) if getattr(row, "settled_scope", None) is not None else None
        ),
        created_at=str(row.created_at),  # type: ignore[attr-defined]
        decided_at=(
            str(row.decided_at) if getattr(row, "decided_at", None) is not None else None
        ),
    )


_OQ_COLUMNS = (
    open_questions.c.id,
    open_questions.c.case_id,
    open_questions.c.introduced_by_run_id,
    open_questions.c.source_run_question,
    open_questions.c.ordinal,
    open_questions.c.proposed_text,
    open_questions.c.rationale,
    open_questions.c.proposed_scope,
    open_questions.c.agenda_decision,
    open_questions.c.disposition,
    open_questions.c.settled_text,
    open_questions.c.settled_scope,
    open_questions.c.created_at,
    open_questions.c.decided_at,
)


def list_open_questions_for_case(conn: Connection, case_id: int) -> list[OpenQuestionRecord]:
    rows = conn.execute(
        select(*_OQ_COLUMNS)
        .where(open_questions.c.case_id == case_id)
        .order_by(open_questions.c.id.asc())
    ).all()
    return [_row_to_open_question(r) for r in rows]


def list_open_questions_for_run(conn: Connection, run_id: int) -> list[OpenQuestionRecord]:
    rows = conn.execute(
        select(*_OQ_COLUMNS)
        .where(open_questions.c.introduced_by_run_id == run_id)
        .order_by(open_questions.c.ordinal.asc())
    ).all()
    return [_row_to_open_question(r) for r in rows]


def list_low_confidence_for_run(conn: Connection, run_id: int) -> list[str]:
    rows = conn.execute(
        select(run_low_confidence.c.statement)
        .where(run_low_confidence.c.run_id == run_id)
        .order_by(run_low_confidence.c.ordinal.asc())
    ).all()
    return [str(r.statement) for r in rows]


def list_captures_for_run(conn: Connection, run_id: int) -> list[CaptureCloseRecord]:
    rows = conn.execute(
        select(
            captures.c.id,
            captures.c.run_id,
            captures.c.url,
            captures.c.status,
            captures.c.created_at,
        )
        .where(captures.c.run_id == run_id)
        .order_by(captures.c.id.asc())
    ).all()
    return [
        CaptureCloseRecord(
            capture_id=int(r.id),
            run_id=int(r.run_id),
            url=str(r.url),
            status=str(r.status),
            created_at=str(r.created_at),
        )
        for r in rows
    ]


def _mark_reported_examined(
    conn: Connection,
    run_id: int,
    capture_ids: list[int],
) -> int:
    """Mark only executor-reported uncited captures as examined (F-32).

    Each id must belong to this run and be unexamined. Cited stays cited —
    reporting a cited capture is a refusal. Omitted uncited captures stay
    unexamined: nobody confirmed looking.
    """
    # Preserve order; ignore accidental duplicates in the list.
    seen: set[int] = set()
    ordered: list[int] = []
    for raw_id in capture_ids:
        cid = int(raw_id)
        if cid in seen:
            continue
        seen.add(cid)
        ordered.append(cid)

    marked = 0
    for cid in ordered:
        row = conn.execute(
            select(captures.c.id, captures.c.run_id, captures.c.status).where(
                captures.c.id == cid
            )
        ).one_or_none()
        if row is None:
            raise DeskRefusal(
                code="CAPTURE_NOT_FOUND",
                what_happened=f"No capture exists with id {cid}.",
                what_was_preserved="The run was not closed; no capture statuses changed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Pass capture ids from this run's capture_url results.",
            )
        if int(row.run_id) != run_id:
            raise DeskRefusal(
                code="CAPTURE_WRONG_RUN",
                what_happened=(
                    f"Capture {cid} belongs to run {int(row.run_id)}, not run {run_id}."
                ),
                what_was_preserved="The run was not closed; no capture statuses changed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Report only captures made under this claim.",
            )
        status = str(row.status)
        if status == "cited":
            raise DeskRefusal(
                code="EXAMINED_CAPTURE_ALREADY_CITED",
                what_happened=(
                    f"Capture {cid} is already cited by a claim; it cannot be "
                    "reported as examined-with-nothing-claimed."
                ),
                what_was_preserved="The run was not closed; no capture statuses changed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Omit cited captures from examined_capture_ids.",
            )
        if status == "examined":
            # Idempotent if already examined (should not happen mid-run, but fail open
            # would be wrong — leave as examined without double-counting).
            continue
        if status != "unexamined":
            raise DeskRefusal(
                code="CAPTURE_STATUS_INVALID",
                what_happened=(
                    f"Capture {cid} has status {status!r}; only unexamined "
                    "captures can be reported as examined at close."
                ),
                what_was_preserved="The run was not closed; no capture statuses changed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Report only unexamined, uncited captures.",
            )
        result = conn.execute(
            update(captures)
            .where(captures.c.id == cid)
            .where(captures.c.run_id == run_id)
            .where(captures.c.status == "unexamined")
            .values(status="examined")
        )
        if result.rowcount != 1:
            raise DeskRefusal(
                code="CAPTURE_STATUS_INVALID",
                what_happened=f"Could not mark capture {cid} examined (status changed).",
                what_was_preserved="The run was not closed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Retry close_run with a fresh view of capture statuses.",
            )
        marked += 1
    return marked


def close_run(conn: Connection, params: CloseRunInput) -> CloseRunResult:
    """Executor: claimed → complete with agenda + low-confidence + examined marks."""
    validate_and_refresh_claim(conn, params.run_id, params.claim_token)

    run_row = conn.execute(
        select(
            runs.c.id,
            runs.c.case_id,
            runs.c.status,
            runs.c.question,
            runs.c.claim_token,
        ).where(runs.c.id == params.run_id)
    ).one_or_none()
    if run_row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Claim a run via claim_next_run, then close_run.",
        )
    if str(run_row.status) != "claimed":
        raise DeskRefusal(
            code="RUN_NOT_CLAIMED",
            what_happened=(
                f"Run {params.run_id} is in status {run_row.status!r}; "
                "only a claimed run can be closed."
            ),
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Run status was not set to complete.",
            what_you_can_do="Close only while the claim is active (not suspended).",
        )

    now = _utc_now()
    case_id = int(run_row.case_id)
    source_run_question = str(run_row.question)
    agenda: list[OpenQuestionRecord] = []

    for ordinal, prop in enumerate(params.proposed_questions, start=1):
        text = prop.text.strip()
        rationale = prop.rationale.strip()
        scope = prop.proposed_scope.strip()
        if not text:
            raise DeskRefusal(
                code="OPEN_QUESTION_TEXT_EMPTY",
                what_happened=f"Proposed open question #{ordinal} has empty text.",
                what_was_preserved="The run was not closed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Provide non-empty text for each proposed open question.",
            )
        if not rationale:
            raise DeskRefusal(
                code="OPEN_QUESTION_RATIONALE_EMPTY",
                what_happened=f"Proposed open question #{ordinal} has empty rationale.",
                what_was_preserved="The run was not closed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="State why this question is worth pursuing.",
            )
        if not scope:
            raise DeskRefusal(
                code="OPEN_QUESTION_SCOPE_EMPTY",
                what_happened=f"Proposed open question #{ordinal} has empty proposed_scope.",
                what_was_preserved="The run was not closed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Propose a bounded scope for the question.",
            )
        ins = conn.execute(
            insert(open_questions).values(
                case_id=case_id,
                introduced_by_run_id=params.run_id,
                source_run_question=source_run_question,
                ordinal=ordinal,
                proposed_text=text,
                rationale=rationale,
                proposed_scope=scope,
                agenda_decision="pending",
                disposition=None,
                settled_text=None,
                settled_scope=None,
                created_at=now,
                decided_at=None,
            )
        )
        pk = ins.inserted_primary_key
        if pk is None or pk[0] is None:
            raise RuntimeError("insert into open_questions did not return a primary key")
        oq_id = int(pk[0])
        row = conn.execute(
            select(*_OQ_COLUMNS).where(open_questions.c.id == oq_id)
        ).one()
        agenda.append(_row_to_open_question(row))

    low_conf: list[str] = []
    for ordinal, raw in enumerate(params.low_confidence_areas, start=1):
        statement = raw.strip()
        if not statement:
            raise DeskRefusal(
                code="LOW_CONFIDENCE_EMPTY",
                what_happened=f"Low-confidence area #{ordinal} was empty after trimming.",
                what_was_preserved="The run was not closed.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Omit empty entries or provide a non-empty statement.",
            )
        conn.execute(
            insert(run_low_confidence).values(
                run_id=params.run_id,
                ordinal=ordinal,
                statement=statement,
            )
        )
        low_conf.append(statement)

    examined = _mark_reported_examined(
        conn, params.run_id, list(params.examined_capture_ids)
    )

    presented = params.claim_token.strip()
    result = conn.execute(
        update(runs)
        .where(runs.c.id == params.run_id)
        .where(runs.c.status == "claimed")
        .where(runs.c.claim_token == presented)
        .values(
            status="complete",
            updated_at=now,
            lease_expires_at=None,
            claim_token=None,
        )
    )
    if result.rowcount != 1:
        raise DeskRefusal(
            code="RUN_CLAIM_STALE",
            what_happened=f"Could not close run {params.run_id}; claim is no longer active.",
            what_was_preserved="Partial work is intact.",
            what_was_not_changed="Run status was not set to complete.",
            what_you_can_do="Call claim_next_run again if the run was reclaimed.",
        )

    captures_count = int(
        conn.execute(
            select(func.count()).select_from(captures).where(captures.c.run_id == params.run_id)
        ).scalar_one()
    )
    claims_count = len(list_claims_for_run(conn, params.run_id))
    run = _load_run_result(conn, params.run_id)
    return CloseRunResult(
        run=run,
        agenda=agenda,
        captures_count=captures_count,
        claims_count=claims_count,
        captures_marked_examined=examined,
        low_confidence_areas=low_conf,
    )


def decide_open_question(
    conn: Connection,
    params: DecideOpenQuestionInput,
) -> DecideOpenQuestionResult:
    """Human-only: approve / reject / replace a pending open-question proposal."""
    decision = params.decision.strip().lower()
    if decision not in _OPERATOR_DECISIONS:
        raise DeskRefusal(
            code="AGENDA_DECISION_INVALID",
            what_happened=(
                f"decision must be one of approve, reject, replace (got {params.decision!r})."
            ),
            what_was_preserved="Open questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Retry with decision approve, reject, or replace.",
        )

    row = conn.execute(
        select(*_OQ_COLUMNS).where(open_questions.c.id == params.open_question_id)
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="OPEN_QUESTION_NOT_FOUND",
            what_happened=f"No open question exists with id {params.open_question_id}.",
            what_was_preserved="Existing open questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List the run-close agenda and use a valid open_question_id.",
        )
    if str(row.agenda_decision) != "pending":
        raise DeskRefusal(
            code="OPEN_QUESTION_ALREADY_DECIDED",
            what_happened=(
                f"Open question {params.open_question_id} is already "
                f"{row.agenda_decision!r}."
            ),
            what_was_preserved="The prior decision stands.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Only pending agenda items can be decided.",
        )

    now = _utc_now()
    disposition: str | None = None
    settled_text: str | None = None
    settled_scope: str | None = None
    agenda_decision: str

    if decision == "reject":
        agenda_decision = "rejected"
        # Reject does not set disposition — the proposal is not kept as an open question.
    elif decision == "approve":
        agenda_decision = "approved"
        disp = (params.disposition or "").strip()
        if disp not in OPEN_QUESTION_DISPOSITIONS:
            raise DeskRefusal(
                code="DISPOSITION_INVALID",
                what_happened=(
                    "approve requires disposition one of: "
                    + ", ".join(sorted(OPEN_QUESTION_DISPOSITIONS))
                ),
                what_was_preserved="Open questions are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do=(
                    "Choose unresolved-likely-permanent, "
                    "unresolved-awaiting-external-development, or not-yet-worked."
                ),
            )
        disposition = disp
        text = (params.text if params.text is not None else str(row.proposed_text)).strip()
        scope = (params.scope if params.scope is not None else str(row.proposed_scope)).strip()
        if not text or not scope:
            raise DeskRefusal(
                code="OPEN_QUESTION_SETTLED_EMPTY",
                what_happened="Approved open question text and scope must be non-empty.",
                what_was_preserved="Open questions are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Provide non-empty text and scope, or omit to keep the proposal.",
            )
        settled_text = text
        settled_scope = scope
    else:  # replace
        agenda_decision = "replaced"
        disp = (params.disposition or "").strip()
        if disp not in OPEN_QUESTION_DISPOSITIONS:
            raise DeskRefusal(
                code="DISPOSITION_INVALID",
                what_happened=(
                    "replace requires disposition one of: "
                    + ", ".join(sorted(OPEN_QUESTION_DISPOSITIONS))
                ),
                what_was_preserved="Open questions are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do=(
                    "Choose unresolved-likely-permanent, "
                    "unresolved-awaiting-external-development, or not-yet-worked."
                ),
            )
        disposition = disp
        text = (params.text or "").strip()
        scope = (params.scope or "").strip()
        if not text or not scope:
            raise DeskRefusal(
                code="OPEN_QUESTION_SETTLED_EMPTY",
                what_happened="replace requires non-empty text and scope for the replacement.",
                what_was_preserved="Open questions are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do="Write your own question text and scope.",
            )
        settled_text = text
        settled_scope = scope

    result = conn.execute(
        update(open_questions)
        .where(open_questions.c.id == params.open_question_id)
        .where(open_questions.c.agenda_decision == "pending")
        .values(
            agenda_decision=agenda_decision,
            disposition=disposition,
            settled_text=settled_text,
            settled_scope=settled_scope,
            decided_at=now,
        )
    )
    if result.rowcount != 1:
        raise DeskRefusal(
            code="OPEN_QUESTION_ALREADY_DECIDED",
            what_happened=f"Open question {params.open_question_id} was decided concurrently.",
            what_was_preserved="Existing decisions stand.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Reload the agenda.",
        )

    updated = conn.execute(
        select(*_OQ_COLUMNS).where(open_questions.c.id == params.open_question_id)
    ).one()
    return DecideOpenQuestionResult.model_validate(
        _row_to_open_question(updated).model_dump()
    )


def get_run_close(conn: Connection, params: GetRunCloseInput) -> GetRunCloseResult:
    """Human-facing run-close projection in D13 order."""
    run_row = conn.execute(
        select(runs.c.id, runs.c.status).where(runs.c.id == params.run_id)
    ).one_or_none()
    if run_row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List runs for the case and open a complete run.",
        )
    if str(run_row.status) != "complete":
        raise DeskRefusal(
            code="RUN_NOT_COMPLETE",
            what_happened=(
                f"Run {params.run_id} is in status {run_row.status!r}; "
                "run-close view is for complete runs."
            ),
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Close the run via the executor first (close_run).",
        )

    run = _load_run_result(conn, params.run_id)
    agenda = list_open_questions_for_run(conn, params.run_id)
    claims = list_claims_for_run(conn, params.run_id)
    caps = list_captures_for_run(conn, params.run_id)
    return GetRunCloseResult(
        run=run,
        agenda=agenda,
        captures_count=len(caps),
        claims_count=len(claims),
        low_confidence_areas=list_low_confidence_for_run(conn, params.run_id),
        claims=claims,
        captures=caps,
    )


def create_operator_open_question(
    conn: Connection,
    params: CreateOperatorOpenQuestionInput,
) -> CreateOperatorOpenQuestionResult:
    """Human-only: write an open question on a completed run with no prior proposal (F-31).

    D5: the operator may write his own. The executor proposes the agenda; it does
    not define the space of possible agendas. Works when the proposed list is empty.
    """
    text = params.text.strip()
    scope = params.scope.strip()
    disposition = (params.disposition or "").strip()
    if not text:
        raise DeskRefusal(
            code="OPEN_QUESTION_TEXT_EMPTY",
            what_happened="Operator open-question text was empty after trimming.",
            what_was_preserved="Existing open questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Provide a non-empty research question.",
        )
    if not scope:
        raise DeskRefusal(
            code="OPEN_QUESTION_SCOPE_EMPTY",
            what_happened="Operator open-question scope was empty after trimming.",
            what_was_preserved="Existing open questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Provide a bounded scope for the question.",
        )
    if disposition not in OPEN_QUESTION_DISPOSITIONS:
        raise DeskRefusal(
            code="DISPOSITION_INVALID",
            what_happened=(
                "Operator open question requires disposition one of: "
                + ", ".join(sorted(OPEN_QUESTION_DISPOSITIONS))
            ),
            what_was_preserved="Existing open questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do=(
                "Choose unresolved-likely-permanent, "
                "unresolved-awaiting-external-development, or not-yet-worked."
            ),
        )

    run_row = conn.execute(
        select(
            runs.c.id,
            runs.c.case_id,
            runs.c.status,
            runs.c.question,
        ).where(runs.c.id == params.run_id)
    ).one_or_none()
    if run_row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Author open questions against a completed run.",
        )
    if str(run_row.status) != "complete":
        raise DeskRefusal(
            code="RUN_NOT_COMPLETE",
            what_happened=(
                f"Run {params.run_id} is in status {run_row.status!r}; "
                "operator-authored open questions attach to complete runs only."
            ),
            what_was_preserved="Existing open questions are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Wait until the run is closed, then add your question.",
        )

    now = _utc_now()
    max_ord = conn.execute(
        select(func.max(open_questions.c.ordinal)).where(
            open_questions.c.introduced_by_run_id == params.run_id
        )
    ).scalar_one()
    ordinal = int(max_ord or 0) + 1

    ins = conn.execute(
        insert(open_questions).values(
            case_id=int(run_row.case_id),
            introduced_by_run_id=params.run_id,
            source_run_question=str(run_row.question),
            ordinal=ordinal,
            proposed_text=text,
            rationale=_OPERATOR_AUTHORED_RATIONALE,
            proposed_scope=scope,
            agenda_decision="approved",
            disposition=disposition,
            settled_text=text,
            settled_scope=scope,
            created_at=now,
            decided_at=now,
        )
    )
    pk = ins.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into open_questions did not return a primary key")
    oq_id = int(pk[0])
    row = conn.execute(select(*_OQ_COLUMNS).where(open_questions.c.id == oq_id)).one()
    return CreateOperatorOpenQuestionResult.model_validate(
        _row_to_open_question(row).model_dump()
    )
