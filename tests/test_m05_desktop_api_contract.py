from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from discrepancy_desk.web import create_app, desktop_runtime_config_from_env


TOKEN = "test-launch-token"


def client_for(tmp_path: Path, *, token: str | None = TOKEN) -> tuple[TestClient, Path]:
    database = tmp_path / "runtime" / "desk.sqlite3"
    app = create_app(
        database_path=database,
        evidence_root=tmp_path / "evidence",
        migrations_root=Path("migrations"),
        desktop_token=token,
        desktop_api_version="1",
    )
    return TestClient(app), database


def test_desktop_api_is_disabled_without_launch_token(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path, token=None)
    with client:
        response = client.get("/desktop-api/v1/health")
        assert response.status_code == 503
        assert response.json() == {
            "error": "desktop_api_disabled",
            "message": "Desktop API mode is not enabled.",
            "preserved": True,
            "changed": False,
        }


def test_desktop_api_refuses_missing_and_incorrect_tokens(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    with client:
        missing = client.get("/desktop-api/v1/health")
        wrong = client.get(
            "/desktop-api/v1/health",
            headers={"x-discrepancy-desk-token": "wrong"},
        )
        assert missing.status_code == 401
        assert wrong.status_code == 401
        assert missing.json()["preserved"] is True
        assert missing.json()["changed"] is False


def test_desktop_health_reports_version_and_migration(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    with client:
        response = client.get(
            "/desktop-api/v1/health",
            headers={"x-discrepancy-desk-token": TOKEN},
        )
        assert response.status_code == 200
        assert response.json() == {
            "api_version": "1",
            "service": "discrepancy-desk-desktop-backend",
            "status": "healthy",
            "sqlite_integrity": "ok",
            "migration": "0004",
        }


def test_desktop_queries_are_token_and_account_scoped(tmp_path: Path) -> None:
    client, database = client_for(tmp_path)
    headers = {"x-discrepancy-desk-token": TOKEN}
    with client:
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO owned_accounts VALUES ('acct-1','x','external-1','Desk',1)"
            )
            connection.commit()
        finally:
            connection.close()

        accounts = client.get("/desktop-api/v1/accounts", headers=headers)
        assert accounts.status_code == 200
        assert accounts.json()["accounts"][0]["id"] == "acct-1"

        center = client.get(
            "/desktop-api/v1/command-center?account_id=acct-1",
            headers=headers,
        )
        assert center.status_code == 200
        assert center.json()["account_id"] == "acct-1"

        refused = client.get(
            "/desktop-api/v1/command-center?account_id=fabricated",
            headers=headers,
        )
        assert refused.status_code == 400
        payload = refused.json()
        assert payload["preserved"] is True
        assert payload["changed"] is False
        assert payload["safe_next_action"]


def test_web_harness_remains_available_without_desktop_token(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path, token=None)
    with client:
        response = client.get("/health")
        assert response.status_code == 200
        assert "SQLite integrity" in response.text


def test_desktop_runtime_config_requires_loopback_token_and_valid_port(monkeypatch) -> None:
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_TOKEN", "x" * 64)
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_HOST", "127.0.0.1")
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_PORT", "43127")
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_DATABASE", "runtime/desktop.sqlite3")
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_EVIDENCE_ROOT", "evidence")
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_MIGRATIONS_ROOT", "migrations")
    assert desktop_runtime_config_from_env() == {
        "host": "127.0.0.1",
        "port": 43127,
        "token": "x" * 64,
        "database_path": Path("runtime/desktop.sqlite3"),
        "evidence_root": Path("evidence"),
        "migrations_root": Path("migrations"),
    }


def test_desktop_runtime_config_rejects_non_loopback_and_bad_values(monkeypatch) -> None:
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_TOKEN", "x" * 64)
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_HOST", "0.0.0.0")
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_PORT", "43127")
    with pytest.raises(ValueError, match="127.0.0.1"):
        desktop_runtime_config_from_env()

    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_HOST", "127.0.0.1")
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_TOKEN", "short")
    with pytest.raises(ValueError, match="too short"):
        desktop_runtime_config_from_env()

    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_TOKEN", "x" * 64)
    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_PORT", "not-a-port")
    with pytest.raises(ValueError, match="integer"):
        desktop_runtime_config_from_env()

    monkeypatch.setenv("DISCREPANCY_DESK_DESKTOP_PORT", "70000")
    with pytest.raises(ValueError, match="valid range"):
        desktop_runtime_config_from_env()


def test_desktop_mutation_parity_capture_organize_tags_and_schedule(tmp_path: Path) -> None:
    client, database = client_for(tmp_path)
    with client:
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "INSERT INTO owned_accounts VALUES ('acct-1','x','one','Desk',1)"
            )
            connection.commit()
        finally:
            connection.close()
        headers = {"x-discrepancy-desk-token": TOKEN}
        capture = client.post(
            "/desktop-api/v1/work-items",
            headers=headers,
            json={"title": "Desktop parity item", "operation_key": "desktop:capture:1"},
        )
        assert capture.status_code == 201
        work_item_id = capture.json()["work_item_id"]
        organize = client.post(
            f"/desktop-api/v1/work-items/{work_item_id}/organize",
            headers=headers,
            json={
                "account_id": "acct-1",
                "lane": "archive",
                "topic": "History",
                "priority": 4,
                "operation_key": "desktop:organize:1",
            },
        )
        assert organize.status_code == 200
        tags = client.put(
            f"/desktop-api/v1/work-items/{work_item_id}/tags",
            headers=headers,
            json={
                "account_id": "acct-1",
                "tags": [" FOIA ", "history"],
                "operation_key": "desktop:tags:1",
            },
        )
        assert tags.status_code == 200
        schedule = client.post(
            f"/desktop-api/v1/work-items/{work_item_id}/schedule",
            headers=headers,
            json={
                "account_id": "acct-1",
                "is_evergreen": True,
                "operation_key": "desktop:schedule:1",
            },
        )
        assert schedule.status_code == 200
        connection = sqlite3.connect(database)
        try:
            assert connection.execute(
                "SELECT lane FROM editorial_profiles WHERE work_item_id=?", (work_item_id,)
            ).fetchone()[0] == "archive"
            assert [row[0] for row in connection.execute(
                "SELECT tag FROM work_item_tags WHERE work_item_id=? ORDER BY tag",
                (work_item_id,),
            )] == ["foia", "history"]
            assert connection.execute(
                "SELECT status FROM schedule_slots WHERE work_item_id=?", (work_item_id,)
            ).fetchone()[0] == "active"
        finally:
            connection.close()


def test_desktop_mutations_fail_closed_without_required_scope(tmp_path: Path) -> None:
    client, _ = client_for(tmp_path)
    with client:
        response = client.post(
            "/desktop-api/v1/work-items/missing/organize",
            headers={"x-discrepancy-desk-token": TOKEN},
            json={"lane": "archive"},
        )
        assert response.status_code == 400
        assert response.json()["changed"] is False
