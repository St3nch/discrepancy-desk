from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import connect
from discrepancy_desk.editorial_queries import (
    evaluate_ready_to_post,
    get_command_center,
    list_schedule,
    list_unscheduled_reserve,
    recommend_need_a_post,
)
from discrepancy_desk.operator_service import organize_work_item, schedule_work_item
from discrepancy_desk.persistence import approve_revision, create_revision, utc_now


def migrate(db_path: Path):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


def seed_ready(db) -> None:
    now = utc_now()
    db.execute("INSERT INTO owned_accounts VALUES ('acct-1','x','one','DeskOne',1)")
    db.execute("INSERT INTO owned_accounts VALUES ('acct-2','x','two','DeskTwo',1)")
    db.execute("INSERT INTO work_items VALUES ('work-1','human_review_needed','Ready item',?,?)", (now, now))
    db.execute("INSERT INTO work_items VALUES ('work-2','captured','Other account',?,?)", (now, now))
    db.commit()
    organize_work_item(
        db, work_item_id="work-1", account_id="acct-1", lane="archive",
        topic="History", priority=5, operator_notes=None, is_dormant=False,
        actor_id="owner", operation_key="org-1",
    )
    organize_work_item(
        db, work_item_id="work-2", account_id="acct-2", lane="docket",
        topic="Other", priority=1, operator_notes=None, is_dormant=False,
        actor_id="owner", operation_key="org-2",
    )
    binding = create_revision(
        db, revision_id="rev-1", work_item_id="work-1", owned_account_id="acct-1",
        bundle=RevisionBundle("x", "acct-1", "Approved exact text"),
    )
    approve_revision(
        db, approval_id="approval-1", revision_id="rev-1",
        binding_sha256=binding, actor_id="owner", action_id="approve-1",
    )


def test_queries_require_explicit_account_and_isolate_records(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed_ready(db)
        with pytest.raises(ValueError, match="account scope"):
            get_command_center(db, account_id="", now=utc_now())
        center = get_command_center(db, account_id="acct-1", now=utc_now())
        all_ids = {
            str(item["id"])
            for value in center.values()
            if isinstance(value, list)
            for item in value
        }
        assert "work-2" not in all_ids
    finally:
        db.close()


def test_ready_to_post_and_need_a_post_are_deterministic(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed_ready(db)
        now = datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat()
        ready = evaluate_ready_to_post(
            db, work_item_id="work-1", account_id="acct-1", now=now
        )
        assert ready["ready"] is True
        recommendation = recommend_need_a_post(
            db, account_id="acct-1", slot_start=now,
            slot_end=(datetime.fromisoformat(now) + timedelta(hours=1)).isoformat(), now=now,
        )
        assert recommendation["leave_empty"] is False
        assert [row["id"] for row in recommendation["candidates"]] == ["work-1"]
    finally:
        db.close()


def test_schedule_and_reserve_views_agree_with_persisted_truth(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        seed_ready(db)
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        assert [row["id"] for row in list_unscheduled_reserve(db, account_id="acct-1")] == ["work-1"]
        schedule_work_item(
            db, schedule_id="sched-1", work_item_id="work-1", account_id="acct-1",
            scheduled_for=(now + timedelta(days=1)).isoformat(),
            preferred_window_start=None, preferred_window_end=None,
            earliest_useful_at=None, stale_after=None, hard_deadline_at=None,
            is_evergreen=False, actor_id="owner", operation_key="sched-1", now=now,
        )
        assert list_unscheduled_reserve(db, account_id="acct-1") == []
        rows = list_schedule(
            db, account_id="acct-1", start=now.isoformat(),
            end=(now + timedelta(days=2)).isoformat(),
        )
        assert [row["id"] for row in rows] == ["sched-1"]
    finally:
        db.close()


def test_empty_slot_is_an_allowed_result(tmp_path: Path) -> None:
    db = migrate(tmp_path / "desk.sqlite3")
    try:
        now = datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat()
        db.execute("INSERT INTO owned_accounts VALUES ('acct-1','x','one','DeskOne',1)")
        db.commit()
        result = recommend_need_a_post(
            db, account_id="acct-1", slot_start=now,
            slot_end=(datetime.fromisoformat(now) + timedelta(hours=1)).isoformat(), now=now,
        )
        assert result["leave_empty"] is True
        assert result["candidates"] == []
    finally:
        db.close()
