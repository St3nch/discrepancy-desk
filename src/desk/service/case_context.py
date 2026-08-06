"""Executor-facing case context (ticket 07 / F-27).

read_case_context is the governed read of the run the claim_token holds, plus
case material. The token proves authority to continue work — not knowledge of
what the operator decided. Suspension answers and full run state are delivered
here so the executor is never blind after resume or any mid-flight event.
"""

from __future__ import annotations

from hmac import compare_digest

from sqlalchemy import Connection, select

from desk.db.schema import cases, runs
from desk.refusals import DeskRefusal
from desk.service.captures import list_capture_summaries_for_case
from desk.service.claims import list_claims_for_case
from desk.service.close import list_open_questions_for_case
from desk.service.lease import validate_claim
from desk.service.models import (
    CaseRecord,
    ExecutorHeldRun,
    ReadCaseContextInput,
    ReadCaseContextResult,
)
from desk.service.runs import (
    _RUN_COLUMNS,
    _captures_used,
    _claims_made,
    _list_suspensions,
)


def read_case_context(
    conn: Connection,
    params: ReadCaseContextInput,
) -> ReadCaseContextResult:
    """Return case material and the run held by claim_token.

    Resolves the held run by matching claim_token on a claimed or suspended
    run for the given case. Refreshes the lease when the run is claimed.
    """
    presented = (params.claim_token or "").strip()
    if not presented:
        raise DeskRefusal(
            code="RUN_CLAIM_STALE",
            what_happened="claim_token was empty; cannot identify a held run.",
            what_was_preserved="No run lease or token was changed.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Call claim_next_run and present the claim_token it returns.",
        )

    case_row = conn.execute(
        select(cases.c.id, cases.c.title, cases.c.created_at).where(
            cases.c.id == params.case_id
        )
    ).one_or_none()
    if case_row is None:
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Use the case_id from the claim packet.",
        )

    candidates = conn.execute(
        select(*_RUN_COLUMNS)
        .where(runs.c.case_id == params.case_id)
        .where(runs.c.status.in_(("claimed", "suspended")))
        .where(runs.c.claim_token.is_not(None))
    ).all()

    held = None
    for row in candidates:
        stored = row.claim_token
        if stored is not None and compare_digest(presented, str(stored)):
            held = row
            break

    if held is None:
        raise DeskRefusal(
            code="RUN_CLAIM_STALE",
            what_happened=(
                f"No claimed or suspended run on case {params.case_id} matches "
                "this claim_token."
            ),
            what_was_preserved="No run lease or token was changed.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do=(
                "Call claim_next_run again and use the new claim_token; "
                "do not retry with a stale token."
            ),
        )

    run_id = int(held.id)
    # Shared claim checks + lease refresh when claimed; suspended keeps token only.
    validate_claim(
        conn,
        run_id,
        presented,
        refresh=True,
        allow_suspended=True,
    )

    # Re-read after possible lease refresh.
    refreshed = conn.execute(
        select(*_RUN_COLUMNS).where(runs.c.id == run_id)
    ).one()
    suspensions = _list_suspensions(conn, run_id)
    current = suspensions[-1] if suspensions else None
    lease = refreshed.lease_expires_at

    held_run = ExecutorHeldRun(
        run_id=run_id,
        case_id=int(refreshed.case_id),
        status=refreshed.status,
        question=str(refreshed.question),
        scope=str(refreshed.scope),
        rubric_version=str(refreshed.rubric_version),
        rubric_text=str(refreshed.rubric_text),
        capture_budget=int(refreshed.capture_budget),
        captures_used=_captures_used(conn, run_id),
        coverage_dimension=(
            None
            if refreshed.coverage_dimension is None
            else str(refreshed.coverage_dimension)
        ),
        claims_made=_claims_made(conn, run_id),
        lease_expires_at=str(lease) if lease is not None else None,
        suspensions=suspensions,
        current_suspension=current,
    )

    return ReadCaseContextResult(
        case=CaseRecord(
            case_id=int(case_row.id),
            title=str(case_row.title),
            created_at=str(case_row.created_at),
        ),
        held_run=held_run,
        claims=list_claims_for_case(conn, params.case_id),
        captures=list_capture_summaries_for_case(conn, params.case_id),
        open_questions=list_open_questions_for_case(conn, params.case_id),
        angles=[],
        renditions=[],
    )
