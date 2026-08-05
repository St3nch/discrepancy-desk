"""Governed Run operations — dispatch is human-only; claim is executor pull."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, func, insert, select, update

from desk.db.schema import captures, cases, claims, runs
from desk.refusals import DeskRefusal
from desk.service.lease import (
    LEASE_TTL_SECONDS,
    format_utc,
    lease_deadline,
    new_claim_token,
    reclaim_expired_leases,
    utc_now,
)
from desk.service.models import (
    ApproveRunInput,
    ApproveRunResult,
    ClaimedRunPacket,
    ClaimNextRunInput,
    ClaimNextRunResult,
    CreateRunInput,
    CreateRunResult,
    ListRunsInput,
    ListRunsResult,
    RunRecord,
)
from desk.service.run_status import (
    ACTIVE_CLAIM_STATUSES,
    PLACEHOLDER_RUBRIC_TEXT,
    PLACEHOLDER_RUBRIC_VERSION,
)

DEFAULT_CAPTURE_BUDGET = 20


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


def _row_to_run(row: object, *, captures_used: int) -> RunRecord:
    lease = getattr(row, "lease_expires_at", None)
    return RunRecord(
        run_id=int(row.id),  # type: ignore[attr-defined]
        case_id=int(row.case_id),  # type: ignore[attr-defined]
        status=row.status,  # type: ignore[attr-defined]
        question=str(row.question),  # type: ignore[attr-defined]
        scope=str(row.scope),  # type: ignore[attr-defined]
        rubric_version=str(row.rubric_version),  # type: ignore[attr-defined]
        rubric_text=str(row.rubric_text),  # type: ignore[attr-defined]
        capture_budget=int(row.capture_budget),  # type: ignore[attr-defined]
        captures_used=captures_used,
        created_at=str(row.created_at),  # type: ignore[attr-defined]
        updated_at=str(row.updated_at),  # type: ignore[attr-defined]
        lease_expires_at=str(lease) if lease is not None else None,
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
    runs.c.created_at,
    runs.c.updated_at,
    runs.c.lease_expires_at,
    runs.c.claim_token,
)


def _select_run(conn: Connection, run_id: int) -> object | None:
    return conn.execute(select(*_RUN_COLUMNS).where(runs.c.id == run_id)).one_or_none()


def _case_exists(conn: Connection, case_id: int) -> bool:
    row = conn.execute(select(cases.c.id).where(cases.c.id == case_id)).one_or_none()
    return row is not None


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
    row = _select_run(conn, run_id)
    assert row is not None
    return CreateRunResult.model_validate(_row_to_run(row, captures_used=0).model_dump())


def approve_run(conn: Connection, params: ApproveRunInput) -> ApproveRunResult:
    """Human-only: draft → approved. Makes the run claimable via pull."""
    # Evaluate leases so an expired claimed run does not look "claimed" forever.
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

    current = _row_to_run(row, captures_used=_captures_used(conn, params.run_id))
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
    updated = _select_run(conn, params.run_id)
    assert updated is not None
    return ApproveRunResult.model_validate(
        _row_to_run(updated, captures_used=_captures_used(conn, params.run_id)).model_dump()
    )


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
        runs=[_row_to_run(row, captures_used=_captures_used(conn, int(row.id))) for row in rows],
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
            claims_made=claims_count,
            is_resume=(used > 0 or claims_count > 0),
            lease_expires_at=expires,
            claim_token=token,
        )
    )
