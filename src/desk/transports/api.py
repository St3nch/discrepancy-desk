"""HTTP `/api` transport — operator-facing routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.service import (
    add_lead,
    answer_suspended_run,
    approve_run,
    attach_lead,
    attest_coverage,
    cancel_run,
    create_case,
    create_operator_open_question,
    create_run,
    decide_open_question,
    dispose_lead,
    get_case,
    get_run_close,
    list_cases,
    list_leads,
    list_runs,
    promote_lead,
    summarise_lead,
)
from desk.service.models import (
    AddLeadInput,
    AddLeadResult,
    AnswerSuspendedRunBody,
    AnswerSuspendedRunInput,
    AnswerSuspendedRunResult,
    ApproveRunInput,
    ApproveRunResult,
    AttachLeadBody,
    AttachLeadInput,
    AttachLeadResult,
    AttestCoverageBody,
    AttestCoverageInput,
    AttestCoverageResult,
    CancelRunInput,
    CancelRunResult,
    CreateCaseInput,
    CreateCaseResult,
    CreateOperatorOpenQuestionBody,
    CreateOperatorOpenQuestionInput,
    CreateOperatorOpenQuestionResult,
    CreateRunInput,
    CreateRunResult,
    DecideOpenQuestionBody,
    DecideOpenQuestionInput,
    DecideOpenQuestionResult,
    DisposeLeadInput,
    DisposeLeadResult,
    GetCaseInput,
    GetCaseResult,
    GetRunCloseInput,
    GetRunCloseResult,
    ListCasesInput,
    ListCasesResult,
    ListLeadsInput,
    ListLeadsResult,
    ListRunsInput,
    ListRunsResult,
    PromoteLeadBody,
    PromoteLeadInput,
    PromoteLeadResult,
    SummariseLeadBody,
    SummariseLeadInput,
    SummariseLeadResult,
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
    "/cases/{case_id}/coverage/{stage}/attest",
    response_model=AttestCoverageResult,
    name="attest_coverage",
)
def api_attest_coverage(
    case_id: int,
    stage: str,
    body: AttestCoverageBody,
    engine: EngineDep,
) -> AttestCoverageResult:
    """Human-only: attest a measurable coverage stage complete (D20)."""
    payload = AttestCoverageInput(
        case_id=case_id,
        stage=stage,
        actor=body.actor,
        examined_capture_ids=list(body.examined_capture_ids),
    )
    with connection_scope(engine) as conn:
        return attest_coverage(conn, payload)


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


@router.post(
    "/runs/{run_id}/answer-suspension",
    response_model=AnswerSuspendedRunResult,
    name="answer_suspended_run",
)
def api_answer_suspended_run(
    run_id: int,
    body: AnswerSuspendedRunBody,
    engine: EngineDep,
) -> AnswerSuspendedRunResult:
    """Human-only: answer a suspended run and return it to claimed."""
    payload = AnswerSuspendedRunInput(run_id=run_id, answer=body.answer)
    with connection_scope(engine) as conn:
        return answer_suspended_run(conn, payload)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=CancelRunResult,
    name="cancel_run",
)
def api_cancel_run(
    run_id: int,
    engine: EngineDep,
) -> CancelRunResult:
    """Human-only: cancel a draft/approved/claimed/suspended run (F-26)."""
    with connection_scope(engine) as conn:
        return cancel_run(conn, CancelRunInput(run_id=run_id))


@router.get(
    "/runs/{run_id}/close",
    response_model=GetRunCloseResult,
    name="get_run_close",
)
def api_get_run_close(
    run_id: int,
    engine: EngineDep,
) -> GetRunCloseResult:
    """Human-only: D13 run-close view (agenda first, detail behind fold)."""
    with connection_scope(engine) as conn:
        return get_run_close(conn, GetRunCloseInput(run_id=run_id))


@router.post(
    "/open-questions/{open_question_id}/decide",
    response_model=DecideOpenQuestionResult,
    name="decide_open_question",
)
def api_decide_open_question(
    open_question_id: int,
    body: DecideOpenQuestionBody,
    engine: EngineDep,
) -> DecideOpenQuestionResult:
    """Human-only: approve / reject / replace a pending agenda item."""
    payload = DecideOpenQuestionInput(
        open_question_id=open_question_id,
        decision=body.decision,
        disposition=body.disposition,
        text=body.text,
        scope=body.scope,
    )
    with connection_scope(engine) as conn:
        return decide_open_question(conn, payload)


@router.post(
    "/runs/{run_id}/open-questions",
    response_model=CreateOperatorOpenQuestionResult,
    name="create_operator_open_question",
)
def api_create_operator_open_question(
    run_id: int,
    body: CreateOperatorOpenQuestionBody,
    engine: EngineDep,
) -> CreateOperatorOpenQuestionResult:
    """Human-only: originate an open question (works when proposed agenda is empty)."""
    payload = CreateOperatorOpenQuestionInput(
        run_id=run_id,
        text=body.text,
        scope=body.scope,
        disposition=body.disposition,
    )
    with connection_scope(engine) as conn:
        return create_operator_open_question(conn, payload)


# --- Lead inbox (ticket 09 / D18) — add_lead is MCP_AND_API; rest API-only ---


@router.post(
    "/leads",
    response_model=AddLeadResult,
    name="add_lead",
)
def api_add_lead(
    body: AddLeadInput,
    engine: EngineDep,
    request: Request,
) -> AddLeadResult:
    """Drop a URL into the lead inbox; capture immediately (always)."""
    vault = request.app.state.vault
    settings = request.app.state.settings
    with connection_scope(engine) as conn:
        return add_lead(
            conn,
            body,
            vault=vault,
            locator_map_cap=settings.locator_map_element_cap,
        )


@router.get(
    "/leads",
    response_model=ListLeadsResult,
    name="list_leads",
)
def api_list_leads(
    engine: EngineDep,
    inbox_status: str | None = None,
) -> ListLeadsResult:
    """List leads. Default: open inbox. Pass inbox_status=all for every status."""
    with connection_scope(engine) as conn:
        return list_leads(conn, ListLeadsInput(inbox_status=inbox_status))


@router.post(
    "/leads/{lead_id}/attach",
    response_model=AttachLeadResult,
    name="attach_lead",
)
def api_attach_lead(
    lead_id: int,
    body: AttachLeadBody,
    engine: EngineDep,
) -> AttachLeadResult:
    """Human-only: attach an open lead to an existing case."""
    payload = AttachLeadInput(lead_id=lead_id, case_id=body.case_id)
    with connection_scope(engine) as conn:
        return attach_lead(conn, payload)


@router.post(
    "/leads/{lead_id}/promote",
    response_model=PromoteLeadResult,
    name="promote_lead",
)
def api_promote_lead(
    lead_id: int,
    body: PromoteLeadBody,
    engine: EngineDep,
) -> PromoteLeadResult:
    """Human-only: create a case from an open lead and attach it."""
    payload = PromoteLeadInput(lead_id=lead_id, title=body.title)
    with connection_scope(engine) as conn:
        return promote_lead(conn, payload)


@router.post(
    "/leads/{lead_id}/dispose",
    response_model=DisposeLeadResult,
    name="dispose_lead",
)
def api_dispose_lead(
    lead_id: int,
    engine: EngineDep,
) -> DisposeLeadResult:
    """Human-only: dispose an open lead."""
    with connection_scope(engine) as conn:
        return dispose_lead(conn, DisposeLeadInput(lead_id=lead_id))


@router.post(
    "/leads/{lead_id}/summarise",
    response_model=SummariseLeadResult,
    name="summarise_lead",
)
def api_summarise_lead(
    lead_id: int,
    body: SummariseLeadBody,
    engine: EngineDep,
) -> SummariseLeadResult:
    """Human-only: optional summary (skippable; never blocks drop)."""
    payload = SummariseLeadInput(lead_id=lead_id, summary=body.summary)
    with connection_scope(engine) as conn:
        return summarise_lead(conn, payload)
