"""HTTP `/api` transport tests for Case operations."""

from __future__ import annotations

from fastapi.testclient import TestClient

from desk.transports.wiring import API_ONLY, mcp_tool_names


def test_api_create_list_get_case(client: TestClient) -> None:
    created = client.post("/api/cases", json={"title": "Vela Incident"})
    assert created.status_code == 200
    body = created.json()
    assert body["title"] == "Vela Incident"
    assert "account_id" not in body
    case_id = body["case_id"]

    listed = client.get("/api/cases")
    assert listed.status_code == 200
    cases = listed.json()["cases"]
    assert any(c["case_id"] == case_id for c in cases)
    assert all("account_id" not in c for c in cases)

    detail = client.get(f"/api/cases/{case_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["case"]["title"] == "Vela Incident"
    assert "account_id" not in payload["case"]
    assert payload["runs"] == []
    assert payload["captures"] == []
    assert payload["claims"] == []  # claim records; empty until propose_claim
    assert payload["open_questions"] == []
    assert payload["angles"] == []
    assert payload["renditions"] == []
    # No complete/closed fields on the projection.
    assert "status" not in payload["case"]
    assert "state" not in payload["case"]
    assert "closed" not in payload["case"]


def test_api_get_case_refusal(client: TestClient) -> None:
    response = client.get("/api/cases/40404")
    assert response.status_code == 409
    payload = response.json()
    assert payload["refusal"]["code"] == "CASE_NOT_FOUND"
    assert payload["refusal"]["what_was_not_changed"] == "Nothing was written."
    assert "Traceback" not in response.text


def test_api_create_empty_title_refusal(client: TestClient) -> None:
    response = client.post("/api/cases", json={"title": "  "})
    assert response.status_code == 409
    assert response.json()["refusal"]["code"] == "CASE_TITLE_EMPTY"


def test_case_ops_are_api_only_not_mcp() -> None:
    for name in ("create_case", "list_cases", "get_case"):
        assert name in API_ONLY
        assert name not in mcp_tool_names()
