"""Governed Case operations — human-only (API transport)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select

from desk.db.schema import cases
from desk.refusals import DeskRefusal
from desk.service.captures import list_capture_summaries_for_case
from desk.service.claims import list_claims_for_case
from desk.service.close import list_open_questions_for_case
from desk.service.coverage import derive_case_coverage
from desk.service.models import (
    CaseRecord,
    CreateCaseInput,
    CreateCaseResult,
    GetCaseInput,
    GetCaseResult,
    ListCasesInput,
    ListCasesResult,
    ListRunsInput,
)
from desk.service.runs import list_runs


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _row_to_case(row: object) -> CaseRecord:
    return CaseRecord(
        case_id=int(row.id),  # type: ignore[attr-defined]
        title=str(row.title),  # type: ignore[attr-defined]
        created_at=str(row.created_at),  # type: ignore[attr-defined]
    )


def create_case(conn: Connection, params: CreateCaseInput) -> CreateCaseResult:
    """Create a Case with a title. No complete/closed state exists."""
    title = params.title.strip()
    if not title:
        raise DeskRefusal(
            code="CASE_TITLE_EMPTY",
            what_happened="Case title was empty after trimming whitespace.",
            what_was_preserved="Existing cases are unchanged.",
            what_was_not_changed="No case was created.",
            what_you_can_do="Retry with a non-empty title describing the investigation topic.",
        )

    created_at = _utc_now()
    result = conn.execute(
        insert(cases).values(
            title=title,
            created_at=created_at,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into cases did not return a primary key")
    case_id = int(pk[0])
    return CreateCaseResult(
        case_id=case_id,
        title=title,
        created_at=created_at,
    )


def list_cases(conn: Connection, params: ListCasesInput) -> ListCasesResult:
    """List all cases in this deployment, oldest first."""
    del params  # empty input model; required by governed-operation signature
    rows = conn.execute(
        select(
            cases.c.id,
            cases.c.title,
            cases.c.created_at,
        ).order_by(cases.c.id.asc())
    ).all()
    return ListCasesResult(cases=[_row_to_case(row) for row in rows])


def get_case(conn: Connection, params: GetCaseInput) -> GetCaseResult:
    """Open a case.

    Projection collections are empty placeholders and grow ticket by ticket
    (captures, claims, open questions, angles, renditions) — not a complete shape.
    """
    row = conn.execute(
        select(
            cases.c.id,
            cases.c.title,
            cases.c.created_at,
        ).where(cases.c.id == params.case_id)
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="Existing cases are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List cases and open an existing case_id, or create a new case.",
        )
    case_runs = list_runs(conn, ListRunsInput(case_id=params.case_id))
    return GetCaseResult(
        case=_row_to_case(row),
        runs=case_runs.runs,
        captures=list_capture_summaries_for_case(conn, params.case_id),
        claims=list_claims_for_case(conn, params.case_id),
        open_questions=list_open_questions_for_case(conn, params.case_id),
        coverage=derive_case_coverage(conn, params.case_id),
        angles=[],
        renditions=[],
    )
