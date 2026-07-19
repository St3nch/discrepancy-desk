from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from discrepancy_desk.archive import create_deterministic_zip, package_and_encrypt_generation
from discrepancy_desk.migration_integrity import MigrationIntegrityError, dirty_marker_path
from discrepancy_desk.migration_runner import run_guarded_upgrade
from discrepancy_desk.test_evidence import TestEvidenceInput, write_test_evidence


def test_guarded_migration_success_clears_dirty_marker(tmp_path: Path) -> None:
    database = tmp_path / "guarded.sqlite3"
    run_guarded_upgrade(database, Path("migrations"), operation_id="migration-1")
    assert database.is_file()
    assert not dirty_marker_path(database).exists()
    raw = sqlite3.connect(database)
    try:
        assert raw.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0003"
    finally:
        raw.close()


def test_guarded_migration_failure_retains_dirty_marker(tmp_path: Path) -> None:
    database = tmp_path / "failed.sqlite3"
    with pytest.raises(Exception):
        run_guarded_upgrade(
            database,
            Path("migrations"),
            operation_id="migration-fail",
            target_revision="missing-revision",
        )
    marker = dirty_marker_path(database)
    assert marker.is_file()
    with pytest.raises(MigrationIntegrityError, match="dirty"):
        run_guarded_upgrade(database, Path("migrations"), operation_id="retry")


def test_deterministic_zip_is_byte_identical(tmp_path: Path) -> None:
    source = tmp_path / "generation"
    source.mkdir()
    (source / "b.txt").write_bytes(b"b")
    (source / "a.txt").write_bytes(b"a")
    first = create_deterministic_zip(source, tmp_path / "first.zip")
    second = create_deterministic_zip(source, tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()


def test_age_encryption_and_manifest(tmp_path: Path) -> None:
    age = shutil.which("age")
    age_keygen = shutil.which("age-keygen")
    if not age or not age_keygen:
        pytest.skip("age tools unavailable")
    key_file = tmp_path / "identity.txt"
    generated = subprocess.run(
        [age_keygen, "-o", str(key_file)], capture_output=True, text=True, check=True
    )
    recipient_line = next(
        line for line in generated.stderr.splitlines() if "Public key:" in line
    )
    recipient = recipient_line.split("Public key:", 1)[1].strip()
    generation = tmp_path / "generation"
    generation.mkdir()
    (generation / "manifest.json").write_text("{}\n", encoding="utf-8")
    result = package_and_encrypt_generation(
        generation,
        tmp_path / "archives",
        recipient=recipient,
        age_executable=age,
    )
    assert result.encrypted_path.is_file()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["encrypted"]["sha256"] == hashlib.sha256(
        result.encrypted_path.read_bytes()
    ).hexdigest()
    decrypted = tmp_path / "decrypted.zip"
    subprocess.run(
        [age, "-d", "-i", str(key_file), "-o", str(decrypted), str(result.encrypted_path)],
        check=True,
    )
    assert decrypted.read_bytes() == result.zip_path.read_bytes()


def test_age_failure_removes_partial_output(tmp_path: Path) -> None:
    generation = tmp_path / "generation"
    generation.mkdir()
    (generation / "data.txt").write_text("data", encoding="utf-8")
    with pytest.raises(RuntimeError, match="age encryption failed"):
        package_and_encrypt_generation(
            generation,
            tmp_path / "archives",
            recipient="not-a-valid-recipient",
            age_executable=shutil.which("age") or "age",
        )
    assert not any((tmp_path / "archives").glob("*.age"))


def test_test_evidence_is_deterministic_and_hashes_attachments(tmp_path: Path) -> None:
    attachment = tmp_path / "result.txt"
    attachment.write_bytes(b"22 passed\n")
    evidence = TestEvidenceInput(
        invariant_id="HT-17",
        fixture_id="dirty-migration-001",
        fixture_version="1",
        command="uv run pytest",
        commit_sha="abc123",
        sqlite_version=sqlite3.sqlite_version,
        python_version=sys.version.split()[0],
        expected_result="fail closed",
        actual_result="failed closed",
        passed=True,
    )
    first = write_test_evidence(tmp_path / "first.json", evidence, attachments=(attachment,))
    second = write_test_evidence(tmp_path / "second.json", evidence, attachments=(attachment,))
    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["attachments"][0]["sha256"] == hashlib.sha256(b"22 passed\n").hexdigest()
