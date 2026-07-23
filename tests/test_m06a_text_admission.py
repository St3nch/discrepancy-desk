from __future__ import annotations


import pytest

from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.parser_service import (
    TEXT_ADMISSION_CONFIRMATION,
    admit_text_parser,
    list_parser_status,
    text_admission_manifest,
)
from discrepancy_desk.vault_service import provision_vault
from discrepancy_desk.vault_router import open_registered_vault


def _actor(vault_id: str, key: str, *, actor_id: str = "owner-local") -> ActorContext:
    return ActorContext(
        actor_id=actor_id,
        actor_class="human",
        vault_account_id=vault_id,
        correlation_id=key,
        authentication_source="pytest",
        allowed_operation_class="vault_admin",
    )


def _admit(opened, key: str = "admit:text"):
    manifest = text_admission_manifest()
    return admit_text_parser(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, key),
        operation_key=key,
        confirmation_text=TEXT_ADMISSION_CONFIRMATION,
        expected_manifest=manifest,
    )


def test_m06a_text_admit_001_exact_tuple_and_evidence_manifest(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    result = _admit(opened)
    manifest = text_admission_manifest()
    row = opened.connection.execute(
        """SELECT state, fixture_manifest_sha256, focused_test_evidence_sha256,
                  no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
                  dependency_lock_sha256, supersedes_admission_id
        FROM parser_admission_versions WHERE id=?""",
        (result.parser_admission_version_id,),
    ).fetchone()
    assert row is not None
    assert tuple(str(value) for value in row) == (
        "owner_admitted",
        manifest["fixture_manifest_sha256"],
        manifest["focused_test_evidence_sha256"],
        manifest["no_egress_evidence_sha256"],
        manifest["packaged_sidecar_evidence_sha256"],
        manifest["dependency_lock_sha256"],
        manifest["supersedes_admission_id"],
    )


def test_m06a_text_admit_002_active_human_vault_owner_guard(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    opened.connection.execute(
        "UPDATE actors SET status='disabled' WHERE id='owner-local'"
    )
    opened.connection.commit()
    with pytest.raises(PermissionError):
        _admit(opened)


def test_m06a_text_admit_003_explicit_confirmation_required(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    with pytest.raises(PermissionError):
        admit_text_parser(
            opened.connection,
            actor=_actor(opened.identity.vault_account_id, "admit:bad-confirmation"),
            operation_key="admit:bad-confirmation",
            confirmation_text="ADMIT",
            expected_manifest=text_admission_manifest(),
        )


def test_m06a_text_admit_004_immutable_successor_preserves_under_test(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    manifest = text_admission_manifest()
    result = _admit(opened)
    rows = opened.connection.execute(
        """SELECT id, state, supersedes_admission_id
        FROM parser_admission_versions ORDER BY created_at, id"""
    ).fetchall()
    assert (manifest["supersedes_admission_id"], "under_test", None) in {
        (str(row[0]), str(row[1]), row[2]) for row in rows
    }
    assert any(
        str(row[0]) == result.parser_admission_version_id
        and str(row[1]) == "owner_admitted"
        and str(row[2]) == manifest["supersedes_admission_id"]
        for row in rows
    )


def test_m06a_text_admit_005_stale_or_mismatched_material_refused(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    manifest = text_admission_manifest()
    manifest["focused_test_evidence_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        admit_text_parser(
            opened.connection,
            actor=_actor(opened.identity.vault_account_id, "admit:mismatch"),
            operation_key="admit:mismatch",
            confirmation_text=TEXT_ADMISSION_CONFIRMATION,
            expected_manifest=manifest,
        )


def test_m06a_text_admit_006_current_successor_refuses_second_admission(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    _admit(opened, "admit:first")
    with pytest.raises(PermissionError):
        _admit(opened, "admit:second")


def test_m06a_text_admit_007_per_vault_isolation(
    m06a_phase3a_vault, m06a_vault_spec, tmp_path
):
    central, opened = m06a_phase3a_vault
    _admit(opened)
    second_id = provision_vault(
        central,
        vault_base=tmp_path / "second-vaults",
        migration_spec=m06a_vault_spec,
        display_name="Second Vault",
        relative_root="second",
        owner_actor_id="owner-local",
        operation_key="fixture:second-vault",
    )
    with open_registered_vault(
        central,
        vault_base=tmp_path / "second-vaults",
        vault_id=second_id,
        migration_spec=m06a_vault_spec,
    ) as second:
        status = list_parser_status(
            second.connection, vault_account_id=second.identity.vault_account_id
        )
        assert status[0]["state"] == "under_test"
        assert status[0]["canonical_available"] is False


def test_m06a_text_admit_008_idempotent_replay_and_conflict(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    first = _admit(opened, "admit:replay")
    second = _admit(opened, "admit:replay")
    assert second.replayed is True
    assert first.parser_admission_version_id == second.parser_admission_version_id
    conflicting = text_admission_manifest()
    conflicting["confirmation_text"] = "changed"
    with pytest.raises((PermissionError, ValueError)):
        admit_text_parser(
            opened.connection,
            actor=_actor(opened.identity.vault_account_id, "admit:replay"),
            operation_key="admit:replay",
            confirmation_text="changed",
            expected_manifest=conflicting,
        )


def test_m06a_text_admit_009_admission_creates_no_parser_output(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    _admit(opened)
    for table in (
        "parser_executions",
        "normalized_packages",
        "document_versions",
        "elements",
        "regions",
    ):
        assert opened.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_m06a_text_admit_010_no_automatic_owner_admission(m06a_phase3a_vault):
    _, opened = m06a_phase3a_vault
    assert opened.connection.execute(
        "SELECT count(*) FROM parser_admission_versions WHERE state='owner_admitted'"
    ).fetchone()[0] == 0
    status = list_parser_status(
        opened.connection, vault_account_id=opened.identity.vault_account_id
    )
    assert status[0]["admission_ready"] is True
    assert status[0]["canonical_available"] is False
