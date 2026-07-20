from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import connect
from discrepancy_desk.editorial_queries import evaluate_ready_to_post, recommend_need_a_post
from discrepancy_desk.operator_service import (
    organize_work_item,
    record_manual_metric_observation,
    record_manual_publication_result,
    reconcile_publication_result,
    reschedule_work_item,
    schedule_work_item,
    unschedule_work_item,
)
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    create_successor_revision,
    mark_manual_ready,
    record_replacement_publication,
    transition_work_item,
    utc_now,
    verify_audit_chain,
)


def migrate(path: Path):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(path)


def add_work(db, work_id: str, account_id: str, lane: str, title: str) -> None:
    now = utc_now()
    db.execute("INSERT INTO work_items VALUES (?, 'captured', ?, ?, ?)", (work_id, title, now, now))
    db.commit()
    organize_work_item(
        db,
        work_item_id=work_id,
        account_id=account_id,
        lane=lane,
        topic=title,
        priority=3,
        operator_notes=None,
        is_dormant=False,
        actor_id="owner",
        operation_key=f"organize:{work_id}",
    )


def approve_text(db, work_id: str, account_id: str, revision_id: str, approval_id: str, text: str) -> None:
    transition_work_item(db, work_id, "drafting", actor_id="owner")
    transition_work_item(db, work_id, "human_review_needed", actor_id="owner")
    binding = create_revision(
        db,
        revision_id=revision_id,
        work_item_id=work_id,
        owned_account_id=account_id,
        bundle=RevisionBundle("x", account_id, text),
    )
    approve_revision(
        db,
        approval_id=approval_id,
        revision_id=revision_id,
        binding_sha256=binding,
        actor_id="owner",
        action_id=f"approve:{approval_id}",
    )


def test_two_account_three_lane_editorial_week_and_correction_loop(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        db.execute("INSERT INTO owned_accounts VALUES ('acct-a','x','a','DeskA',1)")
        db.execute("INSERT INTO owned_accounts VALUES ('acct-b','x','b','DeskB',1)")
        db.commit()
        add_work(db, "archive-1", "acct-a", "archive", "Archive filing")
        add_work(db, "docket-1", "acct-a", "docket", "Docket filing")
        add_work(db, "flash-1", "acct-b", "flash_release", "Flash filing")
        add_work(db, "empty-1", "acct-b", "archive", "Unapproved reserve")

        approve_text(db, "archive-1", "acct-a", "rev-a1", "app-a1", "Archive exact text")
        approve_text(db, "docket-1", "acct-a", "rev-d1", "app-d1", "Docket exact text")
        approve_text(db, "flash-1", "acct-b", "rev-f1", "app-f1", "Flash exact text")

        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        schedule_work_item(
            db,
            schedule_id="sched-a1",
            work_item_id="archive-1",
            account_id="acct-a",
            scheduled_for=(now + timedelta(days=3)).isoformat(),
            preferred_window_start=None,
            preferred_window_end=None,
            earliest_useful_at=None,
            stale_after=None,
            hard_deadline_at=None,
            is_evergreen=False,
            actor_id="owner",
            operation_key="sched:a1",
            now=now,
        )
        assert reschedule_work_item(
            db,
            schedule_id="sched-a2",
            prior_schedule_id="sched-a1",
            account_id="acct-a",
            scheduled_for=(now + timedelta(days=1)).isoformat(),
            preferred_window_start=None,
            preferred_window_end=None,
            earliest_useful_at=None,
            stale_after=None,
            hard_deadline_at=None,
            is_evergreen=False,
            actor_id="owner",
            operation_key="resched:a1",
            now=now,
        ) == "sched-a2"
        assert db.execute("SELECT approved_revision_id FROM schedule_slots WHERE id='sched-a2'").fetchone()[0] == "rev-a1"
        assert db.execute("SELECT decision FROM approvals WHERE id='app-a1'").fetchone()[0] == "approved"

        schedule_work_item(
            db,
            schedule_id="sched-d1",
            work_item_id="docket-1",
            account_id="acct-a",
            scheduled_for=(now + timedelta(days=5)).isoformat(),
            preferred_window_start=None,
            preferred_window_end=None,
            earliest_useful_at=None,
            stale_after=None,
            hard_deadline_at=None,
            is_evergreen=False,
            actor_id="owner",
            operation_key="sched:d1",
            now=now,
        )
        unschedule_work_item(
            db,
            schedule_id="sched-d2",
            prior_schedule_id="sched-d1",
            account_id="acct-a",
            actor_id="owner",
            operation_key="unsched:d1",
        )

        assert evaluate_ready_to_post(
            db,
            work_item_id="archive-1",
            account_id="acct-a",
            now=now.isoformat(),
        )["ready"] is True

        successor_binding = create_successor_revision(
            db,
            revision_id="rev-d2",
            predecessor_revision_id="rev-d1",
            work_item_id="docket-1",
            owned_account_id="acct-a",
            bundle=RevisionBundle("x", "acct-a", "Changed docket text"),
            actor_id="owner",
        )
        assert successor_binding
        assert db.execute("SELECT decision FROM approvals WHERE id='app-d1'").fetchone()[0] == "superseded"
        assert evaluate_ready_to_post(
            db,
            work_item_id="docket-1",
            account_id="acct-a",
            now=now.isoformat(),
        )["ready"] is False

        mark_manual_ready(
            db,
            work_item_id="archive-1",
            approval_id="app-a1",
            actor_id="owner",
            operation_key="ready:a1",
        )
        assert record_manual_publication_result(
            db,
            publication_id="pub-a1",
            revision_id="rev-a1",
            approval_id="app-a1",
            platform="x",
            account_id="acct-a",
            external_post_id="post-a1",
            canonical_url="https://x.com/DeskA/status/post-a1",
            matched=True,
            mismatch_reason=None,
            actor_id="owner",
            operation_key="pub:a1",
        ) == "pub-a1"
        assert reconcile_publication_result(
            db,
            publication_id="pub-a1",
            account_id="acct-a",
            matched=True,
            mismatch_reason=None,
            actor_id="owner",
            operation_key="reconcile:a1",
        ) == "pub-a1"
        assert record_manual_metric_observation(
            db,
            snapshot_id="metric-a1",
            publication_id="pub-a1",
            account_id="acct-a",
            capture_session_id="manual:a1",
            metric_set_version=1,
            metrics={},
            observation_state="unavailable",
            actor_id="owner",
            operation_key="metric:a1",
        ) == "metric-a1"

        mark_manual_ready(
            db,
            work_item_id="flash-1",
            approval_id="app-f1",
            actor_id="owner",
            operation_key="ready:f1",
        )
        assert record_manual_publication_result(
            db,
            publication_id="pub-f1",
            revision_id="rev-f1",
            approval_id="app-f1",
            platform="x",
            account_id="acct-b",
            external_post_id="post-f1",
            canonical_url="https://x.com/DeskB/status/post-f1",
            matched=False,
            mismatch_reason="published bytes differ",
            actor_id="owner",
            operation_key="pub:f1",
        ) == "pub-f1"
        binding_f2 = create_successor_revision(
            db,
            revision_id="rev-f2",
            predecessor_revision_id="rev-f1",
            work_item_id="flash-1",
            owned_account_id="acct-b",
            bundle=RevisionBundle("x", "acct-b", "Corrected flash text"),
            actor_id="owner",
        )
        approve_revision(
            db,
            approval_id="app-f2",
            revision_id="rev-f2",
            binding_sha256=binding_f2,
            actor_id="owner",
            action_id="approve:app-f2",
        )
        mark_manual_ready(
            db,
            work_item_id="flash-1",
            approval_id="app-f2",
            actor_id="owner",
            operation_key="ready:f2",
        )
        assert record_replacement_publication(
            db,
            publication_id="pub-f2",
            replaces_publication_id="pub-f1",
            revision_id="rev-f2",
            approval_id="app-f2",
            platform="x",
            owned_account_id="acct-b",
            external_post_id="post-f2",
            canonical_url="https://x.com/DeskB/status/post-f2",
            actor_id="owner",
            operation_key="pub:f2",
        ) == "pub-f2"
        assert record_manual_metric_observation(
            db,
            snapshot_id="metric-f2",
            publication_id="pub-f2",
            account_id="acct-b",
            capture_session_id="manual:f2",
            metric_set_version=1,
            metrics={"detail": "capture failed"},
            observation_state="errored",
            actor_id="owner",
            operation_key="metric:f2",
        ) == "metric-f2"

        empty = recommend_need_a_post(
            db,
            account_id="acct-b",
            slot_start=now.isoformat(),
            slot_end=(now + timedelta(hours=2)).isoformat(),
            now=now.isoformat(),
        )
        assert empty["leave_empty"] is True
        assert empty["candidates"] == []

        audit_count = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        assert record_manual_publication_result(
            db,
            publication_id="pub-a1",
            revision_id="rev-a1",
            approval_id="app-a1",
            platform="x",
            account_id="acct-a",
            external_post_id="post-a1",
            canonical_url="https://x.com/DeskA/status/post-a1",
            matched=True,
            mismatch_reason=None,
            actor_id="owner",
            operation_key="pub:a1",
        ) == "pub-a1"
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == audit_count
        assert verify_audit_chain(db)
    finally:
        db.close()
