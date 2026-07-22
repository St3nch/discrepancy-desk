from __future__ import annotations

import hashlib
import sqlite3
import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.backup import create_generation, verify_generation
from discrepancy_desk.binding import RevisionBundle
from discrepancy_desk.db import connect
from discrepancy_desk.migration_integrity import MigrationIntegrityError, verify_manifest
from discrepancy_desk.migration_spec import central_migration_spec
from discrepancy_desk.persistence import (
    approve_revision,
    create_revision,
    register_evidence,
    transition_work_item,
    utc_now,
)


def migrate(db_path: Path) -> sqlite3.Connection:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    return connect(db_path)


def seed(connection: sqlite3.Connection) -> None:
    now = utc_now()
    connection.execute(
        "INSERT INTO owned_accounts VALUES (?, 'x', ?, ?, 1)",
        ("acct-1", "12345", "DiscrepancyDesk"),
    )
    connection.execute(
        "INSERT INTO work_items VALUES (?, 'captured', ?, ?, ?)",
        ("work-1", "Restore fixture", now, now),
    )
    connection.commit()


def test_migration_manifest_verifies() -> None:
    verify_manifest(central_migration_spec(Path(".").resolve()))


def test_modified_migration_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    root = project / "migrations"
    shutil.copytree(Path("migrations"), root)
    shutil.copy2(Path("alembic.ini"), project / "alembic.ini")
    original = root / "versions" / "0001_initial_persistence.py"
    original.write_bytes(original.read_bytes() + b"\n# tampered\n")
    with pytest.raises(MigrationIntegrityError, match="hash mismatch"):
        verify_manifest(central_migration_spec(project, root))


def test_approval_wrong_state_rolls_back_even_after_prior_changes(tmp_path: Path) -> None:
    connection = migrate(tmp_path / "state.sqlite3")
    try:
        seed(connection)
        bundle = RevisionBundle("x", "acct-1", "Not review-ready")
        binding = create_revision(
            connection,
            revision_id="rev-1",
            work_item_id="work-1",
            owned_account_id="acct-1",
            bundle=bundle,
        )
        with pytest.raises(ValueError, match="human_review_needed"):
            approve_revision(
                connection,
                approval_id="approval-1",
                revision_id="rev-1",
                binding_sha256=binding,
                actor_id="owner",
                action_id="action-1",
            )
        assert connection.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert connection.execute("SELECT state FROM work_items").fetchone()[0] == "captured"
    finally:
        connection.close()


def test_backup_restore_verifies_database_evidence_and_audit(tmp_path: Path) -> None:
    database = tmp_path / "live.sqlite3"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "capture.json").write_bytes(b'{"fixture":"owned"}\n')

    connection = migrate(database)
    try:
        seed(connection)
        register_evidence(
            connection,
            evidence,
            evidence_id="evidence-1",
            work_item_id="work-1",
            relative_path="capture.json",
            expected_sha256=hashlib.sha256((evidence / "capture.json").read_bytes()).hexdigest(),
        )
        transition_work_item(connection, "work-1", "drafting", actor_id="owner")
    finally:
        connection.close()

    result = create_generation(database, evidence, tmp_path / "backups")
    verify_generation(result.generation_root)


def test_backup_tamper_is_rejected(tmp_path: Path) -> None:
    database = tmp_path / "live.sqlite3"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "capture.json").write_bytes(b"original")

    connection = migrate(database)
    try:
        seed(connection)
        register_evidence(
            connection,
            evidence,
            evidence_id="evidence-1",
            work_item_id="work-1",
            relative_path="capture.json",
            expected_sha256=hashlib.sha256((evidence / "capture.json").read_bytes()).hexdigest(),
        )
    finally:
        connection.close()

    result = create_generation(database, evidence, tmp_path / "backups")
    copied_evidence = result.generation_root / "evidence" / "capture.json"
    copied_evidence.write_bytes(b"modified")
    with pytest.raises(ValueError, match="backup (size|hash) mismatch"):
        verify_generation(result.generation_root)


def test_restore_rejects_orphan_evidence(tmp_path: Path) -> None:
    database = tmp_path / "live.sqlite3"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "orphan.json").write_bytes(b"orphan")

    connection = migrate(database)
    try:
        seed(connection)
    finally:
        connection.close()

    result = create_generation(database, evidence, tmp_path / "backups")
    with pytest.raises(ValueError, match="orphan evidence"):
        verify_generation(result.generation_root)


def test_restore_rejects_database_hash_disagreement(tmp_path: Path) -> None:
    database = tmp_path / "live.sqlite3"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    source = evidence / "capture.json"
    source.write_bytes(b"canonical")

    connection = migrate(database)
    try:
        seed(connection)
        register_evidence(
            connection,
            evidence,
            evidence_id="evidence-1",
            work_item_id="work-1",
            relative_path="capture.json",
            expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
    finally:
        connection.close()

    result = create_generation(database, evidence, tmp_path / "backups")
    restored_db = result.generation_root / "database" / "discrepancy-desk.sqlite3"
    raw = sqlite3.connect(restored_db)
    try:
        raw.execute("UPDATE evidence_refs SET sha256=? WHERE id='evidence-1'", ("0" * 64,))
        raw.commit()
    finally:
        raw.close()

    manifest = result.manifest_path
    data = __import__("json").loads(manifest.read_text(encoding="utf-8"))
    for entry in data["files"]:
        if entry["path"] == "database/discrepancy-desk.sqlite3":
            entry["sha256"] = hashlib.sha256(restored_db.read_bytes()).hexdigest()
            entry["byte_size"] = restored_db.stat().st_size
    manifest.write_text(__import__("json").dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="database/evidence hash disagreement"):
        verify_generation(result.generation_root)
