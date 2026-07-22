from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.db import connect
from discrepancy_desk.operator_service import (
    add_source_record,
    capture_work_item,
    create_owned_account,
    get_control_room_item,
    reject_review,
    run_matched_operator_loop,
)
from discrepancy_desk.persistence import transition_work_item, verify_audit_chain


def migrate(db_path: Path, revision: str = "head") -> sqlite3.Connection:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, revision)
    return connect(db_path)


def test_migration_0002_adds_source_records_without_losing_0001_data(tmp_path: Path) -> None:
    database = tmp_path / "upgrade.sqlite3"
    connection = migrate(database, "0001")
    try:
        now = "2026-07-19T00:00:00+00:00"
        connection.execute(
            "INSERT INTO owned_accounts VALUES ('acct-1','x','external-1','Desk',1)"
        )
        connection.execute(
            "INSERT INTO work_items VALUES ('work-1','captured','Existing',?,?)",
            (now, now),
        )
        connection.commit()
    finally:
        connection.close()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(cfg, "head")

    connection = connect(database)
    try:
        assert connection.execute("SELECT title FROM work_items WHERE id='work-1'").fetchone()[0] == "Existing"
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0005"
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='source_records'"
        ).fetchone()
        assert table is not None
    finally:
        connection.close()


def test_complete_matched_operator_loop_and_control_room_read(tmp_path: Path) -> None:
    database = tmp_path / "operator.sqlite3"
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    evidence = evidence_root / "capture.json"
    evidence.write_bytes(b'{"source":"owned fixture"}\n')

    connection = migrate(database)
    try:
        result = run_matched_operator_loop(
            connection,
            evidence_root,
            account_id="acct-1",
            external_account_id="2078860810688848010",
            username="DiscrepancyDesk",
            work_item_id="work-1",
            title="Check the filing anomaly",
            source_id="source-1",
            source_locator="https://example.test/public-source",
            evidence_id="evidence-1",
            evidence_relative_path="capture.json",
            evidence_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
            revision_id="revision-1",
            authored_text="The filing cabinet denies everything.",
            approval_id="approval-1",
            publication_id="publication-1",
            external_post_id="post-1",
            canonical_url="https://x.com/DiscrepancyDesk/status/post-1",
            metric_snapshot_id="metric-1",
            metric_capture_session_id="metric-session-1",
            metrics={"likes": 3, "reposts": 1},
            actor_id="owner",
            operation_prefix="loop-1",
        )
        assert result.publication_id == "publication-1"
        view = get_control_room_item(connection, "work-1")
        assert view["work_item"]["state"] == "published"
        assert view["sources"][0]["locator"] == "https://example.test/public-source"
        assert view["evidence"][0]["verification_state"] == "verified"
        assert view["revisions"][0]["id"] == "revision-1"
        assert view["publication"]["verification_state"] == "owner_confirmed"
        assert view["metrics"][0]["metrics"] == {"likes": 3, "reposts": 1}
        assert verify_audit_chain(connection)
    finally:
        connection.close()


def test_account_capture_and_source_idempotency_conflicts(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "idempotency.sqlite3")
    try:
        assert create_owned_account(
            connection,
            account_id="acct-1",
            platform="x",
            external_account_id="external-1",
            username="Desk",
            operation_key="account-key",
            actor_id="owner",
        ) == "acct-1"
        assert create_owned_account(
            connection,
            account_id="acct-1",
            platform="x",
            external_account_id="external-1",
            username="Desk",
            operation_key="account-key",
            actor_id="owner",
        ) == "acct-1"
        with pytest.raises(ValueError, match="conflicting content"):
            create_owned_account(
                connection,
                account_id="acct-2",
                platform="x",
                external_account_id="external-2",
                username="Other",
                operation_key="account-key",
                actor_id="owner",
            )

        capture_work_item(
            connection,
            work_item_id="work-1",
            title="Captured",
            operation_key="capture-key",
            actor_id="owner",
        )
        add_source_record(
            connection,
            source_id="source-1",
            work_item_id="work-1",
            source_kind="manual_note",
            locator=None,
            note_text="Exact source note",
            operation_key="source-key",
            actor_id="owner",
        )
        assert add_source_record(
            connection,
            source_id="source-1",
            work_item_id="work-1",
            source_kind="manual_note",
            locator=None,
            note_text="Exact source note",
            operation_key="source-key",
            actor_id="owner",
        ) == "source-1"
        with pytest.raises(ValueError, match="conflicting content"):
            add_source_record(
                connection,
                source_id="source-2",
                work_item_id="work-1",
                source_kind="manual_note",
                locator=None,
                note_text="Changed note",
                operation_key="source-key",
                actor_id="owner",
            )
        assert connection.execute("SELECT count(*) FROM source_records").fetchone()[0] == 1
    finally:
        connection.close()


def test_rejection_requires_review_state_and_preserves_reason_in_audit(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "reject.sqlite3")
    try:
        create_owned_account(
            connection,
            account_id="acct-1",
            platform="x",
            external_account_id="external-1",
            username="Desk",
            operation_key="account",
            actor_id="owner",
        )
        capture_work_item(
            connection,
            work_item_id="work-1",
            title="Reject fixture",
            operation_key="capture",
            actor_id="owner",
        )
        with pytest.raises(ValueError, match="human_review_needed"):
            reject_review(
                connection,
                work_item_id="work-1",
                reason="Not ready",
                actor_id="owner",
                operation_key="reject-early",
            )
        for target in ("drafting", "human_review_needed"):
            transition_work_item(connection, "work-1", target, actor_id="owner")
        reject_review(
            connection,
            work_item_id="work-1",
            reason="Unsupported claim",
            actor_id="owner",
            operation_key="reject-1",
        )
        assert connection.execute("SELECT state FROM work_items").fetchone()[0] == "rejected"
        payload = connection.execute(
            "SELECT payload_json FROM audit_events WHERE operation='reject_review'"
        ).fetchone()[0]
        assert b"Unsupported claim" in bytes(payload)
    finally:
        connection.close()


def test_control_room_read_rejects_unknown_item(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "unknown.sqlite3")
    try:
        with pytest.raises(ValueError, match="unknown work item"):
            get_control_room_item(connection, "missing")
    finally:
        connection.close()


def test_owned_account_stable_identity_replay_uses_existing_record(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "stable-account.sqlite3")
    try:
        first = create_owned_account(
            connection,
            account_id="acct-first",
            platform="x",
            external_account_id="external-stable",
            username="Desk",
            operation_key="account-first",
            actor_id="owner",
        )
        replay = create_owned_account(
            connection,
            account_id="acct-random-form-retry",
            platform="x",
            external_account_id="external-stable",
            username="Desk",
            operation_key="account-second",
            actor_id="owner",
        )
        assert first == "acct-first"
        assert replay == "acct-first"
        assert connection.execute("SELECT count(*) FROM owned_accounts").fetchone()[0] == 1
        assert connection.execute(
            "SELECT result_ref FROM operation_keys WHERE operation_key='account-second'"
        ).fetchone()[0] == "acct-first"
    finally:
        connection.close()


def test_owned_account_stable_identity_updates_mutable_username_metadata(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "stable-account-update.sqlite3")
    try:
        create_owned_account(
            connection,
            account_id="acct-first",
            platform="x",
            external_account_id="external-stable",
            username="Desk",
            operation_key="account-first",
            actor_id="owner",
        )
        updated = create_owned_account(
            connection,
            account_id="acct-second",
            platform="x",
            external_account_id="external-stable",
            username="OtherDesk",
            operation_key="account-second",
            actor_id="owner",
        )
        preserved = create_owned_account(
            connection,
            account_id="acct-third",
            platform="x",
            external_account_id="external-stable",
            username=None,
            operation_key="account-third",
            actor_id="owner",
        )
        assert updated == preserved == "acct-first"
        assert connection.execute("SELECT count(*) FROM owned_accounts").fetchone()[0] == 1
        assert connection.execute("SELECT username FROM owned_accounts").fetchone()[0] == "OtherDesk"
        assert connection.execute(
            "SELECT count(*) FROM audit_events WHERE operation='update_owned_account_metadata'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM operation_keys WHERE operation_key IN ('account-second','account-third')"
        ).fetchone()[0] == 2
    finally:
        connection.close()
