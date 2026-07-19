from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import begin_write, connect
from discrepancy_desk.migration_integrity import (
    MigrationIntegrityError,
    assert_clean_migration_state,
    begin_migration_guard,
    clear_migration_guard,
)
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    mark_manual_ready,
    record_metric_snapshot,
    record_publication,
    transition_work_item,
    utc_now,
    verify_audit_chain,
)


def migrate(db_path: Path) -> sqlite3.Connection:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


def prepared_publication(db: sqlite3.Connection) -> None:
    now = utc_now()
    db.execute(
        "INSERT INTO owned_accounts VALUES (?, 'x', ?, ?, 1)",
        ("acct-1", "12345", "DiscrepancyDesk"),
    )
    db.execute(
        "INSERT INTO work_items VALUES (?, 'captured', ?, ?, ?)",
        ("work-1", "Test item", now, now),
    )
    db.commit()
    transition_work_item(db, "work-1", "drafting", actor_id="owner")
    transition_work_item(db, "work-1", "human_review_needed", actor_id="owner")
    binding = create_revision(
        db,
        revision_id="rev-1",
        work_item_id="work-1",
        owned_account_id="acct-1",
        bundle=RevisionBundle("x", "acct-1", "Approved exact text"),
    )
    approve_revision(
        db,
        approval_id="approval-1",
        revision_id="rev-1",
        binding_sha256=binding,
        actor_id="owner",
        action_id="approve-action-1",
    )
    mark_manual_ready(
        db,
        work_item_id="work-1",
        approval_id="approval-1",
        actor_id="owner",
        operation_key="manual-ready-1",
    )


def test_manual_ready_replay_is_idempotent_and_conflict_fails(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        now = utc_now()
        db.execute("INSERT INTO owned_accounts VALUES ('acct-1','x','12345','DiscrepancyDesk',1)")
        db.execute("INSERT INTO work_items VALUES ('work-1','captured','Test',?,?)", (now, now))
        db.commit()
        transition_work_item(db, "work-1", "drafting", actor_id="owner")
        transition_work_item(db, "work-1", "human_review_needed", actor_id="owner")
        binding = create_revision(
            db,
            revision_id="rev-1",
            work_item_id="work-1",
            owned_account_id="acct-1",
            bundle=RevisionBundle("x", "acct-1", "Approved"),
        )
        approve_revision(
            db,
            approval_id="approval-1",
            revision_id="rev-1",
            binding_sha256=binding,
            actor_id="owner",
            action_id="approve-1",
        )
        assert mark_manual_ready(
            db,
            work_item_id="work-1",
            approval_id="approval-1",
            actor_id="owner",
            operation_key="ready-key",
        ) == "work-1"
        audit_count = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        assert mark_manual_ready(
            db,
            work_item_id="work-1",
            approval_id="approval-1",
            actor_id="owner",
            operation_key="ready-key",
        ) == "work-1"
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == audit_count
        with pytest.raises(ValueError, match="conflicting content"):
            mark_manual_ready(
                db,
                work_item_id="different-work",
                approval_id="approval-1",
                actor_id="owner",
                operation_key="ready-key",
            )
    finally:
        db.close()


def test_publication_replay_and_platform_mismatch_fail_closed(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        prepared_publication(db)
        result = record_publication(
            db,
            publication_id="pub-1",
            revision_id="rev-1",
            approval_id="approval-1",
            platform="x",
            owned_account_id="acct-1",
            external_post_id="post-1",
            canonical_url="https://x.com/DiscrepancyDesk/status/post-1",
            actor_id="owner",
            operation_key="publish-key-1",
        )
        assert result == "pub-1"
        audit_count = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        assert record_publication(
            db,
            publication_id="pub-1",
            revision_id="rev-1",
            approval_id="approval-1",
            platform="x",
            owned_account_id="acct-1",
            external_post_id="post-1",
            canonical_url="https://x.com/DiscrepancyDesk/status/post-1",
            actor_id="owner",
            operation_key="publish-key-1",
        ) == "pub-1"
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == audit_count
        assert db.execute("SELECT state FROM work_items WHERE id='work-1'").fetchone()[0] == "published"
        assert db.execute("SELECT decision FROM approvals WHERE id='approval-1'").fetchone()[0] == "consumed"
        assert verify_audit_chain(db)
    finally:
        db.close()

    mismatch = migrate(tmp_path / "mismatch.sqlite3")
    try:
        prepared_publication(mismatch)
        with pytest.raises(ValueError, match="identity or approval binding mismatch"):
            record_publication(
                mismatch,
                publication_id="pub-bad",
                revision_id="rev-1",
                approval_id="approval-1",
                platform="truth_social",
                owned_account_id="acct-1",
                external_post_id="post-bad",
                canonical_url="https://truthsocial.com/@DiscrepancyDesk/posts/post-bad",
                actor_id="owner",
                operation_key="publish-bad",
            )
        assert mismatch.execute("SELECT count(*) FROM publications").fetchone()[0] == 0
        assert mismatch.execute("SELECT state FROM work_items WHERE id='work-1'").fetchone()[0] == "manual_ready"
    finally:
        mismatch.close()


def test_metric_snapshot_replay_conflict_and_correction(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        prepared_publication(db)
        record_publication(
            db,
            publication_id="pub-1",
            revision_id="rev-1",
            approval_id="approval-1",
            platform="x",
            owned_account_id="acct-1",
            external_post_id="post-1",
            canonical_url="https://x.com/DiscrepancyDesk/status/post-1",
            actor_id="owner",
            operation_key="publish-key-1",
        )
        assert record_metric_snapshot(
            db,
            snapshot_id="metric-1",
            publication_id="pub-1",
            observation_method="manual",
            capture_session_id="session-1",
            metric_set_version=1,
            metrics={"likes": 3, "replies": 1},
            observation_state="observed_value",
        ) == "metric-1"
        assert record_metric_snapshot(
            db,
            snapshot_id="metric-1",
            publication_id="pub-1",
            observation_method="manual",
            capture_session_id="session-1",
            metric_set_version=1,
            metrics={"likes": 3, "replies": 1},
            observation_state="observed_value",
        ) == "metric-1"
        with pytest.raises(ValueError, match="conflicting content"):
            record_metric_snapshot(
                db,
                snapshot_id="metric-1",
                publication_id="pub-1",
                observation_method="manual",
                capture_session_id="session-1",
                metric_set_version=1,
                metrics={"likes": 4, "replies": 1},
                observation_state="observed_value",
            )
        assert record_metric_snapshot(
            db,
            snapshot_id="metric-2",
            publication_id="pub-1",
            observation_method="manual",
            capture_session_id="session-2",
            metric_set_version=1,
            metrics={"likes": 4, "replies": 1},
            observation_state="observed_value",
            corrects_snapshot_id="metric-1",
        ) == "metric-2"
        assert db.execute("SELECT count(*) FROM metric_snapshots").fetchone()[0] == 2
    finally:
        db.close()


def test_busy_writer_rejects_cleanly_without_partial_write(tmp_path: Path) -> None:
    path = tmp_path / "desk.sqlite3"
    first = migrate(path)
    second = connect(path)
    try:
        now = utc_now()
        first.execute("INSERT INTO work_items VALUES ('work-1','captured','One',?,?)", (now, now))
        first.commit()
        begin_write(first)
        first.execute("UPDATE work_items SET title='held' WHERE id='work-1'")
        second.execute("PRAGMA busy_timeout=50")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            begin_write(second)
        second.rollback()
        first.rollback()
        assert second.execute("SELECT title FROM work_items WHERE id='work-1'").fetchone()[0] == "One"
    finally:
        second.close()
        first.close()


def test_out_of_band_audit_tamper_is_detected(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        now = utc_now()
        db.execute("INSERT INTO work_items VALUES ('work-1','captured','One',?,?)", (now, now))
        db.commit()
        transition_work_item(db, "work-1", "drafting", actor_id="owner")
        assert verify_audit_chain(db)
        db.execute("DROP TRIGGER audit_events_no_update")
        db.execute("UPDATE audit_events SET payload_json=X'7B7D' WHERE sequence=1")
        db.commit()
        assert not verify_audit_chain(db)
    finally:
        db.close()


def test_dirty_migration_marker_blocks_and_requires_matching_clear(tmp_path: Path) -> None:
    database = tmp_path / "desk.sqlite3"
    assert_clean_migration_state(database)
    marker = begin_migration_guard(database, operation_id="op-1", target_revision="0002")
    assert marker.is_file()
    with pytest.raises(MigrationIntegrityError, match="dirty"):
        assert_clean_migration_state(database)
    with pytest.raises(MigrationIntegrityError, match="operation mismatch"):
        clear_migration_guard(database, operation_id="wrong")
    clear_migration_guard(database, operation_id="op-1")
    assert_clean_migration_state(database)
