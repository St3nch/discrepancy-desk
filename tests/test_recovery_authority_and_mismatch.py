from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import connect
from discrepancy_desk.migration_integrity import (
    MigrationIntegrityError,
    begin_migration_guard,
    dirty_marker_path,
    discard_failed_empty_migration,
    recover_completed_migration,
)
from discrepancy_desk.migration_spec import central_migration_spec
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    detector_advice,
    mark_manual_ready,
    query_metric_snapshots_by_state,
    record_metric_snapshot,
    record_publication,
    record_publication_mismatch,
    transition_work_item,
    utc_now,
)


def migrate(db_path: Path) -> sqlite3.Connection:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


def seed(connection: sqlite3.Connection, suffix: str = "1") -> None:
    now = utc_now()
    connection.execute(
        "INSERT INTO owned_accounts VALUES (?, 'x', ?, ?, 1)",
        (f"acct-{suffix}", f"account-{suffix}", f"Desk{suffix}"),
    )
    connection.execute(
        "INSERT INTO work_items VALUES (?, 'captured', ?, ?, ?)",
        (f"work-{suffix}", f"Fixture {suffix}", now, now),
    )
    connection.commit()


def ready_revision(connection: sqlite3.Connection, suffix: str = "1") -> tuple[str, str, str]:
    work_id = f"work-{suffix}"
    account_id = f"acct-{suffix}"
    for state in ("drafting", "human_review_needed"):
        transition_work_item(connection, work_id, state, actor_id="owner")
    revision_id = f"revision-{suffix}"
    approval_id = f"approval-{suffix}"
    binding = create_revision(
        connection,
        revision_id=revision_id,
        work_item_id=work_id,
        owned_account_id=account_id,
        bundle=RevisionBundle("x", account_id, f"Exact text {suffix}"),
    )
    approve_revision(
        connection,
        approval_id=approval_id,
        revision_id=revision_id,
        binding_sha256=binding,
        actor_id="owner",
        action_id=f"approval-action-{suffix}",
    )
    mark_manual_ready(
        connection,
        work_item_id=work_id,
        approval_id=approval_id,
        actor_id="owner",
        operation_key=f"ready-{suffix}",
    )
    return work_id, revision_id, approval_id


def test_generic_transition_cannot_bypass_approval_gate(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "authority.sqlite3")
    try:
        seed(connection)
        for state in ("drafting", "human_review_needed"):
            transition_work_item(connection, "work-1", state, actor_id="owner")
        with pytest.raises(ValueError, match="dedicated governed operation"):
            transition_work_item(connection, "work-1", "approved", actor_id="detector")
        assert connection.execute("SELECT state FROM work_items").fetchone()[0] == "human_review_needed"
    finally:
        connection.close()


@pytest.mark.parametrize("outcome", ["flagged", "not_detected", "errored"])
def test_detector_results_are_advisory_and_do_not_change_state(tmp_path: Path, outcome: str) -> None:
    connection = migrate(tmp_path / f"detector-{outcome}.sqlite3")
    try:
        seed(connection)
        advice = detector_advice(
            work_item_id="work-1", detector_name="test-detector", outcome=outcome, detail="fixture"
        )
        assert advice["authority"] == "advisory_only"
        assert connection.execute("SELECT state FROM work_items").fetchone()[0] == "captured"
    finally:
        connection.close()


def test_publication_mismatch_preserves_history_and_requires_reason(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "mismatch.sqlite3")
    try:
        seed(connection)
        work_id, revision_id, approval_id = ready_revision(connection)
        with pytest.raises(ValueError, match="reason"):
            record_publication_mismatch(
                connection,
                publication_id="publication-empty",
                revision_id=revision_id,
                approval_id=approval_id,
                platform="x",
                owned_account_id="acct-1",
                external_post_id="external-empty",
                canonical_url="https://x.com/Desk1/status/external-empty",
                mismatch_reason=" ",
                actor_id="owner",
                operation_key="mismatch-empty",
            )
        publication_id = record_publication_mismatch(
            connection,
            publication_id="publication-1",
            revision_id=revision_id,
            approval_id=approval_id,
            platform="x",
            owned_account_id="acct-1",
            external_post_id="external-1",
            canonical_url="https://x.com/Desk1/status/external-1",
            mismatch_reason="published text omitted final line",
            actor_id="owner",
            operation_key="mismatch-1",
        )
        assert publication_id == "publication-1"
        assert connection.execute("SELECT state FROM work_items WHERE id=?", (work_id,)).fetchone()[0] == "publication_mismatch"
        assert connection.execute("SELECT verification_state FROM publications").fetchone()[0] == "verified_mismatch"
        assert connection.execute("SELECT decision FROM approvals").fetchone()[0] == "consumed"
    finally:
        connection.close()


def test_metric_queries_require_explicit_supported_states(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "metrics.sqlite3")
    try:
        seed(connection)
        _, revision_id, approval_id = ready_revision(connection)
        record_publication(
            connection,
            publication_id="publication-1",
            revision_id=revision_id,
            approval_id=approval_id,
            platform="x",
            owned_account_id="acct-1",
            external_post_id="external-1",
            canonical_url="https://x.com/Desk1/status/external-1",
            actor_id="owner",
            operation_key="publish-1",
        )
        record_metric_snapshot(
            connection,
            snapshot_id="snapshot-value",
            publication_id="publication-1",
            observation_method="manual",
            capture_session_id="session-value",
            metric_set_version=1,
            metrics={"likes": 0},
            observation_state="observed_value",
        )
        record_metric_snapshot(
            connection,
            snapshot_id="snapshot-unavailable",
            publication_id="publication-1",
            observation_method="api",
            capture_session_id="session-unavailable",
            metric_set_version=1,
            metrics={},
            observation_state="unavailable",
        )
        with pytest.raises(ValueError, match="at least one"):
            query_metric_snapshots_by_state(connection, publication_id="publication-1", states=set())
        with pytest.raises(ValueError, match="unsupported"):
            query_metric_snapshots_by_state(connection, publication_id="publication-1", states={"missing"})
        rows = query_metric_snapshots_by_state(
            connection, publication_id="publication-1", states={"unavailable"}
        )
        assert [row["id"] for row in rows] == ["snapshot-unavailable"]
    finally:
        connection.close()


def test_recover_completed_migration_requires_verified_database(tmp_path: Path) -> None:
    database = tmp_path / "completed.sqlite3"
    connection = migrate(database)
    connection.close()
    spec = central_migration_spec(Path(".").resolve())
    begin_migration_guard(
        database,
        operation_id="recover-completed",
        target_revision=spec.expected_head,
        spec=spec,
    )
    recover_completed_migration(database, spec, operation_id="recover-completed")
    assert not dirty_marker_path(database).exists()


def test_completed_recovery_refuses_wrong_operation_and_missing_version(tmp_path: Path) -> None:
    database = tmp_path / "invalid-completed.sqlite3"
    sqlite3.connect(database).close()
    spec = central_migration_spec(Path(".").resolve())
    begin_migration_guard(
        database,
        operation_id="expected",
        target_revision=spec.expected_head,
        spec=spec,
    )
    with pytest.raises(MigrationIntegrityError, match="operation mismatch"):
        recover_completed_migration(database, spec, operation_id="wrong")
    with pytest.raises(MigrationIntegrityError, match="expected head"):
        recover_completed_migration(database, spec, operation_id="expected")
    assert dirty_marker_path(database).exists()


def test_discard_failed_empty_migration_is_bounded(tmp_path: Path) -> None:
    empty_db = tmp_path / "empty.sqlite3"
    sqlite3.connect(empty_db).close()
    begin_migration_guard(empty_db, operation_id="discard-empty", target_revision="head")
    discard_failed_empty_migration(empty_db, operation_id="discard-empty")
    assert not empty_db.exists()
    assert not dirty_marker_path(empty_db).exists()

    nonempty_db = tmp_path / "nonempty.sqlite3"
    raw = sqlite3.connect(nonempty_db)
    raw.execute("CREATE TABLE surviving_data(id TEXT PRIMARY KEY)")
    raw.commit()
    raw.close()
    begin_migration_guard(nonempty_db, operation_id="discard-nonempty", target_revision="head")
    with pytest.raises(MigrationIntegrityError, match="persistent database objects"):
        discard_failed_empty_migration(nonempty_db, operation_id="discard-nonempty")
    assert nonempty_db.exists()
    assert dirty_marker_path(nonempty_db).exists()
