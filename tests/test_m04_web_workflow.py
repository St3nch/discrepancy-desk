from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from discrepancy_desk.web import create_app


def client_for(tmp_path: Path) -> tuple[TestClient, Path]:
    database = tmp_path / "runtime" / "desk.sqlite3"
    app = create_app(database_path=database, evidence_root=tmp_path / "evidence", migrations_root=Path("migrations"))
    return TestClient(app), database


def scalar(database: Path, query: str) -> object:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(query).fetchone()
        assert row is not None
        return row[0]
    finally:
        connection.close()


def test_command_center_organize_schedule_and_pipeline(tmp_path: Path) -> None:
    client, database = client_for(tmp_path)
    with client:
        client.post("/accounts", data={"platform": "x", "external_account_id": "acct", "username": "Desk"})
        account_id = str(scalar(database, "SELECT id FROM owned_accounts"))
        captured = client.post("/work-items", data={"title": "Scheduled filing"}, follow_redirects=False)
        work_item_id = captured.headers["location"].rsplit("/", 1)[-1]
        organized = client.post(
            f"/work-items/{work_item_id}/organize",
            data={"account_id": account_id, "lane": "archive", "topic": "History", "priority": "5", "operator_notes": "note"},
            follow_redirects=False,
        )
        assert organized.status_code == 303
        tagged = client.post(
            f"/work-items/{work_item_id}/tags",
            data={"account_id": account_id, "tags_text": "FOIA, history"},
            follow_redirects=False,
        )
        assert tagged.status_code == 303
        when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        scheduled = client.post(
            f"/work-items/{work_item_id}/schedule",
            data={"account_id": account_id, "scheduled_for": when},
            follow_redirects=False,
        )
        assert scheduled.status_code == 303
        command = client.get(f"/?account_id={account_id}")
        assert command.status_code == 200
        assert "Command Center" in command.text
        schedule = client.get(f"/schedule?account_id={account_id}")
        assert schedule.status_code == 200
        assert "Scheduled filing" in schedule.text
        pipeline = client.get(f"/pipeline?account_id={account_id}&view=needs_my_review")
        assert pipeline.status_code == 200
        detail = client.get(f"/work-items/{work_item_id}")
        assert "Editorial organization" in detail.text
        assert "history" in detail.text


def test_unknown_pipeline_view_and_cross_account_organization_fail_closed(tmp_path: Path) -> None:
    client, database = client_for(tmp_path)
    with client:
        client.post("/accounts", data={"platform": "x", "external_account_id": "one", "username": "One"})
        client.post("/accounts", data={"platform": "x", "external_account_id": "two", "username": "Two"})
        connection = sqlite3.connect(database)
        try:
            accounts = [row[0] for row in connection.execute("SELECT id FROM owned_accounts ORDER BY external_account_id")]
        finally:
            connection.close()
        captured = client.post("/work-items", data={"title": "Scoped"}, follow_redirects=False)
        work_item_id = captured.headers["location"].rsplit("/", 1)[-1]
        client.post(f"/work-items/{work_item_id}/organize", data={"account_id": accounts[0], "lane": "archive", "priority": "3"})
        conflict = client.post(
            f"/work-items/{work_item_id}/organize",
            data={"account_id": accounts[1], "lane": "archive", "priority": "3"},
        )
        assert conflict.status_code == 400
        assert "not changed" not in conflict.text.lower() or "account" in conflict.text.lower()
        bad_view = client.get(f"/pipeline?account_id={accounts[0]}&view=unknown")
        assert bad_view.status_code == 400
        assert "unknown pipeline view" in bad_view.text
