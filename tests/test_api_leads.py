"""HTTP `/api` transport tests for lead inbox (ticket 09 / D18)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from desk.transports.wiring import API_ONLY, MCP_AND_API, mcp_tool_names


def _html_fetch(_url: str) -> tuple[bytes, str]:
    body = b"<!DOCTYPE html><html><body><p>API lead body.</p></body></html>"
    return body, "text/html"


def test_add_lead_on_both_transport_sets() -> None:
    assert "add_lead" in MCP_AND_API
    assert "add_lead" in mcp_tool_names()
    assert "add_lead" not in API_ONLY  # dual surface, not API-only
    for name in (
        "list_leads",
        "attach_lead",
        "promote_lead",
        "dispose_lead",
        "summarise_lead",
    ):
        assert name in API_ONLY
        assert name not in mcp_tool_names()
    assert "get_lead" not in API_ONLY
    assert "get_lead" not in mcp_tool_names()


def test_api_add_list_attach_dispose(client: TestClient, tmp_path: Path) -> None:
    del tmp_path
    with patch("desk.service.leads.default_fetch", side_effect=_html_fetch):
        created = client.post(
            "/api/leads",
            json={"url": "https://example.com/api-lead", "note": "operator drop"},
        )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["material_status"] == "captured"
    assert body["inbox_status"] == "open"
    assert body["capture_id"] is not None
    assert body["capture_status"] == "unexamined"
    lead_id = body["lead_id"]

    listed = client.get("/api/leads")
    assert listed.status_code == 200
    assert any(item["lead_id"] == lead_id for item in listed.json()["leads"])

    case = client.post("/api/cases", json={"title": "Attach target"}).json()
    attached = client.post(
        f"/api/leads/{lead_id}/attach",
        json={"case_id": case["case_id"]},
    )
    assert attached.status_code == 200
    assert attached.json()["inbox_status"] == "attached"
    assert attached.json()["case_id"] == case["case_id"]

    # Promote a second lead
    with patch("desk.service.leads.default_fetch", side_effect=_html_fetch):
        second = client.post(
            "/api/leads",
            json={"url": "https://example.com/promote-me", "note": ""},
        ).json()
    promoted = client.post(
        f"/api/leads/{second['lead_id']}/promote",
        json={"title": "Promoted from lead"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["inbox_status"] == "promoted"
    assert promoted.json()["case_id"] is not None

    with patch("desk.service.leads.default_fetch", side_effect=_html_fetch):
        third = client.post(
            "/api/leads",
            json={"url": "https://example.com/dispose-me", "note": ""},
        ).json()
    disposed = client.post(f"/api/leads/{third['lead_id']}/dispose")
    assert disposed.status_code == 200
    assert disposed.json()["inbox_status"] == "disposed"

    # Summarise is skippable; when used, stores text
    with patch("desk.service.leads.default_fetch", side_effect=_html_fetch):
        fourth = client.post(
            "/api/leads",
            json={"url": "https://example.com/sum", "note": ""},
        ).json()
    summarised = client.post(
        f"/api/leads/{fourth['lead_id']}/summarise",
        json={"summary": "Short note for the inbox."},
    )
    assert summarised.status_code == 200
    assert summarised.json()["summary"] == "Short note for the inbox."


def test_api_identity_only_distinct(client: TestClient) -> None:
    from desk.refusals import DeskRefusal

    def auth_fetch(_url: str) -> tuple[bytes, str]:
        raise DeskRefusal(
            code="CAPTURE_AUTH_WALLED",
            what_happened="HTTP 401",
            what_was_preserved="n/a",
            what_was_not_changed="n/a",
            what_you_can_do="n/a",
        )

    with patch("desk.service.leads.default_fetch", side_effect=auth_fetch):
        created = client.post(
            "/api/leads",
            json={"url": "https://example.com/auth-wall", "note": ""},
        )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["material_status"] == "identity_only"
    assert body["capture_id"] is None
