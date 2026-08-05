"""HTTP `/api` transport — operator-facing routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.service import (
    approve_run,
    create_case,
    create_run,
    get_case,
    list_cases,
    list_runs,
)
from desk.service.models import (
    ApproveRunInput,
    ApproveRunResult,
    CreateCaseInput,
    CreateCaseResult,
    CreateRunInput,
    CreateRunResult,
    GetCaseInput,
    GetCaseResult,
    ListCasesInput,
    ListCasesResult,
    ListRunsInput,
    ListRunsResult,
)

router = APIRouter()


def get_engine() -> Engine:
    """Overridden in tests and set by app factory."""
    raise RuntimeError("Database engine dependency is not configured")


EngineDep = Annotated[Engine, Depends(get_engine)]


# --- Case (ticket 02) — human-only ---


@router.post(
    "/cases",
    response_model=CreateCaseResult,
    name="create_case",
)
def api_create_case(
    body: CreateCaseInput,
    engine: EngineDep,
) -> CreateCaseResult:
    with connection_scope(engine) as conn:
        return create_case(conn, body)


@router.get(
    "/cases",
    response_model=ListCasesResult,
    name="list_cases",
)
def api_list_cases(engine: EngineDep) -> ListCasesResult:
    with connection_scope(engine) as conn:
        return list_cases(conn, ListCasesInput())


@router.get(
    "/cases/{case_id}",
    response_model=GetCaseResult,
    name="get_case",
)
def api_get_case(
    case_id: int,
    engine: EngineDep,
) -> GetCaseResult:
    with connection_scope(engine) as conn:
        return get_case(conn, GetCaseInput(case_id=case_id))


# --- Run (ticket 03) — human-only dispatch ---


@router.post(
    "/runs",
    response_model=CreateRunResult,
    name="create_run",
)
def api_create_run(
    body: CreateRunInput,
    engine: EngineDep,
) -> CreateRunResult:
    with connection_scope(engine) as conn:
        return create_run(conn, body)


@router.post(
    "/runs/{run_id}/approve",
    response_model=ApproveRunResult,
    name="approve_run",
)
def api_approve_run(
    run_id: int,
    engine: EngineDep,
) -> ApproveRunResult:
    with connection_scope(engine) as conn:
        return approve_run(conn, ApproveRunInput(run_id=run_id))


@router.get(
    "/cases/{case_id}/runs",
    response_model=ListRunsResult,
    name="list_runs",
)
def api_list_runs(
    case_id: int,
    engine: EngineDep,
) -> ListRunsResult:
    with connection_scope(engine) as conn:
        return list_runs(conn, ListRunsInput(case_id=case_id))
