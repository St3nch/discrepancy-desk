from __future__ import annotations

from pathlib import Path

import pytest

from discrepancy_desk import parser_service as parser_service_module
from discrepancy_desk import vault_filesystem as vault_filesystem_module
from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.parser_service import (
    TEXT_ADMISSION_CONFIRMATION,
    admit_text_parser,
    canonical_parse_text,
    list_canonical_documents,
    text_admission_manifest,
)
from discrepancy_desk.vault_backup import (
    create_vault_generation,
    restore_generation_disposable,
    verify_vault_generation,
)
from discrepancy_desk.vault_ingestion import admit_bytes, start_intake


def _actor(vault_id: str, key: str) -> ActorContext:
    return ActorContext(
        actor_id="owner-local",
        actor_class="human",
        vault_account_id=vault_id,
        correlation_id=key,
        authentication_source="pytest",
        allowed_operation_class="vault_admin",
    )


def _admit_parser(opened, key: str = "admit:canonical") -> str:
    result = admit_text_parser(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, key),
        operation_key=key,
        confirmation_text=TEXT_ADMISSION_CONFIRMATION,
        expected_manifest=text_admission_manifest(),
    )
    return result.parser_admission_version_id


def _artifact(opened, *, key: str, content: bytes) -> tuple[str, str]:
    start = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, f"intake:{key}"),
        source_kind="manual_file",
        descriptor_class="file",
        display_label=f"{key}.txt",
        locator=None,
        platform_label="local",
        retention_classification="preservation_compatible",
        policy_basis_reference="D039 synthetic canonical fixture",
        human_classification_note="disposable canonical proof",
        client_nonce=f"nonce:{key}",
        operation_key=f"intake:{key}",
        expects_bytes=True,
        supplied_filename=f"{key}.txt",
        supplied_media_type="text/plain",
        advisory_byte_size=len(content),
    )
    assert start.acquisition_id and start.upload_authorization_id
    admitted = admit_bytes(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, f"upload:{key}"),
        acquisition_id=start.acquisition_id,
        upload_authorization_id=start.upload_authorization_id,
        operation_key=f"upload:{key}",
        content=content,
        supplied_filename=f"{key}.txt",
        supplied_media_type="text/plain",
    )
    row = opened.connection.execute(
        "SELECT id FROM acquisition_artifact_links WHERE acquisition_id=?",
        (start.acquisition_id,),
    ).fetchone()
    assert row is not None
    return str(row[0]), admitted.sha256


def _parse(opened, link_id: str, admission_id: str, key: str):
    return canonical_parse_text(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, key),
        acquisition_artifact_link_id=link_id,
        operation_key=key,
        expected_parser_admission_version_id=admission_id,
    )


def test_m06a_text_canon_012_same_vault_and_admission_gate(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="gate", content=b"alpha\n")
    with pytest.raises(PermissionError):
        _parse(opened, link_id, text_admission_manifest()["parser_admission_version_id"], "parse:before")
    admission_id = _admit_parser(opened)
    with pytest.raises(ValueError):
        _parse(opened, "foreign-link", admission_id, "parse:foreign")


def test_m06a_text_canon_013_artifact_hash_verification(
    m06a_phase3a_vault, monkeypatch
):
    _, opened = m06a_phase3a_vault
    original = b"alpha\n"
    link_id, artifact_sha = _artifact(opened, key="tamper", content=original)
    admission_id = _admit_parser(opened)
    row = opened.connection.execute(
        "SELECT storage_relative_path FROM artifact_objects WHERE sha256=?",
        (artifact_sha,),
    ).fetchone()
    assert row is not None
    artifact_path = opened.root / str(row[0])
    artifact_path.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        _parse(opened, link_id, admission_id, "parse:tamper")
    artifact_path.write_bytes(original)
    real_is_reparse = vault_filesystem_module._is_reparse
    monkeypatch.setattr(
        vault_filesystem_module,
        "_is_reparse",
        lambda path: path == artifact_path or real_is_reparse(path),
    )
    with pytest.raises(ValueError, match="reparse"):
        _parse(opened, link_id, admission_id, "parse:reparse")
    assert opened.connection.execute("SELECT count(*) FROM parser_executions").fetchone()[0] == 0


def test_m06a_text_canon_014_worker_launches_only_after_admission(
    m06a_phase3a_vault, monkeypatch
):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="launch", content=b"alpha\n")
    launched = False

    def forbidden(*args, **kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("worker must not launch")

    monkeypatch.setattr(parser_service_module, "run_under_test_worker", forbidden)
    with pytest.raises(PermissionError):
        _parse(opened, link_id, text_admission_manifest()["parser_admission_version_id"], "parse:no-admit")
    assert launched is False


def test_m06a_text_canon_015_source_worker_canonical_execution(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    content = b"alpha\r\n\r\nbeta\r\n"
    link_id, _ = _artifact(opened, key="source", content=content)
    admission_id = _admit_parser(opened)
    result = _parse(opened, link_id, admission_id, "parse:source")
    assert result.state in {"succeeded", "succeeded_with_warnings"}
    assert result.package_sha256
    assert result.normalized_package_id
    assert result.document_version_id


def test_m06a_text_canon_017_deterministic_package_and_coverage(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="determinism", content=b"alpha\n\nbeta\n")
    admission_id = _admit_parser(opened)
    first = _parse(opened, link_id, admission_id, "parse:determinism:1")
    second = _parse(opened, link_id, admission_id, "parse:determinism:2")
    assert first.package_sha256 == second.package_sha256
    assert opened.connection.execute(
        "SELECT count(*) FROM normalized_packages"
    ).fetchone()[0] == 1


def test_m06a_text_canon_018_failure_creates_no_package_or_document(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="failure", content=b"alpha\x00beta")
    admission_id = _admit_parser(opened)
    result = _parse(opened, link_id, admission_id, "parse:failure")
    assert result.state == "failed"
    assert result.package_sha256 is None
    assert opened.connection.execute("SELECT count(*) FROM normalized_packages").fetchone()[0] == 0
    assert opened.connection.execute("SELECT count(*) FROM document_versions").fetchone()[0] == 0



def test_m06a_text_canon_018_parent_worker_exception_fails_safely(
    m06a_phase3a_vault, monkeypatch
):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="worker-exception", content=b"alpha\n")
    admission_id = _admit_parser(opened)

    def crashed(*args, **kwargs):
        raise RuntimeError("synthetic worker launch failure")

    monkeypatch.setattr(parser_service_module, "run_under_test_worker", crashed)
    result = _parse(opened, link_id, admission_id, "parse:worker-exception")
    assert result.state == "failed"
    assert result.terminal_outcome == "internal_error"
    assert result.package_sha256 is None
    assert opened.connection.execute("SELECT count(*) FROM normalized_packages").fetchone()[0] == 0
    assert opened.connection.execute("SELECT count(*) FROM document_versions").fetchone()[0] == 0

def test_m06a_text_canon_019_operation_replay_and_conflict(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    first_link, _ = _artifact(opened, key="replay-a", content=b"alpha\n")
    second_link, _ = _artifact(opened, key="replay-b", content=b"beta\n")
    admission_id = _admit_parser(opened)
    first = _parse(opened, first_link, admission_id, "parse:replay")
    replay = _parse(opened, first_link, admission_id, "parse:replay")
    assert replay.replayed is True
    assert replay.parser_execution_id == first.parser_execution_id
    with pytest.raises(ValueError):
        _parse(opened, second_link, admission_id, "parse:replay")


def test_m06a_text_canon_020_exact_package_reuse_and_execution_link(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="reuse", content=b"same\n")
    admission_id = _admit_parser(opened)
    first = _parse(opened, link_id, admission_id, "parse:reuse:1")
    second = _parse(opened, link_id, admission_id, "parse:reuse:2")
    assert second.reused_package is True
    assert first.normalized_package_id == second.normalized_package_id
    assert opened.connection.execute(
        "SELECT count(*) FROM parser_execution_package_links"
    ).fetchone()[0] == 2


def test_m06a_text_canon_021_initial_document_elements_and_regions(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, artifact_sha = _artifact(opened, key="fidelity", content=b"alpha\n\nbeta\n")
    admission_id = _admit_parser(opened)
    result = _parse(opened, link_id, admission_id, "parse:fidelity")
    document = opened.connection.execute(
        """SELECT source_artifact_sha256, version_ordinal, state
        FROM document_versions WHERE id=?""",
        (result.document_version_id,),
    ).fetchone()
    assert tuple(document) == (artifact_sha, 1, "current")
    assert opened.connection.execute(
        "SELECT count(*) FROM elements WHERE document_version_id=?",
        (result.document_version_id,),
    ).fetchone()[0] == 2
    assert opened.connection.execute(
        "SELECT count(*) FROM regions WHERE document_version_id=?",
        (result.document_version_id,),
    ).fetchone()[0] == 1


def test_m06a_text_canon_022_identical_rerun_creates_no_version_noise(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="version-noise", content=b"alpha\n")
    admission_id = _admit_parser(opened)
    _parse(opened, link_id, admission_id, "parse:version:1")
    second = _parse(opened, link_id, admission_id, "parse:version:2")
    assert second.reused_document is True
    assert opened.connection.execute("SELECT count(*) FROM document_versions").fetchone()[0] == 1


def test_m06a_text_canon_023_package_before_database_requires_reconciliation(
    m06a_phase3a_vault
):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="reconcile", content=b"alpha\n")
    admission_id = _admit_parser(opened)
    with pytest.raises(RuntimeError, match="synthetic package-before-database failure"):
        canonical_parse_text(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "parse:reconcile"),
            acquisition_artifact_link_id=link_id,
            operation_key="parse:reconcile",
            expected_parser_admission_version_id=admission_id,
            fail_after_package_store=True,
        )
    assert opened.connection.execute(
        "SELECT count(*) FROM parser_executions WHERE state='started'"
    ).fetchone()[0] == 1
    assert opened.connection.execute("SELECT count(*) FROM normalized_packages").fetchone()[0] == 0
    assert list((opened.root / "packages" / "sha256").rglob("*.json"))


def test_m06a_text_canon_024_backup_restore_includes_output(
    m06a_phase3a_vault, tmp_path: Path
):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="backup", content=b"alpha\n")
    admission_id = _admit_parser(opened)
    _parse(opened, link_id, admission_id, "parse:backup")
    actor = _actor(opened.identity.vault_account_id, "backup:canonical")
    generation = create_vault_generation(
        opened.connection,
        vault_root=opened.root,
        actor=actor,
        migration_head="V0004",
    )
    verified = verify_vault_generation(
        generation.generation_root,
        expected_vault_account_id=opened.identity.vault_account_id,
        expected_vault_instance_id=opened.identity.vault_instance_id,
        expected_migration_head="V0004",
        authority_connection=opened.connection,
    )
    assert verified["package_count"] == 1
    restored = restore_generation_disposable(
        generation.generation_root,
        tmp_path / "restore-proof",
        expected_vault_account_id=opened.identity.vault_account_id,
        expected_vault_instance_id=opened.identity.vault_instance_id,
        expected_migration_head="V0004",
        authority_connection=opened.connection,
    )
    assert restored.package_count == 1


def test_m06a_text_canon_documents_are_safe_summaries(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    link_id, _ = _artifact(opened, key="summary", content=b"secret-looking fixture\n")
    admission_id = _admit_parser(opened)
    _parse(opened, link_id, admission_id, "parse:summary")
    rows = list_canonical_documents(
        opened.connection, vault_account_id=opened.identity.vault_account_id
    )
    assert len(rows) == 1
    rendered = repr(rows)
    assert "secret-looking fixture" not in rendered
    assert str(opened.root) not in rendered
