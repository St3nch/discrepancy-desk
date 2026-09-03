from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime

import psycopg
import pytest

from discrepancy_desk.db import MIGRATIONS, apply_migrations, bootstrap_database, connect_url
from discrepancy_desk.errors import ConfigurationError, EvidenceContractError, MigrationDriftError
from discrepancy_desk.evidence import (
    add_document_page_locator,
    add_document_text_locator,
    add_excerpt,
    add_media_time_locator,
    add_text_surface,
    capture_local_file,
    verify_file_evidence,
)
from discrepancy_desk.record import (
    admit_observation,
    open_discrepancy,
    open_file,
    propose_claim,
    record_decision,
    revise_discrepancy,
)
from discrepancy_desk.report import render_file_report, walkback
from discrepancy_desk.vault import Vault


@pytest.fixture(scope="module")
def admin_connection():
    database_url = os.environ.get("VEDAOPS_POSTGRES_URL")
    if not database_url:
        pytest.skip("requires the governed disposable PostgreSQL 18 task")
    conn = connect_url(database_url)
    bootstrap_database(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def app_connection(admin_connection):
    conn = connect_url(os.environ["VEDAOPS_POSTGRES_URL"])
    conn.execute("SET ROLE desk_app")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def human_connection(admin_connection):
    conn = connect_url(os.environ["VEDAOPS_POSTGRES_URL"])
    conn.execute("SET ROLE desk_human_authority")
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def file01_record(app_connection, human_connection, tmp_path_factory):
    data_root = tmp_path_factory.mktemp("desk-data").resolve()
    document_source = data_root / "candidate-source.pdf"
    document_source.write_bytes(b"%PDF-1.4\noperator-preserved candidate bytes\n")
    audio_source = data_root / "candidate-recording.mp3"
    audio_source.write_bytes(b"ID3\x04\x00\x00synthetic candidate audio bytes")
    vault = Vault(data_root)

    file_id = open_file(
        app_connection,
        public_id="DD-7225",
        subject="Rendlesham Forest incident, December 1980",
        investigation_question=(
            "What does the contemporaneous record establish about the Rendlesham "
            "Forest incident, how did the story change in later retellings, and which "
            "reported details remain unexplained after the strongest conventional "
            "explanations are considered?"
        ),
    )
    capture = capture_local_file(
        app_connection,
        vault,
        file_public_id="DD-7225",
        source_path=document_source,
        acquisition_url="https://example.test/candidate-source.pdf",
        retrieved_at=datetime(2026, 9, 3, tzinfo=UTC),
        reported_media_type="application/pdf",
        detected_media_type="application/pdf",
        expected_sha256=hashlib.sha256(document_source.read_bytes()).hexdigest(),
        expected_byte_size=document_source.stat().st_size,
        page_count=1,
        duration_ms=None,
        asserted_source_identity="Candidate archival packet",
        asserted_by="example.test",
        identity_verification_state="unverified",
        identity_verification_basis=None,
        provenance_note="Synthetic local bytes used only by the disposable integration test.",
        relevance_note="Exercises the File-scoped evidence path without asserting corpus facts.",
    )
    recapture = capture_local_file(
        app_connection,
        vault,
        file_public_id="DD-7225",
        source_path=document_source,
        acquisition_url="https://mirror.example.test/candidate-source.pdf",
        retrieved_at=datetime(2026, 9, 3, 1, tzinfo=UTC),
        reported_media_type="application/pdf",
        detected_media_type="application/pdf",
        expected_sha256=hashlib.sha256(document_source.read_bytes()).hexdigest(),
        expected_byte_size=document_source.stat().st_size,
        page_count=1,
        duration_ms=None,
        asserted_source_identity="Candidate archival packet",
        asserted_by="mirror.example.test",
        identity_verification_state="unverified",
        identity_verification_basis=None,
        provenance_note="Synthetic identical recapture used to prove receipt preservation.",
        relevance_note="Exercises recapture history without asserting corpus facts.",
    )
    page_locator_id = add_document_page_locator(
        app_connection,
        artifact_id=capture.artifact_id,
        page_number=1,
    )
    surface = add_text_surface(
        app_connection,
        vault,
        artifact_id=capture.artifact_id,
        source_locator_id=page_locator_id,
        surface_kind="operator_transcription",
        text="The witness reported lights. The source also records an ordinary explanation.",
        produced_by_method="operator_transcription",
        produced_by_actor="integration-test operator",
        produced_by_version=None,
        produced_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    excerpt_id = add_excerpt(
        app_connection,
        vault,
        locator_id=page_locator_id,
        capture_id=capture.capture_id,
        surface_id=surface.surface_id,
        exact_text="The witness reported lights. The source also records an ordinary explanation.",
    )
    observation_id = admit_observation(
        app_connection,
        file_public_id="DD-7225",
        statement=("The candidate source records both a light report and an ordinary explanation."),
        excerpt_ids=[excerpt_id],
    )

    page_text_surface = add_text_surface(
        app_connection,
        vault,
        artifact_id=capture.artifact_id,
        source_locator_id=page_locator_id,
        surface_kind="document_page_text",
        text="Frozen page text for a separately authored source.",
        produced_by_method="synthetic_text_extractor",
        produced_by_actor="integration-test operator",
        produced_by_version="1",
        produced_at=datetime(2026, 9, 3, 1, 30, tzinfo=UTC),
    )
    page_text_locator_id = add_document_text_locator(
        app_connection,
        surface_id=page_text_surface.surface_id,
        page_number=1,
        start_char=0,
        end_char=16,
    )
    page_text_excerpt_id = add_excerpt(
        app_connection,
        vault,
        locator_id=page_text_locator_id,
        capture_id=capture.capture_id,
        surface_id=None,
        exact_text="Frozen page text",
    )
    page_text_observation_id = admit_observation(
        app_connection,
        file_public_id="DD-7225",
        statement="The separately authored source presents frozen page text.",
        excerpt_ids=[page_text_excerpt_id],
    )

    audio_capture = capture_local_file(
        app_connection,
        vault,
        file_public_id="DD-7225",
        source_path=audio_source,
        acquisition_url="https://example.test/candidate-recording.mp3",
        retrieved_at=datetime(2026, 9, 3, 2, tzinfo=UTC),
        reported_media_type="audio/mpeg",
        detected_media_type="video/quicktime",
        expected_sha256=hashlib.sha256(audio_source.read_bytes()).hexdigest(),
        expected_byte_size=audio_source.stat().st_size,
        page_count=None,
        duration_ms=1_093_000,
        asserted_source_identity="Candidate field recording",
        asserted_by="example.test",
        identity_verification_state="unverified",
        identity_verification_basis=None,
        provenance_note="Synthetic local audio bytes used only by the integration test.",
        relevance_note="Exercises exact time-range walkback to captured media.",
    )
    audio_locator_id = add_media_time_locator(
        app_connection,
        artifact_id=audio_capture.artifact_id,
        start_ms=12_000,
        end_ms=18_500,
    )
    audio_surface = add_text_surface(
        app_connection,
        vault,
        artifact_id=audio_capture.artifact_id,
        source_locator_id=audio_locator_id,
        surface_kind="audio_transcript_segment",
        text="Synthetic transcript of the exact bounded audio interval.",
        produced_by_method="operator_transcription",
        produced_by_actor="integration-test operator",
        produced_by_version=None,
        produced_at=datetime(2026, 9, 3, 2, 5, tzinfo=UTC),
    )
    audio_excerpt_id = add_excerpt(
        app_connection,
        vault,
        locator_id=audio_locator_id,
        capture_id=audio_capture.capture_id,
        surface_id=audio_surface.surface_id,
        exact_text="Synthetic transcript of the exact bounded audio interval.",
    )
    audio_observation_id = admit_observation(
        app_connection,
        file_public_id="DD-7225",
        statement="The candidate recording presents a report during a bounded interval.",
        excerpt_ids=[audio_excerpt_id],
    )

    claim = propose_claim(
        app_connection,
        file_public_id="DD-7225",
        proposition=(
            "At least one captured account places an ordinary explanation beside the report."
        ),
        relevance_note="Tests a Claim association without making the Claim File-owned.",
        observation_basis=[
            (observation_id, "supports"),
            (audio_observation_id, "contradicts"),
            (page_text_observation_id, "supports"),
        ],
    )

    with pytest.raises(psycopg.errors.InsufficientPrivilege) as refused:
        record_decision(
            app_connection,
            claim_version_id=claim.claim_version_id,
            authorized_by="integration-test operator",
            decision_text="Synthetic capability refusal; not a real investigative Decision.",
            posture="open",
        )
    assert refused.value.sqlstate == "42501"

    decision_id = record_decision(
        human_connection,
        claim_version_id=claim.claim_version_id,
        authorized_by="integration-test operator",
        decision_text="Synthetic positive capability proof; not a real investigative Decision.",
        posture="open",
    )
    superseding_decision_id = record_decision(
        human_connection,
        claim_version_id=claim.claim_version_id,
        authorized_by="integration-test operator",
        decision_text="Synthetic supersession proof; prior history must remain addressable.",
        posture="unresolved",
        supersedes_decision_id=decision_id,
    )
    discrepancy = open_discrepancy(
        app_connection,
        file_public_id="DD-7225",
        local_id="D01",
        question=(
            "Which, if any, reported elements of the named event remain unaccounted "
            "for by the lighthouse and astronomical explanations, and which are accounted for?"
        ),
        lifecycle_state="open",
        observation_ids=[observation_id, audio_observation_id, page_text_observation_id],
        claim_version_ids=[claim.claim_version_id],
    )
    revised_discrepancy = revise_discrepancy(
        app_connection,
        file_public_id="DD-7225",
        local_id="D01",
        question=(
            "Which reported elements of the bounded event remain unresolved after "
            "the named conventional explanations are compared with the captured record?"
        ),
        lifecycle_state="narrowed",
        observation_ids=[observation_id, audio_observation_id, page_text_observation_id],
        claim_version_ids=[claim.claim_version_id],
    )
    return {
        "vault": vault,
        "file_id": file_id,
        "capture": capture,
        "recapture": recapture,
        "surface": surface,
        "excerpt_id": excerpt_id,
        "observation_id": observation_id,
        "page_locator_id": page_locator_id,
        "page_text_surface": page_text_surface,
        "page_text_observation_id": page_text_observation_id,
        "audio_capture": audio_capture,
        "audio_observation_id": audio_observation_id,
        "claim": claim,
        "decision_id": decision_id,
        "superseding_decision_id": superseding_decision_id,
        "discrepancy": discrepancy,
        "revised_discrepancy": revised_discrepancy,
    }


def test_full_slice_renders_durable_refs_and_walks_back(app_connection, file01_record) -> None:
    report = render_file_report(app_connection, file_public_id="DD-7225")

    assert "[O:" in report
    assert f"[C:{file01_record['claim'].claim_version_id}]" in report
    assert f"[D:{file01_record['revised_discrepancy'].discrepancy_version_id}]" in report
    assert "[H:" in report
    assert "supersedes H:" in report
    assert "superseded by H:" in report
    assert "Observations" in report
    assert "Claims" in report
    assert "Human Decisions" in report
    assert "Discrepancies" in report

    result = walkback(
        app_connection,
        object_kind="claim_version",
        object_id=file01_record["claim"].claim_version_id,
    )
    assert result["object_kind"] == "claim_version"
    by_id = {observation["observation_id"]: observation for observation in result["observations"]}
    evidence = by_id[file01_record["observation_id"]]["evidence"][0]
    assert evidence["capture"]["acquisition_url"] == ("https://example.test/candidate-source.pdf")
    assert evidence["artifact"]["digest"] == file01_record["capture"].payload.digest
    assert evidence["locator"]["locator_kind"] == "document_page"


def test_audio_walkback_terminates_at_captured_recording(app_connection, file01_record) -> None:
    result = walkback(
        app_connection,
        object_kind="observation",
        object_id=file01_record["audio_observation_id"],
    )

    evidence = result["observations"][0]["evidence"][0]
    assert evidence["locator"]["locator_kind"] == "media_time_range"
    assert evidence["locator"]["start_ms"] == 12_000
    assert evidence["locator"]["end_ms"] == 18_500
    assert evidence["artifact"]["artifact_id"] == file01_record["audio_capture"].artifact_id
    assert evidence["artifact"]["media_type"] == "video/quicktime"
    assert evidence["capture"]["reported_media_type"] == "audio/mpeg"
    assert evidence["capture"]["expected_digest"] == file01_record["audio_capture"].payload.digest
    assert evidence["surface"]["surface_kind"] == "audio_transcript_segment"


def test_recapture_preserves_receipt_and_deduplicates_only_artifact(
    admin_connection, file01_record
) -> None:
    assert file01_record["capture"].capture_id != file01_record["recapture"].capture_id
    assert file01_record["capture"].artifact_id == file01_record["recapture"].artifact_id
    rows = admin_connection.execute(
        "SELECT count(*) FROM desk.capture WHERE artifact_id = %s",
        (file01_record["capture"].artifact_id,),
    ).fetchone()
    assert rows == (2,)


def test_decision_supersession_preserves_prior_history(admin_connection, file01_record) -> None:
    rows = admin_connection.execute(
        """
        SELECT d.decision_id, ds.supersedes_decision_id
        FROM desk.decision d
        LEFT JOIN desk.decision_supersession ds ON ds.decision_id = d.decision_id
        WHERE d.decision_id IN (%s, %s)
        ORDER BY d.admission_order
        """,
        (
            file01_record["decision_id"],
            file01_record["superseding_decision_id"],
        ),
    ).fetchall()
    assert len(rows) == 2
    assert str(rows[0][0]) == file01_record["decision_id"]
    assert rows[0][1] is None
    assert str(rows[1][1]) == file01_record["decision_id"]


def test_discrepancy_revision_preserves_prior_version(admin_connection, file01_record) -> None:
    rows = admin_connection.execute(
        """
        SELECT version_number, lifecycle_state
        FROM desk.discrepancy_version
        WHERE discrepancy_id = %s
        ORDER BY version_number
        """,
        (file01_record["discrepancy"].discrepancy_id,),
    ).fetchall()
    assert rows == [(1, "open"), (2, "narrowed")]


def test_page_text_walkback_exposes_surface_integrity_and_lineage(
    app_connection, file01_record
) -> None:
    result = walkback(
        app_connection,
        object_kind="observation",
        object_id=file01_record["page_text_observation_id"],
    )

    evidence = result["observations"][0]["evidence"][0]
    surface = evidence["surface"]
    assert evidence["locator"]["locator_kind"] == "document_page_char_range"
    assert surface["surface_kind"] == "document_page_text"
    assert surface["digest"] == file01_record["page_text_surface"].payload.digest
    assert surface["text_length"] == len("Frozen page text for a separately authored source.")
    assert surface["vault_key"] == file01_record["page_text_surface"].payload.vault_key
    assert surface["source_locator_id"] == file01_record["page_locator_id"]
    assert surface["artifact_id"] == file01_record["capture"].artifact_id


def test_locator_contracts_refuse_out_of_bounds_targets(app_connection, file01_record) -> None:
    with pytest.raises(psycopg.errors.CheckViolation) as page_refused:
        add_document_page_locator(
            app_connection,
            artifact_id=file01_record["capture"].artifact_id,
            page_number=2,
        )
    assert page_refused.value.sqlstate == "23514"

    with pytest.raises(psycopg.errors.CheckViolation) as text_refused:
        add_document_text_locator(
            app_connection,
            surface_id=file01_record["page_text_surface"].surface_id,
            page_number=1,
            start_char=0,
            end_char=999,
        )
    assert text_refused.value.sqlstate == "23514"

    with pytest.raises(psycopg.errors.CheckViolation) as media_refused:
        add_media_time_locator(
            app_connection,
            artifact_id=file01_record["audio_capture"].artifact_id,
            start_ms=1_092_000,
            end_ms=1_093_001,
        )
    assert media_refused.value.sqlstate == "23514"


def test_capture_refuses_unverified_bytes_and_unavailable_verified_identity(
    app_connection, tmp_path
) -> None:
    source = tmp_path / "candidate.bin"
    source.write_bytes(b"not the accepted bytes")
    vault = Vault(tmp_path.resolve())
    common = {
        "file_public_id": "DD-7225",
        "source_path": source,
        "acquisition_url": "https://example.test/candidate.bin",
        "retrieved_at": datetime(2026, 9, 3, tzinfo=UTC),
        "reported_media_type": "application/octet-stream",
        "detected_media_type": "application/octet-stream",
        "expected_byte_size": source.stat().st_size,
        "page_count": None,
        "duration_ms": None,
        "asserted_source_identity": "Candidate bytes",
        "asserted_by": "example.test",
        "identity_verification_basis": None,
        "provenance_note": "Synthetic refusal proof.",
        "relevance_note": "Synthetic refusal proof.",
    }
    with pytest.raises(EvidenceContractError, match="accepted digest"):
        capture_local_file(
            app_connection,
            vault,
            expected_sha256="0" * 64,
            identity_verification_state="unverified",
            **common,
        )
    with pytest.raises(EvidenceContractError, match="Verified source identity is unavailable"):
        capture_local_file(
            app_connection,
            vault,
            expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            identity_verification_state="verified",
            **common,
        )


def test_decision_supersession_cannot_cross_claims(
    app_connection, human_connection, file01_record
) -> None:
    other_claim = propose_claim(
        app_connection,
        file_public_id="DD-7225",
        proposition="A separate synthetic proposition.",
        relevance_note="Exercises refusal of cross-Claim Decision lineage.",
        observation_basis=[(file01_record["observation_id"], "supports")],
    )
    with pytest.raises(psycopg.errors.CheckViolation) as refused:
        record_decision(
            human_connection,
            claim_version_id=other_claim.claim_version_id,
            authorized_by="integration-test operator",
            decision_text="This must not supersede a Decision on another Claim.",
            posture="open",
            supersedes_decision_id=file01_record["decision_id"],
        )
    assert refused.value.sqlstate == "23514"


def test_file_evidence_verification_recomputes_every_boundary(
    app_connection, file01_record
) -> None:
    result = verify_file_evidence(
        app_connection,
        file01_record["vault"],
        file_public_id="DD-7225",
    )

    assert result.artifacts_verified == 2
    assert result.surfaces_verified == 3
    assert result.locators_verified == 3
    assert result.excerpts_verified == 3


def test_record_is_append_only_even_for_admin(admin_connection, file01_record) -> None:
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState) as refused:
        admin_connection.execute(
            "UPDATE desk.file SET subject = 'rewritten' WHERE file_id = %s",
            (file01_record["file_id"],),
        )
    assert refused.value.sqlstate == "55000"


def test_migration_ledger_rejects_changed_applied_history(admin_connection, tmp_path) -> None:
    copied = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, copied)
    migration = copied / "0001_file01.sql"
    migration.write_text(migration.read_text() + "\n-- forbidden rewrite\n")

    with pytest.raises(MigrationDriftError, match="does not match"):
        apply_migrations(admin_connection, copied)


def test_bootstrap_revokes_preexisting_runtime_grants(admin_connection) -> None:
    admin_connection.execute("GRANT INSERT ON desk.decision TO desk_app")
    before = admin_connection.execute(
        "SELECT has_table_privilege('desk_app', 'desk.decision', 'INSERT')"
    ).fetchone()
    assert before == (True,)

    bootstrap_database(admin_connection)

    after = admin_connection.execute(
        "SELECT has_table_privilege('desk_app', 'desk.decision', 'INSERT')"
    ).fetchone()
    assert after == (False,)


def test_bootstrap_refuses_capability_role_membership(admin_connection) -> None:
    admin_connection.execute("CREATE ROLE desk_unsafe_parent NOLOGIN NOINHERIT")
    admin_connection.execute("GRANT desk_unsafe_parent TO desk_app")
    try:
        with pytest.raises(ConfigurationError, match="can assume other roles"):
            bootstrap_database(admin_connection)
    finally:
        admin_connection.execute("REVOKE desk_unsafe_parent FROM desk_app")
        admin_connection.execute("DROP ROLE desk_unsafe_parent")


def test_installed_operator_module_runs_outside_repository_path(tmp_path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "discrepancy_desk", "--help"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert "Operate the private Discrepancy Desk" in completed.stdout


def test_postgresql_contains_references_not_payload_bytes(admin_connection) -> None:
    rows = admin_connection.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'desk' AND data_type = 'bytea'
        """
    ).fetchall()

    assert rows == []
