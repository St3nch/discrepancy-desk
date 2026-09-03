"""Capture, Surface, Locator, Excerpt, and integrity behavior."""

from __future__ import annotations

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from psycopg import Connection

from discrepancy_desk.db import admission
from discrepancy_desk.errors import EvidenceContractError, RecordNotFoundError
from discrepancy_desk.vault import PayloadRef, Vault


@dataclass(frozen=True, slots=True)
class CaptureReceipt:
    capture_id: str
    artifact_id: str
    payload: PayloadRef


@dataclass(frozen=True, slots=True)
class SurfaceRef:
    surface_id: str
    artifact_id: str
    payload: PayloadRef


@dataclass(frozen=True, slots=True)
class VerificationResult:
    artifacts_verified: int
    surfaces_verified: int
    locators_verified: int
    excerpts_verified: int


def capture_local_file(
    conn: Connection,
    vault: Vault,
    *,
    file_public_id: str,
    source_path: Path,
    acquisition_url: str,
    retrieved_at: datetime,
    reported_media_type: str | None,
    detected_media_type: str,
    expected_sha256: str,
    expected_byte_size: int,
    page_count: int | None,
    duration_ms: int | None,
    asserted_source_identity: str | None,
    asserted_by: str | None,
    identity_verification_state: str,
    identity_verification_basis: str | None,
    provenance_note: str,
    relevance_note: str,
) -> CaptureReceipt:
    parsed = urlsplit(acquisition_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EvidenceContractError("Capture requires the actual HTTP(S) acquisition URL")
    if retrieved_at.tzinfo is None:
        raise EvidenceContractError("Capture retrieval time must be timezone-aware")
    if identity_verification_state not in {"unverified", "contested"}:
        raise EvidenceContractError(
            "Verified source identity is unavailable until a durable verification seam exists"
        )
    if bool(asserted_source_identity) != bool(asserted_by):
        raise EvidenceContractError("A source-identity assertion requires its asserting source")
    if identity_verification_state == "contested" and not all(
        (asserted_source_identity, asserted_by, identity_verification_basis)
    ):
        raise EvidenceContractError("Contested source identity requires an assertion and basis")
    if not provenance_note.strip() or not relevance_note.strip():
        raise EvidenceContractError("Capture provenance and File relevance are required")
    if (
        len(expected_sha256) != 64
        or expected_sha256.lower() != expected_sha256
        or any(character not in "0123456789abcdef" for character in expected_sha256)
        or expected_byte_size < 0
    ):
        raise EvidenceContractError("Capture requires a valid expected SHA-256 and byte size")
    _validate_media_metadata(detected_media_type, page_count, duration_ms)

    payload = vault.put_file(source_path, detected_media_type)
    if payload.digest != expected_sha256 or payload.byte_size != expected_byte_size:
        raise EvidenceContractError("Captured bytes do not match the accepted digest and byte size")

    capture_id = str(uuid.uuid4())
    candidate_artifact_id = str(uuid.uuid4())
    with admission(conn, label=f"capture {source_path.name}") as admission_order:
        file_id = _file_id(conn, file_public_id)
        inserted = conn.execute(
            """
            INSERT INTO desk.artifact (
                artifact_id, hash_algorithm, digest, byte_size, media_type,
                vault_key, page_count, duration_ms, admission_order
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash_algorithm, digest) DO NOTHING
            RETURNING artifact_id
            """,
            (
                candidate_artifact_id,
                payload.hash_algorithm,
                payload.digest,
                payload.byte_size,
                payload.media_type,
                payload.vault_key,
                page_count,
                duration_ms,
                admission_order,
            ),
        ).fetchone()
        if inserted is None:
            existing = conn.execute(
                """
                SELECT artifact_id, byte_size, media_type, vault_key,
                       page_count, duration_ms
                FROM desk.artifact
                WHERE hash_algorithm = %s AND digest = %s
                """,
                (payload.hash_algorithm, payload.digest),
            ).fetchone()
            if existing is None:
                raise EvidenceContractError("Artifact deduplication lost the existing row")
            if existing[1:] != (
                payload.byte_size,
                payload.media_type,
                payload.vault_key,
                page_count,
                duration_ms,
            ):
                raise EvidenceContractError("Existing Artifact conflicts with captured payload")
            artifact_id = str(existing[0])
        else:
            artifact_id = str(inserted[0])

        conn.execute(
            """
            INSERT INTO desk.capture (
                capture_id, artifact_id, acquisition_url, acquisition_host,
                retrieved_at, reported_media_type, expected_hash_algorithm,
                expected_digest, expected_byte_size, asserted_source_identity,
                asserted_by, identity_verification_state,
                identity_verification_basis, provenance_note, admission_order
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 'sha256', %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                capture_id,
                artifact_id,
                acquisition_url,
                parsed.hostname,
                retrieved_at,
                reported_media_type,
                expected_sha256,
                expected_byte_size,
                asserted_source_identity,
                asserted_by,
                identity_verification_state,
                identity_verification_basis,
                provenance_note,
                admission_order,
            ),
        )
        conn.execute(
            """
            INSERT INTO desk.file_capture
                (file_id, capture_id, relevance_note, admission_order)
            VALUES (%s, %s, %s, %s)
            """,
            (file_id, capture_id, relevance_note, admission_order),
        )
    return CaptureReceipt(capture_id=capture_id, artifact_id=artifact_id, payload=payload)


def add_document_page_locator(
    conn: Connection,
    *,
    artifact_id: str,
    page_number: int,
) -> str:
    if page_number <= 0:
        raise EvidenceContractError("Document page numbers are one-based")
    return _insert_locator(
        conn,
        locator_kind="document_page",
        artifact_id=artifact_id,
        page_number=page_number,
    )


def add_document_text_locator(
    conn: Connection,
    *,
    surface_id: str,
    page_number: int,
    start_char: int,
    end_char: int,
) -> str:
    if page_number <= 0 or start_char < 0 or end_char <= start_char:
        raise EvidenceContractError("Invalid document text range")
    return _insert_locator(
        conn,
        locator_kind="document_page_char_range",
        surface_id=surface_id,
        page_number=page_number,
        start_char=start_char,
        end_char=end_char,
    )


def add_media_time_locator(
    conn: Connection,
    *,
    artifact_id: str,
    start_ms: int,
    end_ms: int,
) -> str:
    if start_ms < 0 or end_ms <= start_ms:
        raise EvidenceContractError("Invalid media time range")
    return _insert_locator(
        conn,
        locator_kind="media_time_range",
        artifact_id=artifact_id,
        start_ms=start_ms,
        end_ms=end_ms,
    )


def _insert_locator(
    conn: Connection,
    *,
    locator_kind: str,
    artifact_id: str | None = None,
    surface_id: str | None = None,
    page_number: int | None = None,
    start_char: int | None = None,
    end_char: int | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> str:
    locator_id = str(uuid.uuid4())
    with admission(conn, label=f"locator {locator_kind}") as admission_order:
        conn.execute(
            """
            INSERT INTO desk.locator (
                locator_id, locator_kind, contract_version, artifact_id,
                surface_id, page_number, start_char, end_char,
                start_ms, end_ms, admission_order
            )
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                locator_id,
                locator_kind,
                artifact_id,
                surface_id,
                page_number,
                start_char,
                end_char,
                start_ms,
                end_ms,
                admission_order,
            ),
        )
    return locator_id


def add_text_surface(
    conn: Connection,
    vault: Vault,
    *,
    artifact_id: str,
    source_locator_id: str,
    surface_kind: str,
    text: str,
    produced_by_method: str,
    produced_by_actor: str,
    produced_by_version: str | None = None,
    produced_at: datetime,
) -> SurfaceRef:
    if produced_at.tzinfo is None:
        raise EvidenceContractError("Surface production time must be timezone-aware")
    normalized = unicodedata.normalize("NFC", text)
    if normalized != text:
        raise EvidenceContractError("Text Surfaces must already be NFC-normalized")
    if not text:
        raise EvidenceContractError("Text Surface payload cannot be empty")
    _assert_locator_resolves_to_artifact(conn, source_locator_id, artifact_id)
    payload = vault.put_bytes(text.encode("utf-8"), "text/plain; charset=utf-8")
    surface_id = str(uuid.uuid4())
    with admission(conn, label=f"surface {surface_kind}") as admission_order:
        conn.execute(
            """
            INSERT INTO desk.surface (
                surface_id, artifact_id, surface_kind, produced_by_method,
                produced_by_actor, produced_by_version, produced_at,
                hash_algorithm, digest, byte_size, media_type, text_length,
                vault_key, source_locator_id, admission_order
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                surface_id,
                artifact_id,
                surface_kind,
                produced_by_method,
                produced_by_actor,
                produced_by_version,
                produced_at,
                payload.hash_algorithm,
                payload.digest,
                payload.byte_size,
                payload.media_type,
                len(text),
                payload.vault_key,
                source_locator_id,
                admission_order,
            ),
        )
    return SurfaceRef(surface_id=surface_id, artifact_id=artifact_id, payload=payload)


def add_excerpt(
    conn: Connection,
    vault: Vault,
    *,
    locator_id: str,
    capture_id: str,
    exact_text: str,
    surface_id: str | None = None,
) -> str:
    if not exact_text:
        raise EvidenceContractError("Excerpt text cannot be empty")
    _assert_capture_matches_locator(conn, capture_id, locator_id)
    _verify_excerpt_selection(conn, vault, locator_id, surface_id, exact_text)
    excerpt_id = str(uuid.uuid4())
    digest = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
    with admission(conn, label="excerpt") as admission_order:
        conn.execute(
            """
            INSERT INTO desk.excerpt (
                excerpt_id, locator_id, surface_id, capture_id, exact_text,
                hash_algorithm, digest, admission_order
            )
            VALUES (%s, %s, %s, %s, %s, 'sha256', %s, %s)
            """,
            (
                excerpt_id,
                locator_id,
                surface_id,
                capture_id,
                exact_text,
                digest,
                admission_order,
            ),
        )
    return excerpt_id


def verify_file_evidence(
    conn: Connection,
    vault: Vault,
    *,
    file_public_id: str,
) -> VerificationResult:
    file_id = _file_id(conn, file_public_id)
    artifact_rows = conn.execute(
        """
        SELECT DISTINCT a.hash_algorithm, a.digest, a.byte_size, a.media_type, a.vault_key
        FROM desk.file_capture fc
        JOIN desk.capture c ON c.capture_id = fc.capture_id
        JOIN desk.artifact a ON a.artifact_id = c.artifact_id
        WHERE fc.file_id = %s
        """,
        (file_id,),
    ).fetchall()
    capture_rows = conn.execute(
        """
        SELECT c.capture_id, c.expected_digest, c.expected_byte_size,
               a.digest, a.byte_size
        FROM desk.file_capture fc
        JOIN desk.capture c ON c.capture_id = fc.capture_id
        JOIN desk.artifact a ON a.artifact_id = c.artifact_id
        WHERE fc.file_id = %s
        """,
        (file_id,),
    ).fetchall()
    surface_rows = conn.execute(
        """
        SELECT DISTINCT s.hash_algorithm, s.digest, s.byte_size, s.media_type, s.vault_key
        FROM desk.file_capture fc
        JOIN desk.capture c ON c.capture_id = fc.capture_id
        JOIN desk.surface s ON s.artifact_id = c.artifact_id
        WHERE fc.file_id = %s
        """,
        (file_id,),
    ).fetchall()
    excerpt_rows = conn.execute(
        """
        SELECT DISTINCT e.locator_id, e.surface_id, e.capture_id,
                        e.exact_text, e.digest
        FROM desk.file_observation fo
        JOIN desk.observation_excerpt oe ON oe.observation_id = fo.observation_id
        JOIN desk.excerpt e ON e.excerpt_id = oe.excerpt_id
        WHERE fo.file_id = %s
        """,
        (file_id,),
    ).fetchall()

    for row in artifact_rows:
        vault.verify(_payload_ref(row))
    for capture_id, expected_digest, expected_size, actual_digest, actual_size in capture_rows:
        if (expected_digest, expected_size) != (actual_digest, actual_size):
            raise EvidenceContractError(
                f"Capture verification receipt no longer matches Artifact: {capture_id}"
            )
    for row in surface_rows:
        vault.verify(_payload_ref(row))
    locator_ids = {str(row[0]) for row in excerpt_rows}
    for locator_id in locator_ids:
        _verify_locator_bounds(conn, locator_id)
    for locator_id, surface_id, capture_id, exact_text, digest in excerpt_rows:
        if hashlib.sha256(exact_text.encode("utf-8")).hexdigest() != digest:
            raise EvidenceContractError("Stored Excerpt digest does not match its text")
        _assert_capture_matches_locator(conn, str(capture_id), str(locator_id))
        _verify_excerpt_selection(
            conn,
            vault,
            str(locator_id),
            str(surface_id) if surface_id else None,
            exact_text,
        )
    return VerificationResult(
        artifacts_verified=len(artifact_rows),
        surfaces_verified=len(surface_rows),
        locators_verified=len(locator_ids),
        excerpts_verified=len(excerpt_rows),
    )


def _verify_excerpt_selection(
    conn: Connection,
    vault: Vault,
    locator_id: str,
    surface_id: str | None,
    exact_text: str,
) -> None:
    locator = conn.execute(
        """
        SELECT locator_kind, surface_id, start_char, end_char
        FROM desk.locator
        WHERE locator_id = %s
        """,
        (locator_id,),
    ).fetchone()
    if locator is None:
        raise RecordNotFoundError(f"Locator not found: {locator_id}")
    locator_kind, located_surface_id, start_char, end_char = locator
    if locator_kind == "document_page_char_range":
        expected_surface_id = str(located_surface_id)
        if surface_id is not None and surface_id != expected_surface_id:
            raise EvidenceContractError("Excerpt Surface conflicts with its text Locator")
        text = _surface_text(conn, vault, expected_surface_id)
        if end_char > len(text) or text[start_char:end_char] != exact_text:
            raise EvidenceContractError("Excerpt does not match the frozen page-text Surface")
        return
    if surface_id is None:
        raise EvidenceContractError("Page/time Excerpts require a bounded transcription Surface")
    surface = conn.execute(
        "SELECT source_locator_id FROM desk.surface WHERE surface_id = %s",
        (surface_id,),
    ).fetchone()
    if surface is None:
        raise RecordNotFoundError(f"Surface not found: {surface_id}")
    if str(surface[0]) != locator_id:
        raise EvidenceContractError("Transcription Surface does not derive from this Locator")
    if _surface_text(conn, vault, surface_id) != exact_text:
        raise EvidenceContractError("Excerpt must equal the bounded transcription Surface")


def _surface_text(conn: Connection, vault: Vault, surface_id: str) -> str:
    row = conn.execute(
        """
        SELECT hash_algorithm, digest, byte_size, media_type, vault_key
        FROM desk.surface
        WHERE surface_id = %s
        """,
        (surface_id,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"Surface not found: {surface_id}")
    try:
        return vault.read_bytes(_payload_ref(row)).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceContractError("Expected a UTF-8 text Surface") from exc


def _assert_locator_resolves_to_artifact(
    conn: Connection,
    locator_id: str,
    artifact_id: str,
) -> None:
    if _locator_artifact_id(conn, locator_id) != artifact_id:
        raise EvidenceContractError("Surface source Locator does not resolve to its Artifact")


def _assert_capture_matches_locator(
    conn: Connection,
    capture_id: str,
    locator_id: str,
) -> None:
    capture = conn.execute(
        "SELECT artifact_id FROM desk.capture WHERE capture_id = %s",
        (capture_id,),
    ).fetchone()
    if capture is None:
        raise RecordNotFoundError(f"Capture not found: {capture_id}")
    if str(capture[0]) != _locator_artifact_id(conn, locator_id):
        raise EvidenceContractError("Excerpt Capture does not contain its Locator target")


def _locator_artifact_id(conn: Connection, locator_id: str) -> str:
    row = conn.execute(
        """
        SELECT COALESCE(l.artifact_id, s.artifact_id)
        FROM desk.locator l
        LEFT JOIN desk.surface s ON s.surface_id = l.surface_id
        WHERE l.locator_id = %s
        """,
        (locator_id,),
    ).fetchone()
    if row is None or row[0] is None:
        raise RecordNotFoundError(f"Locator not found: {locator_id}")
    return str(row[0])


def _verify_locator_bounds(conn: Connection, locator_id: str) -> None:
    row = conn.execute(
        """
        SELECT l.locator_kind, l.page_number, l.end_char, l.end_ms,
               a.media_type, a.page_count, a.duration_ms,
               s.surface_kind, s.text_length, source.page_number
        FROM desk.locator l
        LEFT JOIN desk.artifact a ON a.artifact_id = l.artifact_id
        LEFT JOIN desk.surface s ON s.surface_id = l.surface_id
        LEFT JOIN desk.locator source ON source.locator_id = s.source_locator_id
        WHERE l.locator_id = %s
        """,
        (locator_id,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"Locator not found: {locator_id}")
    (
        kind,
        page_number,
        end_char,
        end_ms,
        media_type,
        page_count,
        duration_ms,
        surface_kind,
        text_length,
        source_page,
    ) = row
    if kind == "document_page":
        valid = media_type == "application/pdf" and page_number <= page_count
    elif kind == "media_time_range":
        valid = media_type.startswith(("audio/", "video/")) and end_ms <= duration_ms
    elif kind == "document_page_char_range":
        valid = (
            surface_kind == "document_page_text"
            and page_number == source_page
            and end_char <= text_length
        )
    else:
        valid = False
    if not valid:
        raise EvidenceContractError(f"Locator contract is invalid: {locator_id}")


def _validate_media_metadata(
    media_type: str,
    page_count: int | None,
    duration_ms: int | None,
) -> None:
    if not media_type or "/" not in media_type:
        raise EvidenceContractError("Capture requires a detected media type")
    if page_count is not None and page_count <= 0:
        raise EvidenceContractError("Observed page count must be positive")
    if duration_ms is not None and duration_ms <= 0:
        raise EvidenceContractError("Observed media duration must be positive")
    if media_type == "application/pdf" and page_count is None:
        raise EvidenceContractError("PDF Capture requires its observed page count")
    if media_type.startswith(("audio/", "video/")) and duration_ms is None:
        raise EvidenceContractError("Media Capture requires its observed duration")


def _file_id(conn: Connection, public_id: str) -> str:
    row = conn.execute(
        "SELECT file_id FROM desk.file WHERE public_id = %s",
        (public_id,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"File not found: {public_id}")
    return str(row[0])


def _payload_ref(row: tuple) -> PayloadRef:
    return PayloadRef(
        hash_algorithm=row[0],
        digest=row[1],
        byte_size=row[2],
        media_type=row[3],
        vault_key=row[4],
    )
