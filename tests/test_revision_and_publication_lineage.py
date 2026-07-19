from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import connect
from discrepancy_desk.operator_service import capture_work_item, create_owned_account
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    create_successor_revision,
    mark_manual_ready,
    record_publication_mismatch,
    record_replacement_publication,
    transition_work_item,
    verify_audit_chain,
)


def migrate(db_path: Path) -> sqlite3.Connection:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


def seed_review(connection: sqlite3.Connection) -> str:
    create_owned_account(
        connection,
        account_id="acct-1",
        platform="x",
        external_account_id="external-1",
        username="Desk",
        operation_key="account-1",
        actor_id="owner",
    )
    capture_work_item(
        connection,
        work_item_id="work-1",
        title="Lineage fixture",
        operation_key="capture-1",
        actor_id="owner",
    )
    transition_work_item(connection, "work-1", "drafting", actor_id="owner")
    binding = create_revision(
        connection,
        revision_id="revision-1",
        work_item_id="work-1",
        owned_account_id="acct-1",
        bundle=RevisionBundle("x", "acct-1", "Original approved text"),
    )
    transition_work_item(connection, "work-1", "human_review_needed", actor_id="owner")
    approve_revision(
        connection,
        approval_id="approval-1",
        revision_id="revision-1",
        binding_sha256=binding,
        actor_id="owner",
        action_id="approve-1",
    )
    return binding


def test_successor_revision_supersedes_active_approval_atomically(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "successor.sqlite3")
    try:
        seed_review(connection)
        binding = create_successor_revision(
            connection,
            revision_id="revision-2",
            predecessor_revision_id="revision-1",
            work_item_id="work-1",
            owned_account_id="acct-1",
            bundle=RevisionBundle("x", "acct-1", "Corrected exact text"),
            actor_id="owner",
        )
        assert len(binding) == 64
        assert connection.execute(
            "SELECT decision FROM approvals WHERE id='approval-1'"
        ).fetchone()[0] == "superseded"
        row = connection.execute(
            "SELECT supersedes_revision_id FROM revisions WHERE id='revision-2'"
        ).fetchone()
        assert row[0] == "revision-1"
        assert connection.execute("SELECT state FROM work_items").fetchone()[0] == "human_review_needed"
        assert verify_audit_chain(connection)
    finally:
        connection.close()


def test_replacement_publication_preserves_mismatch_and_links_resolution(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "replacement.sqlite3")
    try:
        seed_review(connection)
        mark_manual_ready(
            connection,
            work_item_id="work-1",
            approval_id="approval-1",
            actor_id="owner",
            operation_key="ready-1",
        )
        record_publication_mismatch(
            connection,
            publication_id="publication-1",
            revision_id="revision-1",
            approval_id="approval-1",
            platform="x",
            owned_account_id="acct-1",
            external_post_id="post-wrong",
            canonical_url="https://x.invalid/post-wrong",
            mismatch_reason="published text omitted a line",
            actor_id="owner",
            operation_key="mismatch-1",
        )
        successor_binding = create_successor_revision(
            connection,
            revision_id="revision-2",
            predecessor_revision_id="revision-1",
            work_item_id="work-1",
            owned_account_id="acct-1",
            bundle=RevisionBundle("x", "acct-1", "Corrected exact text"),
            actor_id="owner",
        )
        approve_revision(
            connection,
            approval_id="approval-2",
            revision_id="revision-2",
            binding_sha256=successor_binding,
            actor_id="owner",
            action_id="approve-2",
        )
        mark_manual_ready(
            connection,
            work_item_id="work-1",
            approval_id="approval-2",
            actor_id="owner",
            operation_key="ready-2",
        )
        record_replacement_publication(
            connection,
            publication_id="publication-2",
            replaces_publication_id="publication-1",
            revision_id="revision-2",
            approval_id="approval-2",
            platform="x",
            owned_account_id="acct-1",
            external_post_id="post-corrected",
            canonical_url="https://x.invalid/post-corrected",
            actor_id="owner",
            operation_key="replacement-1",
        )
        rows = connection.execute(
            "SELECT id, verification_state, replaces_publication_id, resolution_kind FROM publications ORDER BY observed_at, id"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("publication-1", "verified_mismatch", None, "initial"),
            ("publication-2", "owner_confirmed", "publication-1", "replacement"),
        ]
        assert connection.execute("SELECT state FROM work_items").fetchone()[0] == "published"
        with pytest.raises(ValueError, match="already has a replacement"):
            record_replacement_publication(
                connection,
                publication_id="publication-3",
                replaces_publication_id="publication-1",
                revision_id="revision-2",
                approval_id="approval-2",
                platform="x",
                owned_account_id="acct-1",
                external_post_id="post-duplicate",
                canonical_url="https://x.invalid/post-duplicate",
                actor_id="owner",
                operation_key="replacement-duplicate",
            )
        assert verify_audit_chain(connection)
    finally:
        connection.close()
