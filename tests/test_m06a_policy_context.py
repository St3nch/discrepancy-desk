from __future__ import annotations

import hashlib
import inspect
import sqlite3
from uuid import uuid4

import pytest

from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.vault_ingestion import admit_bytes, start_intake
from discrepancy_desk.vault_persistence import utc_now


def _actor(vault_id: str, key: str) -> ActorContext:
    return ActorContext(
        actor_id="owner-local",
        actor_class="human",
        vault_account_id=vault_id,
        correlation_id=key,
        authentication_source="pytest",
        allowed_operation_class="vault_admin",
    )


def _reject(opened, key: str, classification: str, *, policy: str = "policy fixture"):
    return start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, key),
        source_kind="manual_file",
        descriptor_class="file",
        display_label="SECRET-CONTENT-BEARING-FILENAME.txt",
        locator=None,
        platform_label=None,
        retention_classification=classification,
        policy_basis_reference=policy,
        human_classification_note="classification note only",
        client_nonce=f"nonce:{key}",
        operation_key=key,
        expects_bytes=True,
        supplied_filename="SECRET-CONTENT-BEARING-FILENAME.txt",
        supplied_media_type="text/plain",
        advisory_byte_size=123,
    )


def _admitted_artifact(opened):
    intake_key = "policy:admit"
    start = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, intake_key),
        source_kind="manual_file",
        descriptor_class="file",
        display_label="policy artifact",
        locator=None,
        platform_label="x",
        retention_classification="preservation_compatible",
        policy_basis_reference="owner-controlled fixture",
        human_classification_note="preservation compatible",
        client_nonce="nonce:policy-admit",
        operation_key=intake_key,
        expects_bytes=True,
        supplied_filename="policy.txt",
        supplied_media_type="text/plain",
    )
    assert start.acquisition_id and start.upload_authorization_id
    result = admit_bytes(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, "policy:upload"),
        acquisition_id=start.acquisition_id,
        upload_authorization_id=start.upload_authorization_id,
        operation_key="policy:upload",
        content=b"policy lineage bytes",
        supplied_filename="policy.txt",
        supplied_media_type="text/plain",
    )
    return start, result


def test_m06a_ht_027_unknown_rights_fail_closed(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    result = _reject(opened, "policy:027", "unknown")
    assert result.status == "rejected" and result.reason_code == "unknown"
    assert opened.connection.execute("SELECT count(*) FROM acquisitions").fetchone()[0] == 0
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 0
    assert not any(path.is_file() for path in (opened.root / "temp").rglob("*"))


def test_m06a_ht_029_policy_binding_is_versioned(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    _, artifact = _admitted_artifact(opened)
    vault_id = opened.identity.vault_account_id
    prior = opened.connection.execute(
        """SELECT id FROM artifact_policy_bindings
        WHERE vault_account_id=? AND artifact_object_id=?""",
        (vault_id, artifact.artifact_id),
    ).fetchone()
    assert prior is not None
    rights_id = f"rights-{uuid4()}"
    now = utc_now()
    opened.connection.execute(
        """INSERT INTO rights_retention_versions
        VALUES (?, ?, 'allow', NULL, 'deny', 'deny', 'deny', 'deny', 'deny',
                'deny', 'new policy version', 'reviewed restriction', 'owner-local', ?)""",
        (rights_id, vault_id, now),
    )
    successor = f"binding-{uuid4()}"
    opened.connection.execute(
        """INSERT INTO artifact_policy_bindings
        VALUES (?, ?, ?, ?, 'current', ?, 'owner-local', ?)""",
        (successor, vault_id, artifact.artifact_id, rights_id, str(prior[0]), now),
    )
    opened.connection.commit()
    rows = opened.connection.execute(
        "SELECT id, supersedes_binding_id FROM artifact_policy_bindings ORDER BY created_at, id"
    ).fetchall()
    assert len(rows) == 2 and rows[1][1] == rows[0][0]
    with pytest.raises(sqlite3.IntegrityError, match="must supersede the current leaf"):
        opened.connection.execute(
            """INSERT INTO artifact_policy_bindings
            VALUES (?, ?, ?, ?, 'current', NULL, 'owner-local', ?)""",
            (f"binding-{uuid4()}", vault_id, artifact.artifact_id, rights_id, now),
        )
    with pytest.raises(sqlite3.IntegrityError):
        opened.connection.execute(
            "UPDATE artifact_objects SET media_type_observed='changed' WHERE id=?",
            (artifact.artifact_id,),
        )
    opened.connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        opened.connection.execute(
            "UPDATE artifact_policy_bindings SET binding_state='blocked' WHERE id=?",
            (successor,),
        )
    opened.connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        opened.connection.execute(
            "DELETE FROM artifact_policy_bindings WHERE id=?",
            (successor,),
        )
    opened.connection.rollback()


def test_m06a_ht_030_timed_deletion_material_rejected(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    result = _reject(
        opened,
        "policy:030",
        "timed_deletion_required",
        policy="must delete seven days after access",
    )
    assert result.status == "rejected"
    assert opened.connection.execute(
        "SELECT retention_classification FROM intake_rejection_receipts"
    ).fetchone()[0] == "timed_deletion_required"
    assert opened.connection.execute("SELECT count(*) FROM rights_retention_versions").fetchone()[0] == 0


def test_m06a_ht_098_timed_deletion_rejected_before_byte_admission(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    assert "stream" not in inspect.signature(start_intake).parameters
    assert "content" not in inspect.signature(start_intake).parameters
    result = _reject(opened, "policy:098", "timed_deletion_required")
    assert result.status == "rejected"
    assert not any(path.is_file() for path in (opened.root / "objects").rglob("*"))
    assert not any(path.is_file() for path in (opened.root / "temp").rglob("*"))


def test_m06a_ht_099_unknown_retention_and_rejection_receipt_fail_closed(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    _reject(opened, "policy:099", "unknown")
    row = opened.connection.execute(
        """SELECT attempted_source_kind, descriptor_class, retention_classification,
                  policy_basis_reference, reason_code, client_nonce
        FROM intake_rejection_receipts"""
    ).fetchone()
    assert tuple(row) == (
        "manual_file",
        "file",
        "unknown",
        "policy fixture",
        "unknown",
        "nonce:policy:099",
    )
    dump = "\n".join(opened.connection.iterdump())
    assert "SECRET-CONTENT-BEARING-FILENAME" not in dump


def test_m06a_ht_100_rejected_material_has_no_downstream_presence(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    _reject(opened, "policy:100", "unknown")
    for table in (
        "sources",
        "source_items",
        "occurrences",
        "observations",
        "rights_retention_versions",
        "acquisitions",
        "artifact_objects",
        "acquisition_artifact_links",
        "artifact_policy_bindings",
        "backup_generations",
        "backup_generation_files",
    ):
        assert opened.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert opened.connection.execute("SELECT count(*) FROM intake_rejection_receipts").fetchone()[0] == 1
    assert not any(path.is_file() for path in (opened.root / "objects").rglob("*"))
    assert not any(path.is_file() for path in (opened.root / "backups").rglob("*"))


def test_m06a_ht_101_no_hidden_purge_or_delete_later_bypass(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    import discrepancy_desk.vault_backup as backup
    import discrepancy_desk.vault_ingestion as ingestion

    exported = "\n".join(sorted(set(dir(ingestion)) | set(dir(backup)))).lower()
    for forbidden in ("purge", "delete_later", "deletion_scheduler", "tombstone_purge"):
        assert forbidden not in exported
    result = _reject(opened, "policy:101", "timed_deletion_required")
    assert result.status == "rejected"
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 0


def test_m06a_ht_103_rejected_content_hashes_never_persist(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    rejected_content = b"highly distinctive rejected content packet"
    content_hash = hashlib.sha256(rejected_content).hexdigest()
    _reject(opened, "policy:103", "unknown")
    values: list[str] = []
    for table in ("intake_rejection_receipts", "operation_keys", "audit_events"):
        cursor = opened.connection.execute(f"SELECT * FROM {table}")
        for row in cursor.fetchall():
            for value in row:
                if isinstance(value, bytes):
                    values.append(value.hex())
                    values.append(value.decode("utf-8", errors="ignore"))
                elif value is not None:
                    values.append(str(value))
    material = "\n".join(values)
    assert content_hash not in material
    assert rejected_content.decode() not in material
    assert "SECRET-CONTENT-BEARING-FILENAME" not in material
