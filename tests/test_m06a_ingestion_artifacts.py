from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.vault_backup import create_vault_generation
from discrepancy_desk.vault_filesystem import (
    MAX_ARTIFACT_BYTES,
    ArtifactIntegrityError,
    ArtifactLimitExceeded,
    store_stream,
)
from discrepancy_desk.vault_ingestion import admit_artifact, admit_bytes, start_intake
from discrepancy_desk.vault_router import selected_vault_health


def _actor(vault_id: str, key: str) -> ActorContext:
    return ActorContext(
        actor_id="owner-local",
        actor_class="human",
        vault_account_id=vault_id,
        correlation_id=key,
        authentication_source="pytest",
        allowed_operation_class="vault_admin",
    )


def _start_file(opened, key: str, *, label: str = "fixture.bin"):
    return start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, key),
        source_kind="manual_file",
        descriptor_class="file",
        display_label=label,
        locator=None,
        platform_label="x",
        retention_classification="preservation_compatible",
        policy_basis_reference="owner-controlled local fixture",
        human_classification_note="preservation compatible test fixture",
        client_nonce=f"nonce:{key}",
        operation_key=key,
        expects_bytes=True,
        supplied_filename=label,
        supplied_media_type="application/octet-stream",
        advisory_byte_size=None,
    )


def _admit(opened, start, key: str, content: bytes):
    assert start.acquisition_id and start.upload_authorization_id
    return admit_bytes(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, key),
        acquisition_id=start.acquisition_id,
        upload_authorization_id=start.upload_authorization_id,
        operation_key=key,
        content=content,
        supplied_filename="fixture.bin",
        supplied_media_type="application/octet-stream",
    )


def test_intake_metadata_types_and_bounds_fail_before_mutation(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    vault_id = opened.identity.vault_account_id
    base = {
        "connection": opened.connection,
        "actor": _actor(vault_id, "intake:bounds"),
        "source_kind": "manual_file",
        "descriptor_class": "file",
        "display_label": "bounded file",
        "locator": None,
        "platform_label": "x",
        "retention_classification": "preservation_compatible",
        "policy_basis_reference": "owner-controlled local fixture",
        "human_classification_note": "bounded fixture",
        "client_nonce": "nonce:bounds",
        "operation_key": "intake:bounds",
        "expects_bytes": True,
        "supplied_filename": "fixture.bin",
        "supplied_media_type": "application/octet-stream",
        "advisory_byte_size": 1,
    }
    with pytest.raises(TypeError, match="expects_bytes must be a boolean"):
        start_intake(**{**base, "expects_bytes": "false"})
    with pytest.raises(TypeError, match="advisory byte size must be an integer"):
        start_intake(**{**base, "advisory_byte_size": True})
    with pytest.raises(ValueError, match="outside the admitted ceiling"):
        start_intake(**{**base, "advisory_byte_size": MAX_ARTIFACT_BYTES + 1})
    with pytest.raises(ValueError, match="display label exceeds"):
        start_intake(**{**base, "display_label": "x" * 513})
    with pytest.raises(ValueError, match="operation key exceeds"):
        start_intake(**{**base, "operation_key": "x" * 257})
    with pytest.raises(ValueError, match="manual_locator intake requires a locator"):
        start_intake(
            **{
                **base,
                "source_kind": "manual_locator",
                "descriptor_class": "locator",
                "expects_bytes": False,
                "locator": None,
            }
        )
    assert opened.connection.execute("SELECT count(*) FROM acquisitions").fetchone()[0] == 0
    assert opened.connection.execute("SELECT count(*) FROM intake_rejection_receipts").fetchone()[0] == 0


def test_m06a_ht_018_observation_chain_required(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    vault_id = opened.identity.vault_account_id
    with pytest.raises(sqlite3.IntegrityError):
        opened.connection.execute(
            """INSERT INTO acquisitions
            (id, vault_account_id, observation_id, actor_id, lifecycle_state, outcome,
             operation_key, correlation_id, started_at, finalized_at, error_class,
             error_code, supplied_filename, supplied_media_type,
             rights_retention_version_id, receipt_sha256)
            VALUES ('bad', ?, 'missing-observation', 'owner-local', 'started', NULL,
                    'bad', 'bad', '2026-01-01T00:00:00Z', NULL, NULL, NULL,
                    NULL, NULL, 'missing-rights', ?)""",
            (vault_id, "0" * 64),
        )


def test_m06a_ht_019_truthful_acquisition_lifecycle(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    start = _start_file(opened, "intake:019")
    row = opened.connection.execute(
        "SELECT lifecycle_state, outcome FROM acquisitions WHERE id=?",
        (start.acquisition_id,),
    ).fetchone()
    assert tuple(row) == ("started", None)
    result = _admit(opened, start, "upload:019", b"truthful bytes")
    row = opened.connection.execute(
        "SELECT lifecycle_state, outcome, finalized_at FROM acquisitions WHERE id=?",
        (start.acquisition_id,),
    ).fetchone()
    assert row[0] == "finalized" and row[1] == "succeeded" and row[2]
    assert result.byte_size == len(b"truthful bytes")


def test_m06a_ht_020_locator_is_not_acquisition(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    key = "intake:020"
    result = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, key),
        source_kind="manual_locator",
        descriptor_class="locator",
        display_label="YouTube locator",
        locator="https://www.youtube.com/watch?v=fixture",
        platform_label="youtube",
        retention_classification="preservation_compatible",
        policy_basis_reference="locator only; no remote content acquired",
        human_classification_note="identity pointer only",
        client_nonce="nonce:020",
        operation_key=key,
        expects_bytes=False,
    )
    row = opened.connection.execute(
        "SELECT lifecycle_state, outcome FROM acquisitions WHERE id=?",
        (result.acquisition_id,),
    ).fetchone()
    assert tuple(row) == ("finalized", "no_artifact")
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 0


def test_m06a_ht_021_repeated_identical_bytes_preserve_encounters(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    content = b"same bytes, separate encounters"
    first = _start_file(opened, "intake:021:first")
    second = _start_file(opened, "intake:021:second")
    one = _admit(opened, first, "upload:021:first", content)
    two = _admit(opened, second, "upload:021:second", content)
    assert one.artifact_id == two.artifact_id
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 1
    assert opened.connection.execute("SELECT count(*) FROM acquisition_artifact_links").fetchone()[0] == 2
    assert opened.connection.execute("SELECT count(*) FROM acquisitions").fetchone()[0] == 2


def test_artifact_upload_metadata_is_bounded(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    start = _start_file(opened, "intake:upload-bounds")
    assert start.acquisition_id and start.upload_authorization_id
    with pytest.raises(ValueError, match="supplied filename exceeds"):
        admit_bytes(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "upload:bounds"),
            acquisition_id=start.acquisition_id,
            upload_authorization_id=start.upload_authorization_id,
            operation_key="upload:bounds",
            content=b"bounded bytes",
            supplied_filename="x" * 513,
            supplied_media_type="application/octet-stream",
        )
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 0
    assert not any(path.is_file() for path in (opened.root / "temp").rglob("*"))


def test_artifact_upload_replay_binds_exact_bytes(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    start = _start_file(opened, "intake:replay")
    first = _admit(opened, start, "upload:replay", b"exact replay bytes")
    replay = _admit(opened, start, "upload:replay", b"exact replay bytes")
    assert replay == type(first)(
        acquisition_id=first.acquisition_id,
        artifact_id=first.artifact_id,
        sha256=first.sha256,
        byte_size=first.byte_size,
        storage_relative_path=first.storage_relative_path,
        reused_existing=True,
    )
    with pytest.raises(ValueError, match="idempotency key reused"):
        _admit(opened, start, "upload:replay", b"different replay bytes")
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 1
    assert opened.connection.execute("SELECT count(*) FROM acquisition_artifact_links").fetchone()[0] == 1
    expected_files = [
        path for path in (opened.root / "objects" / "sha256").rglob("*") if path.is_file()
    ]
    assert len(expected_files) == 1


def test_acquisition_and_upload_authority_fields_are_engine_guarded(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    start = _start_file(opened, "intake:engine-guard")
    with pytest.raises(sqlite3.IntegrityError, match="immutable fields"):
        opened.connection.execute(
            "UPDATE acquisitions SET operation_key='changed' WHERE id=?",
            (start.acquisition_id,),
        )
    opened.connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="not permitted"):
        opened.connection.execute(
            "UPDATE intake_upload_authorizations SET max_bytes=1 WHERE id=?",
            (start.upload_authorization_id,),
        )
    opened.connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
        opened.connection.execute(
            "DELETE FROM acquisitions WHERE id=?",
            (start.acquisition_id,),
        )
    opened.connection.rollback()


def test_m06a_ht_022_artifact_overwrite_or_hash_mismatch_rejected(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    content = b"immutable object"
    first = _start_file(opened, "intake:022:first")
    stored = _admit(opened, first, "upload:022:first", content)
    object_path = opened.root / Path(stored.storage_relative_path)
    object_path.write_bytes(b"tampered object")
    second = _start_file(opened, "intake:022:second")
    with pytest.raises(ArtifactIntegrityError):
        _admit(opened, second, "upload:022:second", content)
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 1


def test_m06a_ht_023_temp_partial_write_reconciles(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    start = _start_file(opened, "intake:023")

    class OversizedStream:
        def __init__(self) -> None:
            self.remaining = MAX_ARTIFACT_BYTES + 1

        def read(self, size: int) -> bytes:
            if self.remaining <= 0:
                return b""
            amount = min(size, self.remaining)
            self.remaining -= amount
            return b"x" * amount

    assert start.acquisition_id and start.upload_authorization_id
    with pytest.raises(ArtifactLimitExceeded):
        admit_artifact(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "upload:023"),
            acquisition_id=start.acquisition_id,
            upload_authorization_id=start.upload_authorization_id,
            operation_key="upload:023",
            stream=OversizedStream(),
            supplied_filename="fixture.bin",
            supplied_media_type="application/octet-stream",
        )
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 0
    assert not any(path.is_file() for path in (opened.root / "temp").rglob("*"))
    state = opened.connection.execute(
        "SELECT lifecycle_state, outcome, error_code FROM acquisitions WHERE id=?",
        (start.acquisition_id,),
    ).fetchone()
    assert tuple(state) == ("interrupted", "failed", "artifact_limit_exceeded")


def test_m06a_ht_024_orphan_object_reconciliation(
    m06a_phase2_vault,
    m06a_vault_spec,
    monkeypatch,
) -> None:
    central, opened = m06a_phase2_vault
    start = _start_file(opened, "intake:024")
    import discrepancy_desk.vault_ingestion as ingestion

    def fail_commit(*args, **kwargs):
        raise RuntimeError("synthetic database failure after object finalization")

    monkeypatch.setattr(ingestion, "_commit_artifact_admission", fail_commit)
    with pytest.raises(RuntimeError):
        _admit(opened, start, "upload:024", b"orphan candidate")
    assert any(path.is_file() for path in (opened.root / "objects" / "sha256").rglob("*"))
    assert opened.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == 0
    assert opened.connection.execute(
        "SELECT count(*) FROM reconciliation_work WHERE operation_type='admit_artifact' AND state='required'"
    ).fetchone()[0] == 1
    health = selected_vault_health(
        central,
        vault_base=opened.root.parent,
        vault_id=opened.identity.vault_account_id,
        migration_spec=m06a_vault_spec,
    )
    assert health["status"] == "blocked"
    assert health["reason_code"] == "vault_reconciliation_required"
    with pytest.raises(ValueError, match="unresolved reconciliation"):
        create_vault_generation(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "backup:orphan-blocked"),
            migration_head="V0002",
            application_commit="test-commit",
        )


def test_untracked_object_blocks_health_and_backup(
    m06a_phase2_vault,
    m06a_vault_spec,
) -> None:
    central, opened = m06a_phase2_vault
    orphan = opened.root / "objects" / "sha256" / "aa" / "bb" / ("a" * 64)
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"untracked orphan")
    health = selected_vault_health(
        central,
        vault_base=opened.root.parent,
        vault_id=opened.identity.vault_account_id,
        migration_spec=m06a_vault_spec,
    )
    assert health["status"] == "blocked"
    assert health["reason_code"] == "vault_artifact_integrity_failed"
    with pytest.raises(ArtifactIntegrityError, match="orphan"):
        create_vault_generation(
            opened.connection,
            vault_root=opened.root,
            actor=_actor(opened.identity.vault_account_id, "backup:untracked-orphan"),
            migration_head="V0002",
            application_commit="test-commit",
        )


def test_m06a_ht_025_cross_provenance_composition_rejected(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    first = _start_file(opened, "intake:025:first")
    second = _start_file(opened, "intake:025:second")
    _admit(opened, first, "upload:025:first", b"branch one")
    _admit(opened, second, "upload:025:second", b"branch two")
    rows = opened.connection.execute(
        """SELECT a.id, o.id, occ.id, item.id, source.id
        FROM acquisitions a
        JOIN observations o ON o.vault_account_id=a.vault_account_id AND o.id=a.observation_id
        JOIN occurrences occ ON occ.vault_account_id=o.vault_account_id AND occ.id=o.occurrence_id
        JOIN source_items item ON item.vault_account_id=occ.vault_account_id AND item.id=occ.source_item_id
        JOIN sources source ON source.vault_account_id=item.vault_account_id AND source.id=item.source_id
        ORDER BY a.id"""
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][1:] != rows[1][1:]
    assert "source_id" not in __import__("inspect").signature(start_intake).parameters
    assert "artifact_object_id" not in __import__("inspect").signature(admit_bytes).parameters


def test_m06a_ht_092_cross_platform_research_stays_in_brand_vault(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    for platform in ("x", "truth_social"):
        key = f"intake:092:{platform}"
        start_intake(
            opened.connection,
            actor=_actor(opened.identity.vault_account_id, key),
            source_kind="manual_locator",
            descriptor_class="locator",
            display_label=f"{platform} locator",
            locator=f"https://example.invalid/{platform}",
            platform_label=platform,
            retention_classification="preservation_compatible",
            policy_basis_reference="locator-only fixture",
            human_classification_note="manual identity pointer",
            client_nonce=f"nonce:{platform}",
            operation_key=key,
            expects_bytes=False,
        )
    rows = opened.connection.execute(
        "SELECT DISTINCT vault_account_id FROM sources"
    ).fetchall()
    assert [str(row[0]) for row in rows] == [opened.identity.vault_account_id]
    assert opened.connection.execute("SELECT count(*) FROM sources").fetchone()[0] == 2


def test_m06a_ht_104_no_artifact_is_locator_only_and_cannot_mask_failure(m06a_phase2_vault) -> None:
    _, opened = m06a_phase2_vault
    with pytest.raises(ValueError, match="manual_file intake must expect bytes"):
        start_intake(
            opened.connection,
            actor=_actor(opened.identity.vault_account_id, "intake:104:file"),
            source_kind="manual_file",
            descriptor_class="file",
            display_label="missing bytes",
            locator=None,
            platform_label=None,
            retention_classification="preservation_compatible",
            policy_basis_reference="fixture",
            human_classification_note="fixture",
            client_nonce="nonce:104:file",
            operation_key="intake:104:file",
            expects_bytes=False,
        )
    rejected = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, "intake:104:reject"),
        source_kind="manual_file",
        descriptor_class="file",
        display_label="not retained",
        locator=None,
        platform_label=None,
        retention_classification="timed_deletion_required",
        policy_basis_reference="delete after access",
        human_classification_note="must reject",
        client_nonce="nonce:104:reject",
        operation_key="intake:104:reject",
        expects_bytes=True,
    )
    assert rejected.status == "rejected"
    assert opened.connection.execute("SELECT count(*) FROM acquisitions").fetchone()[0] == 0


def test_m06a_ht_105_temporary_quarantine_is_noncanonical_and_reconciled(
    m06a_phase2_vault,
) -> None:
    _, opened = m06a_phase2_vault
    with pytest.raises(ArtifactLimitExceeded):
        store_stream(
            opened.root,
            operation_id="temporary-quarantine-105",
            stream=io.BytesIO(b"12345"),
            max_bytes=4,
        )
    assert not any(path.is_file() for path in (opened.root / "temp").rglob("*"))
    assert not any(path.is_file() for path in (opened.root / "objects").rglob("*"))
    tables = {
        str(row[0])
        for row in opened.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "parser_executions" not in tables
    assert "normalized_packages" not in tables
