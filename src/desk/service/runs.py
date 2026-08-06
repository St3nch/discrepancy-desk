"""Governed Run operations — dispatch is human-only; claim is executor pull.

Ticket 07: suspend_run (MCP), answer_suspended_run / cancel_run (HTTP).

While suspended the run holds no lease (waiting is not abandonment) but keeps
claim_token so the same claim instance continues after the operator answers.

F-26: cancel_run is the escape hatch when a suspension (or any open run) must
die without an answer — human-only, clears lease and token, preserves work.

F-28: each suspend is a durable run_suspensions row; runs keep a projection of
the latest for list rendering only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, func, insert, select, update

from desk.db.schema import captures, cases, claims, run_suspensions, runs
from desk.refusals import DeskRefusal
from desk.service.lease import (
    LEASE_TTL_SECONDS,
    format_utc,
    lease_deadline,
    new_claim_token,
    reclaim_expired_leases,
    utc_now,
    validate_claim,
)
from desk.service.models import (
    INSTANCE_VS_CLASS_NOTICE,
    AnswerSuspendedRunInput,
    AnswerSuspendedRunResult,
    ApproveRunInput,
    ApproveRunResult,
    CancelRunInput,
    CancelRunResult,
    ClaimedRunPacket,
    ClaimNextRunInput,
    ClaimNextRunResult,
    CreateRunInput,
    CreateRunResult,
    ListRunsInput,
    ListRunsResult,
    RunRecord,
    SuspendRunInput,
    SuspendRunResult,
    SuspensionRecord,
)
from desk.service.run_status import (
    ACTIVE_CLAIM_STATUSES,
    PLACEHOLDER_RUBRIC_TEXT,
    PLACEHOLDER_RUBRIC_VERSION,
)

DEFAULT_CAPTURE_BUDGET = 20

# Statuses from which a human may cancel (F-26). Terminal statuses refuse.
_CANCELLABLE_STATUSES = frozenset({"draft", "approved", "claimed", "suspended"})


def _utc_now() -> str:
    return format_utc(utc_now())


def _captures_used(conn: Connection, run_id: int) -> int:
    value = conn.execute(
        select(func.count()).select_from(captures).where(captures.c.run_id == run_id)
    ).scalar_one()
    return int(value)


def _claims_made(conn: Connection, run_id: int) -> int:
    value = conn.execute(
        select(func.count()).select_from(claims).where(claims.c.run_id == run_id)
    ).scalar_one()
    return int(value)


def _opt_str(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _list_suspensions(conn: Connection, run_id: int) -> list[SuspensionRecord]:
    rows = conn.execute(
        select(
            run_suspensions.c.id,
            run_suspensions.c.run_id,
            run_suspensions.c.ordinal,
            run_suspensions.c.question,
            run_suspensions.c.uncertainty,
            run_suspensions.c.default_action,
            run_suspensions.c.suspended_at,
            run_suspensions.c.human_answer,
            run_suspensions.c.answered_at,
        )
        .where(run_suspensions.c.run_id == run_id)
        .order_by(run_suspensions.c.ordinal.asc())
    ).all()
    return [
        SuspensionRecord(
            suspension_id=int(r.id),
            run_id=int(r.run_id),
            ordinal=int(r.ordinal),
            question=str(r.question),
            uncertainty=str(r.uncertainty),
            default_action=str(r.default_action),
            suspended_at=str(r.suspended_at),
            human_answer=_opt_str(r.human_answer),
            answered_at=_opt_str(r.answered_at),
        )
        for r in rows
    ]


def _row_to_run(
    conn: Connection,
    row: object,
    *,
    captures_used: int,
) -> RunRecord:
    lease = getattr(row, "lease_expires_at", None)
    status = row.status  # type: ignore[attr-defined]
    run_id = int(row.id)  # type: ignore[attr-defined]
    return RunRecord(
        run_id=run_id,
        case_id=int(row.case_id),  # type: ignore[attr-defined]
        status=status,
        question=str(row.question),  # type: ignore[attr-defined]
        scope=str(row.scope),  # type: ignore[attr-defined]
        rubric_version=str(row.rubric_version),  # type: ignore[attr-defined]
        rubric_text=str(row.rubric_text),  # type: ignore[attr-defined]
        capture_budget=int(row.capture_budget),  # type: ignore[attr-defined]
        captures_used=captures_used,
        coverage_dimension=(
            None
            if getattr(row, "coverage_dimension", None) is None
            else str(row.coverage_dimension)  # type: ignore[attr-defined]
        ),
        created_at=str(row.created_at),  # type: ignore[attr-defined]
        updated_at=str(row.updated_at),  # type: ignore[attr-defined]
        lease_expires_at=str(lease) if lease is not None else None,
        suspension_question=_opt_str(getattr(row, "suspension_question", None)),
        suspension_uncertainty=_opt_str(getattr(row, "suspension_uncertainty", None)),
        suspension_default_action=_opt_str(getattr(row, "suspension_default_action", None)),
        suspended_at=_opt_str(getattr(row, "suspended_at", None)),
        human_answer=_opt_str(getattr(row, "human_answer", None)),
        answered_at=_opt_str(getattr(row, "answered_at", None)),
        suspensions=_list_suspensions(conn, run_id),
        instance_vs_class_notice=(INSTANCE_VS_CLASS_NOTICE if str(status) == "suspended" else None),
    )


_RUN_COLUMNS = (
    runs.c.id,
    runs.c.case_id,
    runs.c.status,
    runs.c.question,
    runs.c.scope,
    runs.c.rubric_version,
    runs.c.rubric_text,
    runs.c.capture_budget,
    runs.c.coverage_dimension,
    runs.c.created_at,
    runs.c.updated_at,
    runs.c.lease_expires_at,
    runs.c.claim_token,
    runs.c.suspension_question,
    runs.c.suspension_uncertainty,
    runs.c.suspension_default_action,
    runs.c.suspended_at,
    runs.c.human_answer,
    runs.c.answered_at,
)


def _select_run(conn: Connection, run_id: int) -> object | None:
    return conn.execute(select(*_RUN_COLUMNS).where(runs.c.id == run_id)).one_or_none()


def _case_exists(conn: Connection, case_id: int) -> bool:
    row = conn.execute(select(cases.c.id).where(cases.c.id == case_id)).one_or_none()
    return row is not None


def _load_run_result(conn: Connection, run_id: int) -> RunRecord:
    row = _select_run(conn, run_id)
    assert row is not None
    return _row_to_run(conn, row, captures_used=_captures_used(conn, run_id))


def create_run(conn: Connection, params: CreateRunInput) -> CreateRunResult:
    """Human-only: create a run in `draft`. Does not make it claimable."""
    if not _case_exists(conn, params.case_id):
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="No run was created.",
            what_you_can_do="Create a case first, then dispatch a run against it.",
        )

    question = params.question.strip()
    if not question:
        raise DeskRefusal(
            code="RUN_QUESTION_EMPTY",
            what_happened="Run question was empty after trimming whitespace.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="No run was created.",
            what_you_can_do="Retry with an explicit research question.",
        )

    scope = params.scope.strip()
    if not scope:
        raise DeskRefusal(
            code="RUN_SCOPE_EMPTY",
            what_happened="Run scope was empty after trimming whitespace.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="No run was created.",
            what_you_can_do="Retry with a bounded scope for the run.",
        )

    rubric_version = (params.rubric_version or PLACEHOLDER_RUBRIC_VERSION).strip()
    rubric_text = (params.rubric_text or PLACEHOLDER_RUBRIC_TEXT).strip()
    if not rubric_version or not rubric_text:
        raise DeskRefusal(
            code="RUN_RUBRIC_EMPTY",
            what_happened="Rubric version or text was empty after trimming.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="No run was created.",
            what_you_can_do="Provide non-empty rubric fields, or omit them for the placeholder.",
        )

    budget = params.capture_budget if params.capture_budget is not None else DEFAULT_CAPTURE_BUDGET
    if budget < 1:
        raise DeskRefusal(
            code="RUN_BUDGET_INVALID",
            what_happened=f"capture_budget must be at least 1 (got {budget}).",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="No run was created.",
            what_you_can_do="Retry with a positive capture_budget.",
        )

    from desk.service.coverage import COVERAGE_STAGE_IDS

    coverage_dimension = params.coverage_dimension.strip()
    if coverage_dimension not in COVERAGE_STAGE_IDS:
        raise DeskRefusal(
            code="COVERAGE_STAGE_INVALID",
            what_happened=(
                f"coverage_dimension {coverage_dimension!r} is not recognised. "
                f"Use one of: {sorted(COVERAGE_STAGE_IDS)}."
            ),
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="No run was created.",
            what_you_can_do="Set coverage_dimension to one of the six coverage stages.",
        )

    now = _utc_now()
    result = conn.execute(
        insert(runs).values(
            case_id=params.case_id,
            status="draft",
            question=question,
            scope=scope,
            rubric_version=rubric_version,
            rubric_text=rubric_text,
            capture_budget=budget,
            coverage_dimension=coverage_dimension,
            created_at=now,
            updated_at=now,
            lease_expires_at=None,
            claim_token=None,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into runs did not return a primary key")
    run_id = int(pk[0])
    return CreateRunResult.model_validate(_load_run_result(conn, run_id).model_dump())


def approve_run(conn: Connection, params: ApproveRunInput) -> ApproveRunResult:
    """Human-only: draft → approved. Makes the run claimable via pull."""
    reclaim_expired_leases(conn)

    row = _select_run(conn, params.run_id)
    if row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List runs for the case and approve an existing draft run_id.",
        )

    current = _row_to_run(conn, row, captures_used=_captures_used(conn, params.run_id))
    if current.status != "draft":
        raise DeskRefusal(
            code="RUN_NOT_DRAFT",
            what_happened=(f"Run {params.run_id} is in status {current.status!r}, not 'draft'."),
            what_was_preserved="The run was not re-approved or re-queued.",
            what_was_not_changed=f"Run status remains {current.status!r}.",
            what_you_can_do="Only draft runs can be approved. Create a new run if needed.",
        )

    blocking = conn.execute(
        select(runs.c.id, runs.c.status)
        .where(runs.c.case_id == current.case_id)
        .where(runs.c.status.in_(tuple(ACTIVE_CLAIM_STATUSES)))
        .where(runs.c.id != current.run_id)
    ).first()
    if blocking is not None:
        raise DeskRefusal(
            code="RUN_CASE_BUSY",
            what_happened=(
                f"Case {current.case_id} already has run {int(blocking.id)} "
                f"in status {blocking.status!r}."
            ),
            what_was_preserved="This draft was not approved.",
            what_was_not_changed="Run status remains 'draft'.",
            what_you_can_do=(
                "Wait until the active run is complete, abandoned, or cancelled "
                "before approving another for this case."
            ),
        )

    now = _utc_now()
    conn.execute(
        update(runs)
        .where(runs.c.id == params.run_id)
        .values(
            status="approved",
            updated_at=now,
            lease_expires_at=None,
            claim_token=None,
        )
    )
    return ApproveRunResult.model_validate(_load_run_result(conn, params.run_id).model_dump())


def list_runs(conn: Connection, params: ListRunsInput) -> ListRunsResult:
    """List runs for a case, oldest first. Human-facing projection."""
    reclaim_expired_leases(conn)

    if not _case_exists(conn, params.case_id):
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Create a case first, then list its runs.",
        )

    rows = conn.execute(
        select(*_RUN_COLUMNS).where(runs.c.case_id == params.case_id).order_by(runs.c.id.asc())
    ).all()
    return ListRunsResult(
        case_id=params.case_id,
        runs=[
            _row_to_run(conn, row, captures_used=_captures_used(conn, int(row.id))) for row in rows
        ],
    )


def claim_next_run(
    conn: Connection,
    params: ClaimNextRunInput,
    *,
    now: datetime | None = None,
    lease_ttl_seconds: int = LEASE_TTL_SECONDS,
) -> ClaimNextRunResult:
    """Executor pull: oldest approved run → claimed. No executor identity (ADR 8).

    Evaluates expired leases first (claimed → approved; partial work kept).
    Idle (no approved run) returns run=None — not a DeskRefusal.

    The packet includes captures_used / claims_made / is_resume so a reclaimer
    knows it is continuing prior work, not starting fresh.
    """
    del params
    base = now or utc_now()
    reclaim_expired_leases(conn, now=base)

    row = conn.execute(
        select(*_RUN_COLUMNS).where(runs.c.status == "approved").order_by(runs.c.id.asc()).limit(1)
    ).one_or_none()

    if row is None:
        return ClaimNextRunResult(run=None)

    run_id = int(row.id)
    now_s = format_utc(base)
    expires = lease_deadline(base, ttl_seconds=lease_ttl_seconds)
    token = new_claim_token()
    result = conn.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .where(runs.c.status == "approved")
        .values(
            status="claimed",
            updated_at=now_s,
            lease_expires_at=expires,
            claim_token=token,
        )
    )
    if result.rowcount != 1:
        return ClaimNextRunResult(run=None)

    used = _captures_used(conn, run_id)
    claims_count = _claims_made(conn, run_id)
    suspensions = _list_suspensions(conn, run_id)
    human_answer = _opt_str(getattr(row, "human_answer", None))
    suspension_question = _opt_str(getattr(row, "suspension_question", None))
    is_resume = used > 0 or claims_count > 0 or len(suspensions) > 0
    return ClaimNextRunResult(
        run=ClaimedRunPacket(
            run_id=run_id,
            case_id=int(row.case_id),
            status="claimed",
            question=str(row.question),
            scope=str(row.scope),
            rubric_version=str(row.rubric_version),
            rubric_text=str(row.rubric_text),
            capture_budget=int(row.capture_budget),
            captures_used=used,
            coverage_dimension=(
                None if row.coverage_dimension is None else str(row.coverage_dimension)
            ),
            claims_made=claims_count,
            is_resume=is_resume,
            lease_expires_at=expires,
            claim_token=token,
            suspension_question=suspension_question,
            suspension_uncertainty=_opt_str(getattr(row, "suspension_uncertainty", None)),
            suspension_default_action=_opt_str(getattr(row, "suspension_default_action", None)),
            human_answer=human_answer,
            suspensions=suspensions,
        )
    )


def suspend_run(conn: Connection, params: SuspendRunInput) -> SuspendRunResult:
    """Executor: claimed → suspended. Appends a durable suspension instance (F-28).

    Clears the lease so the wait is not treated as abandonment, but keeps
    claim_token so the same claim instance can continue after the answer.
    Work tools refuse while suspended (status is not claimed).
    """
    # Validate only — do not refresh a lease we are about to clear.
    validate_claim(conn, params.run_id, params.claim_token, refresh=False)

    question = params.question.strip()
    if not question:
        raise DeskRefusal(
            code="SUSPEND_QUESTION_EMPTY",
            what_happened="Suspension question was empty after trimming whitespace.",
            what_was_preserved="The run remains claimed with its current lease.",
            what_was_not_changed="Run status remains 'claimed'.",
            what_you_can_do="Retry with an explicit question for the operator.",
        )

    uncertainty = params.uncertainty.strip()
    if not uncertainty:
        raise DeskRefusal(
            code="SUSPEND_UNCERTAINTY_EMPTY",
            what_happened="Suspension uncertainty was empty after trimming whitespace.",
            what_was_preserved="The run remains claimed with its current lease.",
            what_was_not_changed="Run status remains 'claimed'.",
            what_you_can_do=("State what the executor is uncertain between (the alternatives)."),
        )

    default_action = params.default_action.strip()
    if not default_action:
        raise DeskRefusal(
            code="SUSPEND_DEFAULT_ACTION_EMPTY",
            what_happened="Default action was empty after trimming whitespace.",
            what_was_preserved="The run remains claimed with its current lease.",
            what_was_not_changed="Run status remains 'claimed'.",
            what_you_can_do="State what the executor would do by default if unanswered.",
        )

    presented = params.claim_token.strip()
    now = _utc_now()

    # Next ordinal for this run (1-based). Prior rows are never overwritten.
    max_ord = conn.execute(
        select(func.max(run_suspensions.c.ordinal)).where(run_suspensions.c.run_id == params.run_id)
    ).scalar_one()
    ordinal = int(max_ord or 0) + 1

    # Refuse a second open suspension (should not happen if status is claimed).
    open_row = conn.execute(
        select(run_suspensions.c.id)
        .where(run_suspensions.c.run_id == params.run_id)
        .where(run_suspensions.c.answered_at.is_(None))
    ).first()
    if open_row is not None:
        raise DeskRefusal(
            code="SUSPEND_ALREADY_OPEN",
            what_happened=(
                f"Run {params.run_id} already has an unanswered suspension (id {int(open_row.id)})."
            ),
            what_was_preserved="Existing suspension instances are unchanged.",
            what_was_not_changed="No new suspension was written; run status unchanged.",
            what_you_can_do="Wait for the operator to answer, or cancel the run.",
        )

    ins = conn.execute(
        insert(run_suspensions).values(
            run_id=params.run_id,
            ordinal=ordinal,
            question=question,
            uncertainty=uncertainty,
            default_action=default_action,
            suspended_at=now,
            human_answer=None,
            answered_at=None,
        )
    )
    pk = ins.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into run_suspensions did not return a primary key")

    # Atomic status flip + projection update. History lives in run_suspensions.
    result = conn.execute(
        update(runs)
        .where(runs.c.id == params.run_id)
        .where(runs.c.status == "claimed")
        .where(runs.c.claim_token == presented)
        .values(
            status="suspended",
            updated_at=now,
            lease_expires_at=None,
            suspension_question=question,
            suspension_uncertainty=uncertainty,
            suspension_default_action=default_action,
            suspended_at=now,
            human_answer=None,
            answered_at=None,
        )
    )
    if result.rowcount != 1:
        raise DeskRefusal(
            code="RUN_CLAIM_STALE",
            what_happened=(f"Could not suspend run {params.run_id}; claim is no longer active."),
            what_was_preserved="Partial work is intact.",
            what_was_not_changed="Run status was not set to suspended.",
            what_you_can_do=(
                "Call claim_next_run again and use the new claim_token; "
                "do not retry with the old token."
            ),
        )

    return SuspendRunResult.model_validate(_load_run_result(conn, params.run_id).model_dump())


def answer_suspended_run(
    conn: Connection,
    params: AnswerSuspendedRunInput,
    *,
    now: datetime | None = None,
    lease_ttl_seconds: int = LEASE_TTL_SECONDS,
) -> AnswerSuspendedRunResult:
    """Human-only: answer the open suspension instance; suspended → claimed.

    Writes the answer onto the durable open suspension row, refreshes the run
    projection, and restores a lease with the same claim_token.
    """
    answer = params.answer.strip()
    if not answer:
        raise DeskRefusal(
            code="SUSPEND_ANSWER_EMPTY",
            what_happened="Operator answer was empty after trimming whitespace.",
            what_was_preserved="The run remains suspended awaiting an answer.",
            what_was_not_changed="Run status remains 'suspended'.",
            what_you_can_do="Retry with a non-empty answer for the executor.",
        )

    row = _select_run(conn, params.run_id)
    if row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List runs for the case and answer an existing suspended run.",
        )

    if str(row.status) != "suspended":  # type: ignore[attr-defined]
        raise DeskRefusal(
            code="RUN_NOT_SUSPENDED",
            what_happened=(
                f"Run {params.run_id} is in status {row.status!r}, not 'suspended'."  # type: ignore[attr-defined]
            ),
            what_was_preserved="The run was not re-claimed or re-answered.",
            what_was_not_changed=f"Run status remains {row.status!r}.",  # type: ignore[attr-defined]
            what_you_can_do="Only a suspended run can receive an operator answer.",
        )

    open_suspension = conn.execute(
        select(run_suspensions.c.id)
        .where(run_suspensions.c.run_id == params.run_id)
        .where(run_suspensions.c.answered_at.is_(None))
        .order_by(run_suspensions.c.ordinal.desc())
        .limit(1)
    ).one_or_none()
    if open_suspension is None:
        raise DeskRefusal(
            code="SUSPEND_NO_OPEN",
            what_happened=(f"Run {params.run_id} is suspended but has no open suspension row."),
            what_was_preserved="Existing suspension history is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Cancel the run or inspect the database; this is inconsistent state.",
        )

    base = now or utc_now()
    now_s = format_utc(base)
    expires = lease_deadline(base, ttl_seconds=lease_ttl_seconds)
    suspension_id = int(open_suspension.id)

    ans = conn.execute(
        update(run_suspensions)
        .where(run_suspensions.c.id == suspension_id)
        .where(run_suspensions.c.answered_at.is_(None))
        .values(human_answer=answer, answered_at=now_s)
    )
    if ans.rowcount != 1:
        raise DeskRefusal(
            code="SUSPEND_NO_OPEN",
            what_happened=f"Open suspension {suspension_id} was answered concurrently.",
            what_was_preserved="Existing suspension history is unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Reload the case and check whether the run is still suspended.",
        )

    result = conn.execute(
        update(runs)
        .where(runs.c.id == params.run_id)
        .where(runs.c.status == "suspended")
        .values(
            status="claimed",
            updated_at=now_s,
            lease_expires_at=expires,
            human_answer=answer,
            answered_at=now_s,
        )
    )
    if result.rowcount != 1:
        raise DeskRefusal(
            code="RUN_NOT_SUSPENDED",
            what_happened=(f"Could not resume run {params.run_id}; it is no longer suspended."),
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Reload the case and answer only if status is still suspended.",
        )

    return AnswerSuspendedRunResult.model_validate(
        _load_run_result(conn, params.run_id).model_dump()
    )


def cancel_run(conn: Connection, params: CancelRunInput) -> CancelRunResult:
    """Human-only: move a run to cancelled (F-26).

    Allowed from draft, approved, claimed, or suspended. Clears lease and
    claim_token. Captures and claims (and suspension history) are preserved.
    Capture status (unexamined / examined / cited) is deliberately untouched —
    cancel is not a close judgement about what was looked at; only close_run
    may mark examined, and only for ids the executor explicitly reports (F-32).
    Not reachable from MCP — an executor cannot abandon its own work this way.
    """
    reclaim_expired_leases(conn)

    row = _select_run(conn, params.run_id)
    if row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List runs and cancel an existing cancellable run_id.",
        )

    status = str(row.status)  # type: ignore[attr-defined]
    if status not in _CANCELLABLE_STATUSES:
        raise DeskRefusal(
            code="RUN_NOT_CANCELLABLE",
            what_happened=(
                f"Run {params.run_id} is in status {status!r}; only draft, "
                "approved, claimed, or suspended runs can be cancelled."
            ),
            what_was_preserved="The run was not cancelled.",
            what_was_not_changed=f"Run status remains {status!r}.",
            what_you_can_do="Leave complete/cancelled/abandoned runs as they are.",
        )

    now = _utc_now()
    result = conn.execute(
        update(runs)
        .where(runs.c.id == params.run_id)
        .where(runs.c.status.in_(tuple(_CANCELLABLE_STATUSES)))
        .values(
            status="cancelled",
            updated_at=now,
            lease_expires_at=None,
            claim_token=None,
        )
    )
    if result.rowcount != 1:
        raise DeskRefusal(
            code="RUN_NOT_CANCELLABLE",
            what_happened=f"Could not cancel run {params.run_id}; status changed concurrently.",
            what_was_preserved="Existing cases and runs are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Reload the case and try again if still cancellable.",
        )

    return CancelRunResult.model_validate(_load_run_result(conn, params.run_id).model_dump())
