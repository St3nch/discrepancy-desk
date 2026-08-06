"""HTTP `/api` transport tests for Run dispatch (human-only)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from desk.transports.wiring import API_ONLY, mcp_tool_names


def _create_case(client: TestClient, title: str = "Case") -> int:
    response = client.post("/api/cases", json={"title": title})
    assert response.status_code == 200
    return int(response.json()["case_id"])


def test_api_create_approve_list_runs(client: TestClient) -> None:
    case_id = _create_case(client)
    created = client.post(
        "/api/runs",
        json={
            "case_id": case_id,
            "question": "What is known officially?",
            "scope": "Official reports",
            "coverage_dimension": "official_foundation",
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "draft"
    assert body["coverage_dimension"] == "official_foundation"
    run_id = body["run_id"]

    approved = client.post(f"/api/runs/{run_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    listed = client.get(f"/api/cases/{case_id}/runs")
    assert listed.status_code == 200
    runs = listed.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "approved"

    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    assert any(r["run_id"] == run_id for r in detail.json()["runs"])


def test_dispatch_ops_are_api_only_not_mcp() -> None:
    for name in ("create_run", "approve_run", "list_runs"):
        assert name in API_ONLY
        assert name not in mcp_tool_names()
    assert "claim_next_run" in mcp_tool_names()
    assert "claim_next_run" not in API_ONLY


def test_api_approve_refusal_shape(client: TestClient) -> None:
    response = client.post("/api/runs/99999/approve")
    assert response.status_code == 409
    assert response.json()["refusal"]["code"] == "RUN_NOT_FOUND"
    assert "Traceback" not in response.text
