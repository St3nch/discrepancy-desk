"""HTTP seam: answer / cancel human-only; suspend / read_case_context not on /api."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.service import approve_run, claim_next_run, create_case, create_run, suspend_run
from desk.service.models import (
    INSTANCE_VS_CLASS_NOTICE,
    ApproveRunInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    SuspendRunInput,
)


def test_answer_suspension_http_round_trip(client: TestClient, engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="API suspend")).case_id
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id, question="Q?", scope="s", coverage_dimension="official_foundation"
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        run_id = claimed.run.run_id
        token = claimed.run.claim_token
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Is this the same entity?",
                uncertainty="Alias vs distinct",
                default_action="Treat as alias",
            ),
        )

    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    runs = detail.json()["runs"]
    assert runs[0]["status"] == "suspended"
    assert runs[0]["suspension_question"] == "Is this the same entity?"
    assert runs[0]["instance_vs_class_notice"] == INSTANCE_VS_CLASS_NOTICE
    assert len(runs[0]["suspensions"]) == 1

    answered = client.post(
        f"/api/runs/{run_id}/answer-suspension",
        json={"answer": "Same entity under a later name."},
    )
    assert answered.status_code == 200
    body = answered.json()
    assert body["status"] == "claimed"
    assert body["human_answer"] == "Same entity under a later name."
    assert body["instance_vs_class_notice"] is None

    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Again?",
                uncertainty="A vs B",
                default_action="A",
            ),
        )

    empty = client.post(
        f"/api/runs/{run_id}/answer-suspension",
        json={"answer": "   "},
    )
    assert empty.status_code == 409
    assert empty.json()["refusal"]["code"] == "SUSPEND_ANSWER_EMPTY"


def test_cancel_suspended_via_http(client: TestClient, engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="API cancel")).case_id
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id, question="Q?", scope="s", coverage_dimension="official_foundation"
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        run_id = claimed.run.run_id
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=claimed.run.claim_token,
                question="Kill me?",
                uncertainty="X",
                default_action="Stop",
            ),
        )

    cancelled = client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Case is free for a new approval.
    draft2 = client.post(
        "/api/runs",
        json={
            "case_id": case_id,
            "question": "Next?",
            "scope": "s",
            "coverage_dimension": "official_foundation",
        },
    )
    assert draft2.status_code == 200
    approved = client.post(f"/api/runs/{draft2.json()['run_id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_suspend_not_on_http_api(client: TestClient) -> None:
    response = client.post(
        "/api/runs/1/suspend",
        json={
            "question": "Q?",
            "uncertainty": "A vs B",
            "default_action": "A",
            "claim_token": "x",
        },
    )
    assert response.status_code == 404


def test_cancel_not_on_mcp_wiring() -> None:
    from desk.transports.wiring import API_ONLY, mcp_tool_names

    assert "cancel_run" in API_ONLY
    assert "cancel_run" not in mcp_tool_names()
    assert "answer_suspended_run" not in mcp_tool_names()
    assert "read_case_context" in mcp_tool_names()
