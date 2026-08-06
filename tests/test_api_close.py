"""HTTP seam for run-close agenda (human-only)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.service import approve_run, claim_next_run, close_run, create_case, create_run
from desk.service.models import (
    ApproveRunInput,
    ClaimNextRunInput,
    CloseRunInput,
    CreateCaseInput,
    CreateRunInput,
    ProposedOpenQuestionInput,
)
from desk.transports.wiring import API_ONLY, mcp_tool_names


def test_operator_create_open_question_http(client: TestClient, engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="API own Q")).case_id
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Foundation?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        run_id = claimed.run.run_id
        close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=claimed.run.claim_token,
                proposed_questions=[],
            ),
        )

    created = client.post(
        f"/api/runs/{run_id}/open-questions",
        json={
            "text": "Who held the seal?",
            "scope": "Personnel files",
            "disposition": "not-yet-worked",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["agenda_decision"] == "approved"
    assert body["settled_text"] == "Who held the seal?"
    assert body["disposition"] == "not-yet-worked"

    view = client.get(f"/api/runs/{run_id}/close")
    assert view.status_code == 200
    assert len(view.json()["agenda"]) == 1


def test_run_close_http_and_decide(client: TestClient, engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="API close")).case_id
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Foundation?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        run_id = claimed.run.run_id
        close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=claimed.run.claim_token,
                proposed_questions=[
                    ProposedOpenQuestionInput(
                        text="Who signed?",
                        rationale="Signature missing",
                        proposed_scope="Archives",
                    )
                ],
                low_confidence_areas=["Scope felt thin"],
            ),
        )

    view = client.get(f"/api/runs/{run_id}/close")
    assert view.status_code == 200
    body = view.json()
    assert body["run"]["status"] == "complete"
    assert body["captures_count"] == 0
    assert body["claims_count"] == 0
    assert body["low_confidence_areas"] == ["Scope felt thin"]
    assert len(body["agenda"]) == 1
    oq_id = body["agenda"][0]["open_question_id"]
    assert body["agenda"][0]["source_run_question"] == "Foundation?"

    # Case projection includes open questions with lineage
    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    oqs = detail.json()["open_questions"]
    assert len(oqs) == 1
    assert oqs[0]["introduced_by_run_id"] == run_id

    decided = client.post(
        f"/api/open-questions/{oq_id}/decide",
        json={
            "decision": "approve",
            "disposition": "not-yet-worked",
            "text": "Who signed the annex?",
            "scope": "National archives 1970–1980",
        },
    )
    assert decided.status_code == 200
    assert decided.json()["agenda_decision"] == "approved"
    assert decided.json()["disposition"] == "not-yet-worked"


def test_close_run_not_on_http(client: TestClient) -> None:
    r = client.post("/api/runs/1/close", json={"claim_token": "x"})
    # GET is get_run_close; POST must not be close_run
    assert r.status_code in {404, 405}


def test_transport_split() -> None:
    assert "close_run" in mcp_tool_names()
    assert "close_run" not in API_ONLY
    assert "get_run_close" in API_ONLY
    assert "decide_open_question" in API_ONLY
    assert "create_operator_open_question" in API_ONLY
    assert "create_operator_open_question" not in mcp_tool_names()
    assert "get_run_close" not in mcp_tool_names()
