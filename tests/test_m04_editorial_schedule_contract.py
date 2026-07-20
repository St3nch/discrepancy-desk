from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import connect
from discrepancy_desk.operator_service import (
    organize_work_item,
    reconcile_publication_result,
    record_manual_metric_observation,
    record_manual_publication_result,
    reschedule_work_item,
    schedule_work_item,
    set_editorial_target,
    set_work_item_tags,
    unschedule_work_item,
)
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    mark_manual_ready,
    transition_work_item,
    utc_now,
    verify_audit_chain,
)


def migrate(db_path: Path):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


def seed(db) -> None:
    now = utc_now()
    db.execute("INSERT INTO owned_accounts VALUES ('acct-1','x','one','DeskOne',1)")
    db.execute("INSERT INTO owned_accounts VALUES ('acct-2','x','two','DeskTwo',1)")
    db.execute("INSERT INTO work_items VALUES ('work-1','captured','Item',?,?)", (now, now))
    db.commit()


def organize(db) -> None:
    organize_work_item(
        db, work_item_id="work-1", account_id="acct-1", lane="archive",
        topic="History", priority=2, operator_notes="note", is_dormant=False,
        actor_id="owner", operation_key="organize-1",
    )


def test_migration_preserves_unassigned_work_and_requires_explicit_account(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed(db)
        assert db.execute("SELECT count(*) FROM editorial_profiles").fetchone()[0] == 0
        with pytest.raises(ValueError, match="organized"):
            schedule_work_item(
                db, schedule_id="sched-1", work_item_id="work-1", account_id="acct-1",
                scheduled_for=None, preferred_window_start=None, preferred_window_end=None,
                earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
                is_evergreen=True, actor_id="owner", operation_key="schedule-1",
            )
    finally:
        db.close()


def test_organize_is_account_scoped_idempotent_and_conflict_fails(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed(db)
        organize(db)
        audit_count = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        organize(db)
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == audit_count
        with pytest.raises(ValueError, match="conflicting content"):
            organize_work_item(
                db, work_item_id="work-1", account_id="acct-2", lane="archive",
                topic="History", priority=2, operator_notes="note", is_dormant=False,
                actor_id="owner", operation_key="organize-1",
            )
        with pytest.raises(ValueError, match="cannot be changed"):
            organize_work_item(
                db, work_item_id="work-1", account_id="acct-2", lane="archive",
                topic="History", priority=2, operator_notes="note", is_dormant=False,
                actor_id="owner", operation_key="organize-2",
            )
        assert verify_audit_chain(db)
    finally:
        db.close()


def test_lane_and_tag_contracts(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed(db)
        with pytest.raises(ValueError, match="invalid editorial lane"):
            organize_work_item(
                db, work_item_id="work-1", account_id="acct-1", lane="Archive",
                topic=None, priority=3, operator_notes=None, is_dormant=False,
                actor_id="owner", operation_key="bad-lane",
            )
        organize(db)
        set_work_item_tags(
            db, work_item_id="work-1", account_id="acct-1",
            tags=[" FOIA ", "foia", "History"], actor_id="owner", operation_key="tags-1",
        )
        assert [row[0] for row in db.execute(
            "SELECT tag FROM work_item_tags ORDER BY tag"
        )] == ["foia", "history"]
        with pytest.raises(ValueError, match="account scope mismatch"):
            set_work_item_tags(
                db, work_item_id="work-1", account_id="acct-2", tags=["x"],
                actor_id="owner", operation_key="tags-2",
            )
    finally:
        db.close()


def test_schedule_horizon_history_and_replay(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed(db)
        organize(db)
        now = datetime(2026, 7, 20, 16, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="90-day"):
            schedule_work_item(
                db, schedule_id="too-far", work_item_id="work-1", account_id="acct-1",
                scheduled_for=(now + timedelta(days=90, seconds=1)).isoformat(),
                preferred_window_start=None, preferred_window_end=None,
                earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
                is_evergreen=False, actor_id="owner", operation_key="too-far", now=now,
            )
        boundary = (now + timedelta(days=90)).isoformat()
        assert schedule_work_item(
            db, schedule_id="sched-1", work_item_id="work-1", account_id="acct-1",
            scheduled_for=boundary, preferred_window_start=None, preferred_window_end=None,
            earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
            is_evergreen=False, actor_id="owner", operation_key="schedule-1", now=now,
        ) == "sched-1"
        audit_count = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        assert schedule_work_item(
            db, schedule_id="sched-1", work_item_id="work-1", account_id="acct-1",
            scheduled_for=boundary, preferred_window_start=None, preferred_window_end=None,
            earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
            is_evergreen=False, actor_id="owner", operation_key="schedule-1", now=now,
        ) == "sched-1"
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == audit_count
        assert reschedule_work_item(
            db, schedule_id="sched-2", prior_schedule_id="sched-1", account_id="acct-1",
            scheduled_for=(now + timedelta(days=10)).isoformat(),
            preferred_window_start=None, preferred_window_end=None, earliest_useful_at=None,
            stale_after=None, hard_deadline_at=None, is_evergreen=False,
            actor_id="owner", operation_key="reschedule-1", now=now,
        ) == "sched-2"
        assert db.execute("SELECT status FROM schedule_slots WHERE id='sched-1'").fetchone()[0] == "superseded"
        assert unschedule_work_item(
            db, schedule_id="sched-3", prior_schedule_id="sched-2", account_id="acct-1",
            actor_id="owner", operation_key="unschedule-1",
        ) == "sched-3"
        rows = db.execute(
            "SELECT id,status,supersedes_schedule_id FROM schedule_slots ORDER BY id"
        ).fetchall()
        assert [(r[0], r[1], r[2]) for r in rows] == [
            ("sched-1", "superseded", None),
            ("sched-2", "superseded", "sched-1"),
            ("sched-3", "unscheduled", "sched-2"),
        ]
    finally:
        db.close()


def test_invalid_dates_dormancy_and_target_contract(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed(db)
        organize(db)
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="window"):
            schedule_work_item(
                db, schedule_id="bad", work_item_id="work-1", account_id="acct-1",
                scheduled_for=None,
                preferred_window_start=(now + timedelta(days=2)).isoformat(),
                preferred_window_end=(now + timedelta(days=1)).isoformat(),
                earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
                is_evergreen=True, actor_id="owner", operation_key="bad-window", now=now,
            )
        organize_work_item(
            db, work_item_id="work-1", account_id="acct-1", lane="archive",
            topic=None, priority=3, operator_notes=None, is_dormant=True,
            actor_id="owner", operation_key="dormant-1",
        )
        with pytest.raises(ValueError, match="dormant"):
            schedule_work_item(
                db, schedule_id="dormant", work_item_id="work-1", account_id="acct-1",
                scheduled_for=None, preferred_window_start=None, preferred_window_end=None,
                earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
                is_evergreen=True, actor_id="owner", operation_key="dormant-schedule", now=now,
            )
        assert set_editorial_target(
            db, target_id="target-1", account_id="acct-1", target_kind="impressions",
            window_days=90, target_value=5_000_000, effective_from=now.isoformat(),
            effective_until=None, source_note="Owner-entered dated target",
            actor_id="owner", operation_key="target-1",
        ) == "target-1"
    finally:
        db.close()


def test_manual_publication_reconciliation_and_metric_wrappers(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed(db)
        organize(db)
        transition_work_item(db, "work-1", "drafting", actor_id="owner")
        transition_work_item(db, "work-1", "human_review_needed", actor_id="owner")
        binding = create_revision(
            db,
            revision_id="rev-1",
            work_item_id="work-1",
            owned_account_id="acct-1",
            bundle=RevisionBundle("x", "acct-1", "Approved text"),
        )
        approve_revision(
            db,
            approval_id="approval-1",
            revision_id="rev-1",
            binding_sha256=binding,
            actor_id="owner",
            action_id="approve-1",
        )
        mark_manual_ready(
            db,
            work_item_id="work-1",
            approval_id="approval-1",
            actor_id="owner",
            operation_key="ready-1",
        )
        assert record_manual_publication_result(
            db,
            publication_id="pub-1",
            revision_id="rev-1",
            approval_id="approval-1",
            platform="x",
            account_id="acct-1",
            external_post_id="post-1",
            canonical_url="https://x.com/DiscrepancyDesk/status/post-1",
            matched=True,
            mismatch_reason=None,
            actor_id="owner",
            operation_key="publish-1",
        ) == "pub-1"
        assert reconcile_publication_result(
            db,
            publication_id="pub-1",
            account_id="acct-1",
            matched=True,
            mismatch_reason=None,
            actor_id="owner",
            operation_key="reconcile-1",
        ) == "pub-1"
        assert db.execute(
            "SELECT verification_state FROM publications WHERE id='pub-1'"
        ).fetchone()[0] == "verified_match"
        assert record_manual_metric_observation(
            db,
            snapshot_id="metric-1",
            publication_id="pub-1",
            account_id="acct-1",
            capture_session_id="manual-session-1",
            metric_set_version=1,
            metrics={"impressions": 100},
            observation_state="observed_value",
            actor_id="owner",
            operation_key="metric-1",
        ) == "metric-1"
        with pytest.raises(ValueError, match="account mismatch"):
            record_manual_metric_observation(
                db,
                snapshot_id="metric-2",
                publication_id="pub-1",
                account_id="acct-2",
                capture_session_id="manual-session-2",
                metric_set_version=1,
                metrics={"impressions": 200},
                observation_state="observed_value",
                actor_id="owner",
                operation_key="metric-2",
            )
        assert verify_audit_chain(db)
    finally:
        db.close()
