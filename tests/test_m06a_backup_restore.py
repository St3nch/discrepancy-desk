from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.vault_backup import (
    create_vault_generation,
    restore_generation_disposable,
    verify_vault_generation,
)
from discrepancy_desk.vault_ingestion import admit_bytes, start_intake
from discrepancy_desk.vault_router import open_registered_vault
from discrepancy_desk.vault_service import provision_vault


def _actor(vault_id: str, key: str) -> ActorContext:
    return ActorContext(
        actor_id="owner-local",
        actor_class="human",
        vault_account_id=vault_id,
        correlation_id=key,
        authentication_source="pytest",
        allowed_operation_class="vault_admin",
    )


def _seed_artifact(opened, key: str, content: bytes = b"backup fixture bytes"):
    start = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, f"intake:{key}"),
        source_kind="manual_file",
        descriptor_class="file",
        display_label=f"{key}.bin",
        locator=None,
        platform_label="x",
        retention_classification="preservation_compatible",
        policy_basis_reference="owner-controlled backup fixture",
        human_classification_note="preservation compatible",
        client_nonce=f"nonce:{key}",
        operation_key=f"intake:{key}",
        expects_bytes=True,
        supplied_filename=f"{key}.bin",
        supplied_media_type="application/octet-stream",
    )
    assert start.acquisition_id and start.upload_authorization_id
    return admit_bytes(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, f"upload:{key}"),
        acquisition_id=start.acquisition_id,
        upload_authorization_id=start.upload_authorization_id,
        operation_key=f"upload:{key}",
        content=content,
        supplied_filename=f"{key}.bin",
        supplied_media_type="application/octet-stream",
    )


def _generation(opened, key: str = "default"):
    migration_head = str(
        opened.connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    )
    return create_vault_generation(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, f"backup:{key}"),
        migration_head=migration_head,
        application_commit="test-commit",
    )


def test_m06a_ht_066_missing_original_fails_backup_or_restore(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    artifact = _seed_artifact(opened, "066")
    generation = _generation(opened, "066")
    copied = generation.generation_root / Path(artifact.storage_relative_path)
    copied.unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_vault_generation(
            generation.generation_root,
            expected_vault_account_id=opened.identity.vault_account_id,
            expected_vault_instance_id=opened.identity.vault_instance_id,
        )


def test_m06a_ht_067_manifest_and_artifact_tamper_detected(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    artifact = _seed_artifact(opened, "067")
    generation = _generation(opened, "067")
    copied = generation.generation_root / Path(artifact.storage_relative_path)
    copied.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="size mismatch|hash mismatch"):
        verify_vault_generation(generation.generation_root)
    copied.write_bytes(b"backup fixture bytes")
    manifest = json.loads(generation.manifest_path.read_text(encoding="utf-8"))
    manifest["application_commit"] = "fabricated"
    generation.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="completion marker"):
        verify_vault_generation(generation.generation_root)


def test_m06a_ht_068_wrong_account_restore_rejected(m06a_phase2_vault, tmp_path: Path) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, "068")
    generation = _generation(opened, "068")
    with pytest.raises(ValueError, match="another Vault account"):
        restore_generation_disposable(
            generation.generation_root,
            tmp_path / "proof",
            expected_vault_account_id="vault-wrong",
            expected_vault_instance_id=opened.identity.vault_instance_id,
        )


def test_m06a_ht_069_dirty_restore_target_rejected(m06a_phase2_vault, tmp_path: Path) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, "069")
    generation = _generation(opened, "069")
    target = tmp_path / "dirty-proof"
    target.mkdir()
    (target / "existing.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        restore_generation_disposable(
            generation.generation_root,
            target,
            expected_vault_account_id=opened.identity.vault_account_id,
            expected_vault_instance_id=opened.identity.vault_instance_id,
        )
    assert (target / "existing.txt").read_text(encoding="utf-8") == "dirty"


def test_m06a_ht_070_partial_backup_reconciliation(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, "070")
    generation = _generation(opened, "070")
    complete = generation.generation_root / "COMPLETE"
    complete_bytes = complete.read_bytes()
    complete.unlink()
    with pytest.raises(ValueError, match="incomplete"):
        verify_vault_generation(generation.generation_root)
    state = opened.connection.execute(
        "SELECT lifecycle_state, manifest_sha256 FROM backup_generations WHERE id=?",
        (generation.generation_id,),
    ).fetchone()
    assert tuple(state) == ("complete", generation.manifest_sha256)

    complete.write_bytes(complete_bytes)
    opened.connection.execute("DROP TRIGGER backup_generations_update_guard")
    opened.connection.execute(
        "UPDATE backup_generations SET lifecycle_state='reconciliation_required' WHERE id=?",
        (generation.generation_id,),
    )
    opened.connection.commit()
    with pytest.raises(ValueError, match="not complete in Vault authority"):
        verify_vault_generation(
            generation.generation_root,
            authority_connection=opened.connection,
        )


def test_backup_requires_active_bounded_human_authority(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    opened.connection.execute(
        "UPDATE actors SET status='disabled' WHERE vault_account_id=? AND id='owner-local'",
        (opened.identity.vault_account_id,),
    )
    opened.connection.commit()
    with pytest.raises(PermissionError, match="active human"):
        _generation(opened, "disabled")
    assert opened.connection.execute("SELECT count(*) FROM backup_generations").fetchone()[0] == 0


def test_backup_operation_key_is_bounded(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    with pytest.raises(ValueError, match="exceeds its admitted length"):
        create_vault_generation(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "x" * 257),
            migration_head="V0004",
            application_commit="test-commit",
        )
    assert opened.connection.execute("SELECT count(*) FROM backup_generations").fetchone()[0] == 0


def test_backup_operation_replay_is_idempotent_and_conflicts_fail(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, "backup-replay")
    first = _generation(opened, "replay")
    replay = _generation(opened, "replay")
    assert replay == first
    assert opened.connection.execute("SELECT count(*) FROM backup_generations").fetchone()[0] == 1
    with pytest.raises(ValueError, match="idempotency key reused"):
        create_vault_generation(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "backup:replay"),
            migration_head="V0004",
            application_commit="different-commit",
        )


def test_backup_generation_authority_fields_are_engine_guarded(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    generation = _generation(opened, "engine-guard")
    with pytest.raises(sqlite3.IntegrityError, match="immutable fields"):
        opened.connection.execute(
            "UPDATE backup_generations SET application_commit='changed' WHERE id=?",
            (generation.generation_id,),
        )
    opened.connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        opened.connection.execute(
            "DELETE FROM backup_generations WHERE id=?",
            (generation.generation_id,),
        )
    opened.connection.rollback()


def test_backup_manifest_path_escape_is_rejected(m06a_phase2_vault, tmp_path: Path) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, "path-escape")
    generation = _generation(opened, "path-escape")
    manifest = json.loads(generation.manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../outside.sqlite3"
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    generation.manifest_path.write_bytes(manifest_bytes)
    complete = json.loads((generation.generation_root / "COMPLETE").read_text(encoding="utf-8"))
    import hashlib

    complete["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    (generation.generation_root / "COMPLETE").write_text(
        json.dumps(complete, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (generation.generation_root.parent / "outside.sqlite3").write_bytes(b"outside")
    with pytest.raises(ValueError, match="unsafe path"):
        verify_vault_generation(generation.generation_root)


def test_m06a_ht_073_derived_snapshot_rows_are_non_authoritative(m06a_phase2_vault, tmp_path: Path) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, "073")
    generation = _generation(opened, "073")
    manifest = json.loads(generation.manifest_path.read_text(encoding="utf-8"))
    assert manifest["derived_state_authoritative"] is False
    assert {entry["authority_class"] for entry in manifest["files"]} == {"canonical"}
    proof = restore_generation_disposable(
        generation.generation_root,
        tmp_path / "proof-073",
        expected_vault_account_id=opened.identity.vault_account_id,
        expected_vault_instance_id=opened.identity.vault_instance_id,
    )
    assert proof.artifact_count == 1


def test_m06a_ht_096_backup_restore_is_per_vault(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_vault_spec,
        display_name="First",
        relative_root="first",
        owner_actor_id="owner-local",
        operation_key="backup:096:first",
    )
    second_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_vault_spec,
        display_name="Second",
        relative_root="second",
        owner_actor_id="owner-local",
        operation_key="backup:096:second",
    )
    with open_registered_vault(
        central, vault_base=vault_base, vault_id=first_id, migration_spec=m06a_vault_spec
    ) as first, open_registered_vault(
        central, vault_base=vault_base, vault_id=second_id, migration_spec=m06a_vault_spec
    ) as second:
        _seed_artifact(first, "096-first", b"first Vault")
        _seed_artifact(second, "096-second", b"second Vault")
        generation = _generation(first, "096")
        manifest_text = generation.manifest_path.read_text(encoding="utf-8")
        assert second.identity.vault_account_id not in manifest_text
        assert b"second Vault" not in b"".join(
            path.read_bytes()
            for path in generation.generation_root.rglob("*")
            if path.is_file() and path.name not in {"vault.sqlite3"}
        )
        with pytest.raises(ValueError, match="another Vault account"):
            verify_vault_generation(
                generation.generation_root,
                expected_vault_account_id=second.identity.vault_account_id,
                expected_vault_instance_id=second.identity.vault_instance_id,
            )
        assert not any(
            "backups" in path.relative_to(generation.generation_root).parts[:-1]
            for path in generation.generation_root.rglob("*")
            if path.is_file()
        )


@pytest.mark.parametrize("control_name", ["manifest.json", "COMPLETE"])
def test_nested_backup_control_names_are_unmanifested_tamper(
    m06a_phase2_vault, tmp_path: Path, control_name: str
) -> None:
    _, opened = m06a_phase2_vault
    _seed_artifact(opened, f"nested-{control_name}")
    generation = _generation(opened, f"nested-{control_name}")
    injected = generation.generation_root / "objects" / "unmanifested" / control_name
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_text("unmanifested nested control-name file", encoding="utf-8")

    with pytest.raises(ValueError, match="unmanifested or missing files"):
        verify_vault_generation(
            generation.generation_root,
            expected_vault_account_id=opened.identity.vault_account_id,
            expected_vault_instance_id=opened.identity.vault_instance_id,
            authority_connection=opened.connection,
        )

    proof_root = tmp_path / f"proof-{control_name}"
    with pytest.raises(ValueError, match="unmanifested or missing files"):
        restore_generation_disposable(
            generation.generation_root,
            proof_root,
            expected_vault_account_id=opened.identity.vault_account_id,
            expected_vault_instance_id=opened.identity.vault_instance_id,
            authority_connection=opened.connection,
        )
    assert not proof_root.exists()
