from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from discrepancy_desk.migration_integrity import begin_migration_guard
from discrepancy_desk.web import create_app


def client_for(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    database = tmp_path / "runtime" / "desk.sqlite3"
    evidence = tmp_path / "evidence"
    app = create_app(database_path=database, evidence_root=evidence, migrations_root=Path("migrations"))
    return TestClient(app), database, evidence


def scalar(database: Path, query: str, parameters: tuple[object, ...] = ()) -> object:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(query, parameters).fetchone()
        assert row is not None
        return row[0]
    finally:
        connection.close()


def test_health_and_empty_control_room(tmp_path: Path) -> None:
    client, _, _ = client_for(tmp_path)
    with client:
        health = client.get("/health")
        assert health.status_code == 200
        assert "SQLite integrity" in health.text
        assert "0002" in health.text
        index = client.get("/")
        assert index.status_code == 200
        assert "No work items" in index.text


def test_complete_http_operator_loop(tmp_path: Path) -> None:
    client, database, evidence_root = client_for(tmp_path)
    evidence_root.mkdir(parents=True, exist_ok=True)
    evidence_file = evidence_root / "capture.json"
    evidence_file.write_bytes(b'{"source":"fixture"}\n')

    with client:
        account = client.post(
            "/accounts",
            data={"platform": "x", "external_account_id": "account-123", "username": "Desk"},
            follow_redirects=False,
        )
        assert account.status_code == 303
        account_id = str(scalar(database, "SELECT id FROM owned_accounts"))

        captured = client.post(
            "/work-items", data={"title": "HTTP operator fixture"}, follow_redirects=False
        )
        assert captured.status_code == 303
        location = captured.headers["location"]
        work_item_id = location.rsplit("/", 1)[-1]

        source = client.post(
            f"/work-items/{work_item_id}/sources",
            data={
                "source_kind": "url",
                "locator": "https://example.invalid/source",
                "note_text": "",
            },
            follow_redirects=False,
        )
        assert source.status_code == 303

        evidence = client.post(
            f"/work-items/{work_item_id}/evidence",
            data={"relative_path": "capture.json"},
            follow_redirects=False,
        )
        assert evidence.status_code == 303
        assert scalar(database, "SELECT sha256 FROM evidence_refs") == hashlib.sha256(
            evidence_file.read_bytes()
        ).hexdigest()

        draft = client.post(
            f"/work-items/{work_item_id}/draft",
            data={"owned_account_id": account_id, "authored_text": "Exact HTTP-approved text"},
            follow_redirects=False,
        )
        assert draft.status_code == 303
        revision_id = str(scalar(database, "SELECT id FROM revisions"))
        assert scalar(database, "SELECT state FROM work_items") == "human_review_needed"

        approved = client.post(
            f"/work-items/{work_item_id}/approve",
            data={"revision_id": revision_id},
            follow_redirects=False,
        )
        assert approved.status_code == 303
        approval_id = str(scalar(database, "SELECT id FROM approvals"))
        assert scalar(database, "SELECT state FROM work_items") == "approved"

        ready = client.post(
            f"/work-items/{work_item_id}/manual-ready",
            data={"approval_id": approval_id},
            follow_redirects=False,
        )
        assert ready.status_code == 303
        assert scalar(database, "SELECT state FROM work_items") == "manual_ready"

        publication = client.post(
            f"/work-items/{work_item_id}/publication",
            data={
                "revision_id": revision_id,
                "approval_id": approval_id,
                "external_post_id": "post-123",
                "canonical_url": "https://x.com/Desk/status/post-123",
                "mismatch_reason": "",
            },
            follow_redirects=False,
        )
        assert publication.status_code == 303
        assert scalar(database, "SELECT state FROM work_items") == "published"
        publication_id = str(scalar(database, "SELECT id FROM publications"))

        metric = client.post(
            f"/work-items/{work_item_id}/metrics",
            data={
                "observation_method": "manual",
                "observation_state": "observed_value",
                "metrics_json": '{"likes": 4, "reposts": 1}',
            },
            follow_redirects=False,
        )
        assert metric.status_code == 303
        assert scalar(
            database,
            "SELECT publication_id FROM metric_snapshots",
        ) == publication_id

        view = client.get(location)
        assert view.status_code == 200
        assert "HTTP operator fixture" in view.text
        assert "published" in view.text
        assert "post-123" in view.text
        assert "likes" in view.text

    assert scalar(database, "SELECT count(*) FROM audit_events") >= 10


def test_mismatch_route_preserves_publication_mismatch_state(tmp_path: Path) -> None:
    client, database, _ = client_for(tmp_path)
    with client:
        client.post(
            "/accounts",
            data={"platform": "x", "external_account_id": "account-1", "username": "Desk"},
        )
        account_id = str(scalar(database, "SELECT id FROM owned_accounts"))
        captured = client.post(
            "/work-items", data={"title": "Mismatch fixture"}, follow_redirects=False
        )
        work_item_id = captured.headers["location"].rsplit("/", 1)[-1]
        client.post(
            f"/work-items/{work_item_id}/draft",
            data={"owned_account_id": account_id, "authored_text": "Approved text"},
        )
        revision_id = str(scalar(database, "SELECT id FROM revisions"))
        client.post(f"/work-items/{work_item_id}/approve", data={"revision_id": revision_id})
        approval_id = str(scalar(database, "SELECT id FROM approvals"))
        client.post(
            f"/work-items/{work_item_id}/manual-ready", data={"approval_id": approval_id}
        )
        response = client.post(
            f"/work-items/{work_item_id}/publication",
            data={
                "revision_id": revision_id,
                "approval_id": approval_id,
                "external_post_id": "mismatch-1",
                "canonical_url": "https://x.com/Desk/status/mismatch-1",
                "mismatch_reason": "A line was omitted during manual posting",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert scalar(database, "SELECT state FROM work_items") == "publication_mismatch"
        assert scalar(database, "SELECT verification_state FROM publications") == "verified_mismatch"


def test_routes_fail_closed_on_bad_revision_and_bad_metrics(tmp_path: Path) -> None:
    client, database, _ = client_for(tmp_path)
    with client:
        captured = client.post(
            "/work-items", data={"title": "Failure fixture"}, follow_redirects=False
        )
        work_item_id = captured.headers["location"].rsplit("/", 1)[-1]
        bad_approval = client.post(
            f"/work-items/{work_item_id}/approve", data={"revision_id": "fabricated"}
        )
        assert bad_approval.status_code == 400
        assert "does not belong" in bad_approval.text
        assert scalar(database, "SELECT state FROM work_items") == "captured"

        bad_metric = client.post(
            f"/work-items/{work_item_id}/metrics",
            data={
                "observation_method": "manual",
                "observation_state": "observed_value",
                "metrics_json": "not-json",
            },
        )
        assert bad_metric.status_code == 400
        assert "valid JSON" in bad_metric.text
        assert scalar(database, "SELECT count(*) FROM metric_snapshots") == 0


def test_startup_refuses_dirty_migration_state(tmp_path: Path) -> None:
    database = tmp_path / "runtime" / "dirty.sqlite3"
    begin_migration_guard(database, operation_id="interrupted", target_revision="head")
    app = create_app(
        database_path=database,
        evidence_root=tmp_path / "evidence",
        migrations_root=Path("migrations"),
    )
    with pytest.raises(Exception, match="dirty"):
        with TestClient(app):
            pass
