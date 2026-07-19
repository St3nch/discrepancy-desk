from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.binding import RevisionBundle, revision_binding
from discrepancy_desk.db import connect
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    register_evidence,
    transition_work_item,
    utc_now,
    verify_audit_chain,
)


def migrate(db_path: Path) -> sqlite3.Connection:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    connection = migrate(tmp_path / "desk.sqlite3")
    now = utc_now()
    connection.execute(
        "INSERT INTO owned_accounts VALUES (?, 'x', ?, ?, 1)",
        ("acct-1", "12345", "DiscrepancyDesk"),
    )
    connection.execute(
        "INSERT INTO work_items VALUES (?, 'captured', ?, ?, ?)",
        ("work-1", "Test item", now, now),
    )
    connection.commit()
    yield connection
    connection.close()


def test_connection_contract(db: sqlite3.Connection) -> None:
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_foreign_keys_reject_fabricated_identity(db: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO revisions
            (id, work_item_id, platform, owned_account_id, authored_text, component_json,
             binding_version, binding_sha256, created_at)
            VALUES ('bad', 'missing', 'x', 'acct-1', X'00', X'00', 1, ?, ?)""",
            ("0" * 64, utc_now()),
        )


def test_exact_binding_changes_for_whitespace_unicode_and_platform() -> None:
    base = RevisionBundle("x", "acct-1", "Line one\nLine two")
    variants = [
        RevisionBundle("x", "acct-1", "Line one\r\nLine two"),
        RevisionBundle("x", "acct-1", "Line one\nLine two "),
        RevisionBundle("x", "acct-1", "Line one\nLine\u200b two"),
        RevisionBundle("truth_social", "acct-1", "Line one\nLine two"),
    ]
    assert len({revision_binding(base), *(revision_binding(v) for v in variants)}) == 5


def test_illegal_transition_rolls_back_without_audit(db: sqlite3.Connection) -> None:
    before = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    with pytest.raises(ValueError, match="illegal transition"):
        transition_work_item(db, "work-1", "published", actor_id="owner")
    assert db.execute("SELECT state FROM work_items WHERE id='work-1'").fetchone()[0] == "captured"
    assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == before


def test_legal_transition_is_atomic_and_audited(db: sqlite3.Connection) -> None:
    transition_work_item(db, "work-1", "drafting", actor_id="owner")
    assert db.execute("SELECT state FROM work_items WHERE id='work-1'").fetchone()[0] == "drafting"
    assert verify_audit_chain(db)


def test_evidence_hash_and_path_fail_closed(db: sqlite3.Connection, tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    evidence = root / "capture.json"
    evidence.write_bytes(b'{"ok":true}\n')
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="hash mismatch"):
        register_evidence(
            db,
            root,
            evidence_id="ev-bad",
            work_item_id="work-1",
            relative_path="capture.json",
            expected_sha256="0" * 64,
        )

    register_evidence(
        db,
        root,
        evidence_id="ev-1",
        work_item_id="work-1",
        relative_path="capture.json",
        expected_sha256=digest,
    )
    assert verify_audit_chain(db)

    with pytest.raises(ValueError, match="escapes"):
        register_evidence(
            db,
            root,
            evidence_id="ev-escape",
            work_item_id="work-1",
            relative_path="../outside.json",
            expected_sha256=digest,
        )


def test_stale_approval_binding_is_rejected_atomically(db: sqlite3.Connection) -> None:
    for target in ("drafting", "human_review_needed"):
        transition_work_item(db, "work-1", target, actor_id="owner")
    bundle = RevisionBundle("x", "acct-1", "Approved exact text")
    binding = create_revision(
        db,
        revision_id="rev-1",
        work_item_id="work-1",
        owned_account_id="acct-1",
        bundle=bundle,
    )
    with pytest.raises(ValueError, match="mismatched approval"):
        approve_revision(
            db,
            approval_id="approval-bad",
            revision_id="rev-1",
            binding_sha256="0" * 64,
            actor_id="owner",
            action_id="action-bad",
        )
    assert db.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
    approve_revision(
        db,
        approval_id="approval-1",
        revision_id="rev-1",
        binding_sha256=binding,
        actor_id="owner",
        action_id="action-1",
    )
    assert db.execute("SELECT state FROM work_items WHERE id='work-1'").fetchone()[0] == "approved"
    assert verify_audit_chain(db)


def test_audit_events_are_append_only(db: sqlite3.Connection) -> None:
    transition_work_item(db, "work-1", "drafting", actor_id="owner")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE audit_events SET operation='tampered'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM audit_events")
    assert verify_audit_chain(db)


def test_duplicate_external_publication_identity_is_rejected(db: sqlite3.Connection) -> None:
    for target in ("drafting", "human_review_needed"):
        transition_work_item(db, "work-1", target, actor_id="owner")
    bundle = RevisionBundle("x", "acct-1", "Publish me")
    binding = create_revision(
        db,
        revision_id="rev-pub",
        work_item_id="work-1",
        owned_account_id="acct-1",
        bundle=bundle,
    )
    approve_revision(
        db,
        approval_id="approval-pub",
        revision_id="rev-pub",
        binding_sha256=binding,
        actor_id="owner",
        action_id="action-pub",
    )
    db.execute(
        """INSERT INTO publications
        (id, revision_id, approval_id, platform, owned_account_id, external_post_id,
         canonical_url, verification_state, observed_at)
        VALUES (?, ?, ?, 'x', 'acct-1', 'post-1', ?, 'owner_confirmed', ?)""",
        ("pub-1", "rev-pub", "approval-pub", "https://x.com/DiscrepancyDesk/status/post-1", utc_now()),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO publications
            (id, revision_id, approval_id, platform, owned_account_id, external_post_id,
             canonical_url, verification_state, observed_at)
            VALUES (?, ?, ?, 'x', 'acct-1', 'post-1', ?, 'owner_confirmed', ?)""",
            ("pub-2", "rev-pub", "approval-pub", "https://x.com/DiscrepancyDesk/status/post-1", utc_now()),
        )
