from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from .actor_context import ActorContext
from .vault_filesystem import (
    ArtifactIntegrityError,
    ArtifactLimitExceeded,
    MAX_ARTIFACT_BYTES,
    StoredArtifact,
    discard_staged,
    finalize_staged,
    object_relative_path,
    reject_reparse_chain,
    sha256_file,
    stage_stream,
)
from .vault_persistence import (
    append_vault_audit,
    canonical_json,
    existing_vault_operation,
    record_vault_operation,
    request_hash,
    sha256_bytes,
    utc_now,
)

ALLOWED_SOURCE_KINDS = {"manual_file", "manual_locator"}
REJECTED_RETENTION = {
    "timed_deletion_required",
    "unknown",
    "missing",
    "contradictory",
}
MAX_OPERATION_KEY_CHARS = 256
MAX_CLIENT_NONCE_CHARS = 256
MAX_DISPLAY_LABEL_CHARS = 512
MAX_LOCATOR_CHARS = 4096
MAX_PLATFORM_LABEL_CHARS = 64
MAX_POLICY_REFERENCE_CHARS = 2048
MAX_CLASSIFICATION_NOTE_CHARS = 4096
MAX_FILENAME_CHARS = 512
MAX_MEDIA_TYPE_CHARS = 255
MAX_IDENTIFIER_CHARS = 256


@dataclass(frozen=True, slots=True)
class IntakeResult:
    status: str
    result_id: str
    acquisition_id: str | None
    upload_authorization_id: str | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class ArtifactAdmissionResult:
    acquisition_id: str
    artifact_id: str
    sha256: str
    byte_size: int
    storage_relative_path: str
    reused_existing: bool


def _vault_id(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT vault_account_id FROM vault_metadata WHERE singleton_id=1"
    ).fetchone()
    if row is None:
        raise ValueError("Vault metadata singleton is missing")
    return str(row[0])


def _require_actor(connection: sqlite3.Connection, actor: ActorContext) -> None:
    actor.require_human()
    vault_id = _vault_id(connection)
    if actor.vault_account_id != vault_id:
        raise PermissionError("actor context belongs to another Vault")
    row = connection.execute(
        "SELECT actor_class, status, authority_profile FROM actors WHERE vault_account_id=? AND id=?",
        (vault_id, actor.actor_id),
    ).fetchone()
    if row is None or str(row[0]) != "human" or str(row[1]) != "active":
        raise PermissionError("intake requires an active human actor")
    authorities = {value.strip() for value in str(row[2]).split(",") if value.strip()}
    if "vault_admin" not in authorities and "human_decision" not in authorities and "*" not in authorities:
        raise PermissionError("actor is not authorized for Vault intake")


def _safe_rejection_request(
    *,
    vault_id: str,
    actor_id: str,
    source_kind: str,
    descriptor_class: str,
    retention_classification: str,
    policy_basis_reference: str,
    client_nonce: str,
) -> dict[str, str]:
    return {
        "vault_id": vault_id,
        "actor_id": actor_id,
        "source_kind": source_kind,
        "descriptor_class": descriptor_class,
        "retention_classification": retention_classification,
        "policy_basis_reference": policy_basis_reference,
        "client_nonce": client_nonce,
    }


def _admitted_request(
    *,
    vault_id: str,
    actor_id: str,
    source_kind: str,
    display_label: str,
    locator: str | None,
    platform_label: str | None,
    policy_basis_reference: str,
    human_classification_note: str,
    client_nonce: str,
    expects_bytes: bool,
    supplied_filename: str | None,
    supplied_media_type: str | None,
    advisory_byte_size: int | None,
) -> dict[str, object]:
    return {
        "vault_id": vault_id,
        "actor_id": actor_id,
        "source_kind": source_kind,
        "display_label": display_label,
        "locator": locator,
        "platform_label": platform_label,
        "retention_classification": "preservation_compatible",
        "policy_basis_reference": policy_basis_reference,
        "human_classification_note": human_classification_note,
        "client_nonce": client_nonce,
        "expects_bytes": expects_bytes,
        "supplied_filename": supplied_filename,
        "supplied_media_type": supplied_media_type,
        "advisory_byte_size": advisory_byte_size,
    }


def _receipt_hash(payload: object) -> str:
    return sha256_bytes(canonical_json(payload))


def verify_artifact_inventory(
    connection: sqlite3.Connection,
    *,
    vault_root: Path,
    vault_account_id: str,
) -> int:
    expected: set[str] = set()
    for row in connection.execute(
        """SELECT storage_relative_path, sha256, byte_size
        FROM artifact_objects WHERE vault_account_id=? ORDER BY storage_relative_path""",
        (vault_account_id,),
    ):
        relative = str(row[0])
        artifact_sha256 = str(row[1])
        if relative != object_relative_path(artifact_sha256):
            raise ArtifactIntegrityError("artifact object path is not its content address")
        candidate = vault_root / Path(relative)
        reject_reparse_chain(candidate, stop=vault_root)
        if not candidate.is_file():
            raise ArtifactIntegrityError("artifact object is missing")
        if candidate.stat().st_size != int(row[2]) or sha256_file(candidate) != artifact_sha256:
            raise ArtifactIntegrityError("artifact object bytes do not match Vault authority")
        expected.add(relative)
    object_root = vault_root / "objects" / "sha256"
    reject_reparse_chain(object_root, stop=vault_root)
    actual = {
        path.relative_to(vault_root).as_posix()
        for path in object_root.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ArtifactIntegrityError("Vault object inventory contains missing or orphan files")
    return len(expected)


def _bounded_text(
    value: str | None,
    *,
    field: str,
    maximum: int,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    normalized = value.strip()
    if required and not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > maximum:
        raise ValueError(f"{field} exceeds its admitted length")
    return normalized or None


def start_intake(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    source_kind: str,
    descriptor_class: str,
    display_label: str,
    locator: str | None,
    platform_label: str | None,
    retention_classification: str,
    policy_basis_reference: str,
    human_classification_note: str,
    client_nonce: str,
    operation_key: str,
    expects_bytes: bool,
    supplied_filename: str | None = None,
    supplied_media_type: str | None = None,
    advisory_byte_size: int | None = None,
) -> IntakeResult:
    _require_actor(connection, actor)
    vault_id = actor.vault_account_id
    source_kind = str(source_kind).strip()
    descriptor_class = str(descriptor_class).strip()
    retention_classification = str(retention_classification).strip()
    operation_key = _bounded_text(
        operation_key,
        field="operation key",
        maximum=MAX_OPERATION_KEY_CHARS,
        required=True,
    )
    client_nonce = _bounded_text(
        client_nonce,
        field="client nonce",
        maximum=MAX_CLIENT_NONCE_CHARS,
        required=True,
    )
    policy_basis_reference = _bounded_text(
        policy_basis_reference,
        field="policy basis reference",
        maximum=MAX_POLICY_REFERENCE_CHARS,
    )
    display_label = _bounded_text(
        display_label,
        field="display label",
        maximum=MAX_DISPLAY_LABEL_CHARS,
    )
    locator = _bounded_text(locator, field="locator", maximum=MAX_LOCATOR_CHARS)
    platform_label = _bounded_text(
        platform_label,
        field="platform label",
        maximum=MAX_PLATFORM_LABEL_CHARS,
    )
    human_classification_note = _bounded_text(
        human_classification_note,
        field="human classification note",
        maximum=MAX_CLASSIFICATION_NOTE_CHARS,
    )
    supplied_filename = _bounded_text(
        supplied_filename,
        field="supplied filename",
        maximum=MAX_FILENAME_CHARS,
    )
    supplied_media_type = _bounded_text(
        supplied_media_type,
        field="supplied media type",
        maximum=MAX_MEDIA_TYPE_CHARS,
    )
    if type(expects_bytes) is not bool:
        raise TypeError("expects_bytes must be a boolean")
    if advisory_byte_size is not None:
        if type(advisory_byte_size) is not int:
            raise TypeError("advisory byte size must be an integer")
        if advisory_byte_size < 0 or advisory_byte_size > MAX_ARTIFACT_BYTES:
            raise ValueError("advisory byte size is outside the admitted ceiling")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError("source kind is not admitted in Phase 2")
    if descriptor_class not in {"file", "locator"}:
        raise ValueError("descriptor class is invalid")
    expected_descriptor = {
        "manual_file": "file",
        "manual_locator": "locator",
    }[source_kind]
    if descriptor_class != expected_descriptor:
        raise ValueError("descriptor class does not match source kind")
    if source_kind == "manual_locator" and locator is None:
        raise ValueError("manual_locator intake requires a locator")
    if source_kind != "manual_locator" and locator is not None:
        raise ValueError("only manual_locator intake may carry a locator")
    assert operation_key is not None
    assert client_nonce is not None
    if policy_basis_reference is None:
        retention_classification = "missing"
    if retention_classification != "preservation_compatible":
        if retention_classification not in REJECTED_RETENTION:
            retention_classification = "contradictory"
        safe_request = _safe_rejection_request(
            vault_id=vault_id,
            actor_id=actor.actor_id,
            source_kind=source_kind,
            descriptor_class=descriptor_class,
            retention_classification=retention_classification,
            policy_basis_reference=policy_basis_reference or "not-supplied",
            client_nonce=client_nonce,
        )
        request_sha256 = request_hash(safe_request)
        existing = existing_vault_operation(
            connection,
            actor=actor,
            operation_type="reject_intake",
            operation_key=operation_key,
            request_sha256=request_sha256,
        )
        if existing is not None:
            return IntakeResult("rejected", existing, None, None, retention_classification)
        receipt_id = f"intake-rejection-{uuid4()}"
        now = utc_now()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """INSERT INTO intake_rejection_receipts
                (id, vault_account_id, actor_id, operation_key, correlation_id,
                 attempted_source_kind, descriptor_class, retention_classification,
                 policy_basis_reference, reason_code, client_nonce, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    receipt_id,
                    vault_id,
                    actor.actor_id,
                    operation_key,
                    actor.correlation_id,
                    source_kind,
                    descriptor_class,
                    retention_classification,
                    policy_basis_reference or "not-supplied",
                    retention_classification,
                    client_nonce,
                    now,
                ),
            )
            record_vault_operation(
                connection,
                actor=actor,
                operation_type="reject_intake",
                operation_key=operation_key,
                request_sha256=request_sha256,
                result_ref=receipt_id,
            )
            append_vault_audit(
                connection,
                actor=actor,
                authority_operation="human_decision",
                request_sha256=request_sha256,
                record_type="intake_rejection_receipt",
                record_id=receipt_id,
                payload={
                    "source_kind": source_kind,
                    "descriptor_class": descriptor_class,
                    "retention_classification": retention_classification,
                    "reason_code": retention_classification,
                    "client_nonce": client_nonce,
                },
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return IntakeResult("rejected", receipt_id, None, None, retention_classification)

    if expects_bytes and source_kind != "manual_file":
        raise ValueError("only manual_file intake may expect bytes in Phase 2")
    if not expects_bytes and source_kind == "manual_file":
        raise ValueError("manual_file intake must expect bytes")
    if display_label is None:
        raise ValueError("display label is required for admitted intake")
    assert policy_basis_reference is not None
    request = _admitted_request(
        vault_id=vault_id,
        actor_id=actor.actor_id,
        source_kind=source_kind,
        display_label=display_label,
        locator=locator,
        platform_label=platform_label,
        policy_basis_reference=policy_basis_reference,
        human_classification_note=human_classification_note,
        client_nonce=client_nonce,
        expects_bytes=expects_bytes,
        supplied_filename=supplied_filename,
        supplied_media_type=supplied_media_type,
        advisory_byte_size=advisory_byte_size,
    )
    request_sha256 = request_hash(request)
    existing = existing_vault_operation(
        connection,
        actor=actor,
        operation_type="start_intake",
        operation_key=operation_key,
        request_sha256=request_sha256,
    )
    if existing is not None:
        row = connection.execute(
            "SELECT lifecycle_state, outcome FROM acquisitions WHERE vault_account_id=? AND id=?",
            (vault_id, existing),
        ).fetchone()
        if row is None:
            raise RuntimeError("prior intake operation result is missing")
        auth = connection.execute(
            "SELECT id FROM intake_upload_authorizations WHERE vault_account_id=? AND acquisition_id=?",
            (vault_id, existing),
        ).fetchone()
        return IntakeResult(
            "ready_for_upload" if str(row[0]) == "started" else "recorded",
            existing,
            existing,
            str(auth[0]) if auth is not None else None,
            None,
        )

    source_id = f"source-{uuid4()}"
    item_id = f"source-item-{uuid4()}"
    occurrence_id = f"occurrence-{uuid4()}"
    observation_id = f"observation-{uuid4()}"
    rights_id = f"rights-{uuid4()}"
    acquisition_id = f"acquisition-{uuid4()}"
    authorization_id = f"upload-{uuid4()}" if expects_bytes else None
    now = utc_now()
    receipt_sha256 = _receipt_hash(request)
    observation_method = {
        "manual_file": "human_file_selection",
        "manual_locator": "human_locator_entry",
    }[source_kind]
    observation_state = {
        "manual_file": "observed",
        "manual_locator": "locator_only",
    }[source_kind]
    occurrence_kind = {
        "manual_file": "manual_selection",
        "manual_locator": "manual_locator",
    }[source_kind]
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source_id, vault_id, source_kind, platform_label, display_label, actor.actor_id, now),
        )
        connection.execute(
            "INSERT INTO source_items VALUES (?, ?, ?, ?, 'current', ?, ?)",
            (item_id, vault_id, source_id, locator, actor.actor_id, now),
        )
        connection.execute(
            "INSERT INTO occurrences VALUES (?, ?, ?, ?, ?, ?, ?)",
            (occurrence_id, vault_id, item_id, occurrence_kind, now, actor.actor_id, now),
        )
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                observation_id,
                vault_id,
                occurrence_id,
                actor.actor_id,
                observation_method,
                now,
                observation_state,
                human_classification_note,
                receipt_sha256,
                now,
            ),
        )
        connection.execute(
            """INSERT INTO rights_retention_versions
            VALUES (?, ?, 'allow', NULL, 'unknown', 'unknown', 'unknown',
                    'unknown', 'deny', 'unknown', ?, ?, ?, ?)""",
            (
                rights_id,
                vault_id,
                policy_basis_reference,
                human_classification_note or "",
                actor.actor_id,
                now,
            ),
        )
        final_state = "started" if expects_bytes else "finalized"
        outcome = None if expects_bytes else "no_artifact"
        finalized_at = None if expects_bytes else now
        connection.execute(
            """INSERT INTO acquisitions
            (id, vault_account_id, observation_id, actor_id, lifecycle_state, outcome,
             operation_key, correlation_id, started_at, finalized_at, error_class,
             error_code, supplied_filename, supplied_media_type,
             rights_retention_version_id, receipt_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)""",
            (
                acquisition_id,
                vault_id,
                observation_id,
                actor.actor_id,
                final_state,
                outcome,
                operation_key,
                actor.correlation_id,
                now,
                finalized_at,
                supplied_filename,
                supplied_media_type,
                rights_id,
                receipt_sha256,
            ),
        )
        if authorization_id is not None:
            connection.execute(
                "INSERT INTO intake_upload_authorizations VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (
                    authorization_id,
                    vault_id,
                    acquisition_id,
                    f"upload:{operation_key}",
                    MAX_ARTIFACT_BYTES,
                    now,
                ),
            )
        record_vault_operation(
            connection,
            actor=actor,
            operation_type="start_intake",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=acquisition_id,
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="human_decision",
            request_sha256=request_sha256,
            record_type="acquisition",
            record_id=acquisition_id,
            payload={
                "source_id": source_id,
                "source_item_id": item_id,
                "occurrence_id": occurrence_id,
                "observation_id": observation_id,
                "rights_retention_version_id": rights_id,
                "lifecycle_state": final_state,
                "outcome": outcome,
                "expects_bytes": expects_bytes,
            },
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return IntakeResult(
        "ready_for_upload" if expects_bytes else "recorded",
        acquisition_id,
        acquisition_id,
        authorization_id,
        None,
    )


def _record_artifact_failure(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    acquisition_id: str,
    error_class: str,
    error_code: str,
    request_sha256: str,
    reconciliation_required: bool = False,
) -> None:
    now = utc_now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            "SELECT lifecycle_state FROM acquisitions WHERE vault_account_id=? AND id=?",
            (actor.vault_account_id, acquisition_id),
        ).fetchone()
        if row is not None and str(row[0]) == "started":
            connection.execute(
                """UPDATE acquisitions
                SET lifecycle_state='interrupted', outcome='failed', finalized_at=?,
                    error_class=?, error_code=?
                WHERE vault_account_id=? AND id=? AND lifecycle_state='started'""",
                (now, error_class, error_code, actor.vault_account_id, acquisition_id),
            )
            append_vault_audit(
                connection,
                actor=actor,
                authority_operation="vault_admin",
                request_sha256=request_sha256,
                record_type="acquisition",
                record_id=acquisition_id,
                payload={"lifecycle_state": "interrupted", "outcome": "failed", "error_code": error_code},
            )
        if reconciliation_required:
            connection.execute(
                """INSERT OR IGNORE INTO reconciliation_work
                (id, vault_account_id, correlation_id, operation_type, state,
                 request_sha256, created_at, resolved_at, resolution_sha256)
                VALUES (?, ?, ?, 'admit_artifact', 'required', ?, ?, NULL, NULL)""",
                (
                    f"reconcile-{uuid4()}",
                    actor.vault_account_id,
                    actor.correlation_id,
                    request_sha256,
                    now,
                ),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def admit_artifact(
    connection: sqlite3.Connection,
    *,
    vault_root: Path,
    actor: ActorContext,
    acquisition_id: str,
    upload_authorization_id: str,
    operation_key: str,
    stream: BinaryIO,
    supplied_filename: str | None,
    supplied_media_type: str | None,
) -> ArtifactAdmissionResult:
    _require_actor(connection, actor)
    acquisition_id = _bounded_text(
        acquisition_id,
        field="acquisition ID",
        maximum=MAX_IDENTIFIER_CHARS,
        required=True,
    )
    upload_authorization_id = _bounded_text(
        upload_authorization_id,
        field="upload authorization ID",
        maximum=MAX_IDENTIFIER_CHARS,
        required=True,
    )
    operation_key = _bounded_text(
        operation_key,
        field="operation key",
        maximum=MAX_OPERATION_KEY_CHARS,
        required=True,
    )
    supplied_filename = _bounded_text(
        supplied_filename,
        field="supplied filename",
        maximum=MAX_FILENAME_CHARS,
    )
    supplied_media_type = _bounded_text(
        supplied_media_type,
        field="supplied media type",
        maximum=MAX_MEDIA_TYPE_CHARS,
    )
    assert acquisition_id is not None
    assert upload_authorization_id is not None
    assert operation_key is not None
    row = connection.execute(
        """SELECT a.lifecycle_state, a.outcome, a.rights_retention_version_id,
                  a.supplied_filename, a.supplied_media_type, u.id, u.max_bytes, u.consumed_at
        FROM acquisitions a
        JOIN intake_upload_authorizations u
          ON u.vault_account_id=a.vault_account_id AND u.acquisition_id=a.id
        WHERE a.vault_account_id=? AND a.id=?""",
        (actor.vault_account_id, acquisition_id),
    ).fetchone()
    if row is None:
        raise ValueError("unknown acquisition or upload authorization")
    if str(row[5]) != upload_authorization_id:
        raise PermissionError("upload authorization does not match the acquisition")
    rights_id = str(row[2])
    policy = connection.execute(
        """SELECT retention_eligible, retention_deadline
        FROM rights_retention_versions WHERE vault_account_id=? AND id=?""",
        (actor.vault_account_id, rights_id),
    ).fetchone()
    if policy is None or str(policy[0]) != "allow" or policy[1] is not None:
        raise PermissionError("artifact admission requires preservation-compatible retention")

    request_base = {
        "vault_id": actor.vault_account_id,
        "actor_id": actor.actor_id,
        "acquisition_id": acquisition_id,
        "upload_authorization_id": upload_authorization_id,
        "supplied_filename": supplied_filename,
        "supplied_media_type": supplied_media_type,
    }
    failure_request_sha256 = request_hash(request_base)
    operation_id = f"admit-{sha256_bytes(operation_key.encode('utf-8'))[:32]}"
    try:
        staged = stage_stream(
            vault_root,
            operation_id=operation_id,
            stream=stream,
            max_bytes=int(row[6]),
        )
    except ArtifactLimitExceeded:
        _record_artifact_failure(
            connection,
            actor=actor,
            acquisition_id=acquisition_id,
            error_class="limit",
            error_code="artifact_limit_exceeded",
            request_sha256=failure_request_sha256,
        )
        raise
    except Exception as exc:
        _record_artifact_failure(
            connection,
            actor=actor,
            acquisition_id=acquisition_id,
            error_class=type(exc).__name__,
            error_code="artifact_storage_failed",
            request_sha256=failure_request_sha256,
            reconciliation_required=True,
        )
        raise

    request_sha256 = request_hash(
        {
            **request_base,
            "sha256": staged.sha256,
            "byte_size": staged.byte_size,
        }
    )
    try:
        existing = existing_vault_operation(
            connection,
            actor=actor,
            operation_type="admit_artifact",
            operation_key=operation_key,
            request_sha256=request_sha256,
        )
    except Exception:
        discard_staged(staged)
        raise
    if existing is not None:
        existing_row = connection.execute(
            """SELECT ao.id, ao.sha256, ao.byte_size, ao.storage_relative_path
            FROM acquisition_artifact_links link
            JOIN artifact_objects ao
              ON ao.vault_account_id=link.vault_account_id AND ao.id=link.artifact_object_id
            WHERE link.vault_account_id=? AND link.acquisition_id=?""",
            (actor.vault_account_id, acquisition_id),
        ).fetchone()
        discard_staged(staged)
        if existing_row is None or str(existing_row[0]) != existing:
            raise RuntimeError("prior artifact operation result is missing")
        if str(existing_row[1]) != staged.sha256 or int(existing_row[2]) != staged.byte_size:
            raise RuntimeError("prior artifact operation bytes disagree with replay")
        return ArtifactAdmissionResult(
            acquisition_id,
            str(existing_row[0]),
            str(existing_row[1]),
            int(existing_row[2]),
            str(existing_row[3]),
            True,
        )

    if str(row[0]) != "started" or row[1] is not None:
        discard_staged(staged)
        raise ValueError("acquisition is not awaiting artifact bytes")
    if row[7] is not None:
        discard_staged(staged)
        raise ValueError("upload authorization has already been consumed")

    try:
        stored = finalize_staged(vault_root, staged)
    except Exception as exc:
        _record_artifact_failure(
            connection,
            actor=actor,
            acquisition_id=acquisition_id,
            error_class=type(exc).__name__,
            error_code="artifact_storage_failed",
            request_sha256=request_sha256,
            reconciliation_required=True,
        )
        raise
    try:
        return _commit_artifact_admission(
            connection,
            actor=actor,
            acquisition_id=acquisition_id,
            upload_authorization_id=upload_authorization_id,
            operation_key=operation_key,
            request_sha256=request_sha256,
            rights_id=rights_id,
            stored=stored,
            supplied_filename=supplied_filename or (str(row[3]) if row[3] is not None else None),
            supplied_media_type=supplied_media_type or (str(row[4]) if row[4] is not None else None),
        )
    except Exception:
        connection.rollback()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """INSERT OR IGNORE INTO reconciliation_work
                (id, vault_account_id, correlation_id, operation_type, state,
                 request_sha256, created_at, resolved_at, resolution_sha256)
                VALUES (?, ?, ?, 'admit_artifact', 'required', ?, ?, NULL, NULL)""",
                (
                    f"reconcile-{uuid4()}",
                    actor.vault_account_id,
                    actor.correlation_id,
                    request_sha256,
                    utc_now(),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
        raise


def _commit_artifact_admission(
    connection: sqlite3.Connection,
    *,
    actor: ActorContext,
    acquisition_id: str,
    upload_authorization_id: str,
    operation_key: str,
    request_sha256: str,
    rights_id: str,
    stored: StoredArtifact,
    supplied_filename: str | None,
    supplied_media_type: str | None,
) -> ArtifactAdmissionResult:
    now = utc_now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing_object = connection.execute(
            "SELECT id, byte_size, storage_relative_path FROM artifact_objects WHERE vault_account_id=? AND sha256=?",
            (actor.vault_account_id, stored.sha256),
        ).fetchone()
        if existing_object is None:
            artifact_id = f"artifact-{uuid4()}"
            connection.execute(
                "INSERT INTO artifact_objects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    actor.vault_account_id,
                    stored.sha256,
                    stored.byte_size,
                    stored.storage_relative_path,
                    supplied_media_type or "application/octet-stream",
                    now,
                ),
            )
        else:
            artifact_id = str(existing_object[0])
            if int(existing_object[1]) != stored.byte_size or str(existing_object[2]) != stored.storage_relative_path:
                raise ArtifactIntegrityError("artifact database metadata disagrees with content address")
        link_id = f"artifact-link-{uuid4()}"
        receipt = {
            "acquisition_id": acquisition_id,
            "artifact_id": artifact_id,
            "sha256": stored.sha256,
            "byte_size": stored.byte_size,
            "storage_relative_path": stored.storage_relative_path,
            "rights_retention_version_id": rights_id,
        }
        receipt_sha256 = _receipt_hash(receipt)
        connection.execute(
            """INSERT INTO acquisition_artifact_links
            VALUES (?, ?, ?, ?, 'original', ?, ?, ?, ?, ?)""",
            (
                link_id,
                actor.vault_account_id,
                acquisition_id,
                artifact_id,
                supplied_filename,
                supplied_media_type,
                rights_id,
                receipt_sha256,
                now,
            ),
        )
        current = connection.execute(
            """SELECT binding.id FROM artifact_policy_bindings binding
            WHERE binding.vault_account_id=? AND binding.artifact_object_id=?
              AND binding.binding_state='current'
              AND NOT EXISTS (
                  SELECT 1 FROM artifact_policy_bindings successor
                  WHERE successor.vault_account_id=binding.vault_account_id
                    AND successor.supersedes_binding_id=binding.id
              )""",
            (actor.vault_account_id, artifact_id),
        ).fetchone()
        binding_id = f"policy-binding-{uuid4()}"
        connection.execute(
            """INSERT INTO artifact_policy_bindings
            VALUES (?, ?, ?, ?, 'current', ?, ?, ?)""",
            (
                binding_id,
                actor.vault_account_id,
                artifact_id,
                rights_id,
                str(current[0]) if current is not None else None,
                actor.actor_id,
                now,
            ),
        )
        updated = connection.execute(
            """UPDATE acquisitions
            SET lifecycle_state='finalized', outcome='succeeded', finalized_at=?,
                error_class=NULL, error_code=NULL
            WHERE vault_account_id=? AND id=? AND lifecycle_state='started' AND outcome IS NULL""",
            (now, actor.vault_account_id, acquisition_id),
        )
        if updated.rowcount != 1:
            raise ValueError("acquisition lifecycle changed during artifact admission")
        consumed = connection.execute(
            """UPDATE intake_upload_authorizations SET consumed_at=?
            WHERE vault_account_id=? AND id=? AND consumed_at IS NULL""",
            (now, actor.vault_account_id, upload_authorization_id),
        )
        if consumed.rowcount != 1:
            raise ValueError("upload authorization is no longer available")
        record_vault_operation(
            connection,
            actor=actor,
            operation_type="admit_artifact",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=artifact_id,
        )
        append_vault_audit(
            connection,
            actor=actor,
            authority_operation="vault_admin",
            request_sha256=request_sha256,
            record_type="artifact_object",
            record_id=artifact_id,
            payload=receipt,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return ArtifactAdmissionResult(
        acquisition_id=acquisition_id,
        artifact_id=artifact_id,
        sha256=stored.sha256,
        byte_size=stored.byte_size,
        storage_relative_path=stored.storage_relative_path,
        reused_existing=stored.reused_existing or existing_object is not None,
    )


def admit_bytes(
    connection: sqlite3.Connection,
    *,
    vault_root: Path,
    actor: ActorContext,
    acquisition_id: str,
    upload_authorization_id: str,
    operation_key: str,
    content: bytes,
    supplied_filename: str | None = None,
    supplied_media_type: str | None = None,
) -> ArtifactAdmissionResult:
    return admit_artifact(
        connection,
        vault_root=vault_root,
        actor=actor,
        acquisition_id=acquisition_id,
        upload_authorization_id=upload_authorization_id,
        operation_key=operation_key,
        stream=io.BytesIO(content),
        supplied_filename=supplied_filename,
        supplied_media_type=supplied_media_type,
    )


def list_intake_records(connection: sqlite3.Connection, *, vault_account_id: str) -> dict[str, list[dict[str, object]]]:
    acquisitions = [
        dict(row)
        for row in connection.execute(
            """SELECT a.id, a.lifecycle_state, a.outcome, a.started_at, a.finalized_at,
                      a.supplied_filename, a.supplied_media_type, a.error_code,
                      o.observation_method, o.observation_state
            FROM acquisitions a
            JOIN observations o
              ON o.vault_account_id=a.vault_account_id AND o.id=a.observation_id
            WHERE a.vault_account_id=? ORDER BY a.started_at DESC, a.id DESC""",
            (vault_account_id,),
        )
    ]
    artifacts = [
        dict(row)
        for row in connection.execute(
            """SELECT id, sha256, byte_size, storage_relative_path, media_type_observed, created_at
            FROM artifact_objects WHERE vault_account_id=? ORDER BY created_at DESC, id DESC""",
            (vault_account_id,),
        )
    ]
    rejections = [
        dict(row)
        for row in connection.execute(
            """SELECT id, attempted_source_kind, descriptor_class, retention_classification,
                      reason_code, occurred_at
            FROM intake_rejection_receipts WHERE vault_account_id=?
            ORDER BY occurred_at DESC, id DESC""",
            (vault_account_id,),
        )
    ]
    return {"acquisitions": acquisitions, "artifacts": artifacts, "rejections": rejections}
