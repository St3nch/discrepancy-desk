"""Living internal File report and evidence walkback."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from psycopg import Connection

from discrepancy_desk.errors import EvidenceContractError, RecordNotFoundError
from discrepancy_desk.evidence import verify_file_evidence
from discrepancy_desk.vault import Vault


def render_file_report(conn: Connection, *, file_public_id: str) -> str:
    file_row = conn.execute(
        """
        SELECT file_id, subject, investigation_question
        FROM desk.file
        WHERE public_id = %s
        """,
        (file_public_id,),
    ).fetchone()
    if file_row is None:
        raise RecordNotFoundError(f"File not found: {file_public_id}")
    file_id, subject, investigation_question = file_row

    observations = conn.execute(
        """
        SELECT o.observation_id, o.statement
        FROM desk.file_observation fo
        JOIN desk.observation o ON o.observation_id = fo.observation_id
        WHERE fo.file_id = %s
        ORDER BY o.admission_order
        """,
        (file_id,),
    ).fetchall()
    claims = conn.execute(
        """
        SELECT c.claim_id, cv.claim_version_id, cv.version_number, cv.proposition
        FROM desk.file_claim fc
        JOIN desk.claim c ON c.claim_id = fc.claim_id
        JOIN LATERAL (
            SELECT candidate.claim_version_id, candidate.version_number,
                   candidate.proposition
            FROM desk.claim_version candidate
            WHERE candidate.claim_id = c.claim_id
            ORDER BY candidate.version_number DESC
            LIMIT 1
        ) cv ON true
        WHERE fc.file_id = %s
        ORDER BY c.admission_order
        """,
        (file_id,),
    ).fetchall()
    decisions = conn.execute(
        """
        SELECT d.decision_id, d.authorized_by, d.decision_text,
               e.posture, cv.claim_version_id, cv.claim_id,
               cv.version_number, prior.supersedes_decision_id,
               successors.superseded_by
        FROM desk.file_claim fc
        JOIN desk.claim_version cv ON cv.claim_id = fc.claim_id
        JOIN desk.claim_posture_decision_effect e
          ON e.claim_version_id = cv.claim_version_id
        JOIN desk.decision d ON d.decision_id = e.decision_id
        LEFT JOIN desk.decision_supersession prior
          ON prior.decision_id = d.decision_id
        LEFT JOIN LATERAL (
            SELECT array_agg(revision.decision_id ORDER BY revision.admission_order)
                     AS superseded_by
            FROM desk.decision_supersession revision
            WHERE revision.supersedes_decision_id = d.decision_id
        ) successors ON true
        WHERE fc.file_id = %s
        ORDER BY d.admission_order
        """,
        (file_id,),
    ).fetchall()
    discrepancies = conn.execute(
        """
        SELECT d.local_id, dv.discrepancy_version_id, dv.version_number,
               dv.question, dv.lifecycle_state
        FROM desk.discrepancy d
        JOIN LATERAL (
            SELECT candidate.discrepancy_version_id, candidate.version_number,
                   candidate.question, candidate.lifecycle_state
            FROM desk.discrepancy_version candidate
            WHERE candidate.discrepancy_id = d.discrepancy_id
            ORDER BY candidate.version_number DESC
            LIMIT 1
        ) dv ON true
        WHERE d.file_id = %s
        ORDER BY d.local_id
        """,
        (file_id,),
    ).fetchall()

    lines = [
        f"# {file_public_id} — {subject}",
        "",
        investigation_question,
        "",
        "## Observations",
        "",
    ]
    lines.extend(
        _rows_or_empty(
            f"- [O:{observation_id}] {statement}" for observation_id, statement in observations
        )
    )
    lines.extend(["", "## Claims", ""])
    lines.extend(
        _rows_or_empty(
            (
                f"- [C:{version_id}] {proposition} (Claim {claim_id}, version {version_number})"
                for claim_id, version_id, version_number, proposition in claims
            )
        )
    )
    lines.extend(["", "## Human Decisions", ""])
    lines.extend(
        _rows_or_empty(
            f"- [H:{decision_id}] {posture} for "
            f"[C:{claim_version_id}] — {decision_text} "
            f"(authorized by {authorized_by}; Claim {claim_id} version {version_number}"
            f"{_decision_lineage(supersedes, superseded_by)})"
            for (
                decision_id,
                authorized_by,
                decision_text,
                posture,
                claim_version_id,
                claim_id,
                version_number,
                supersedes,
                superseded_by,
            ) in decisions
        )
    )
    lines.extend(["", "## Discrepancies", ""])
    lines.extend(
        _rows_or_empty(
            f"- [D:{version_id}] {question} "
            f"(File handle {local_id}, version {version_number}; state: {lifecycle_state})"
            for (
                local_id,
                version_id,
                version_number,
                question,
                lifecycle_state,
            ) in discrepancies
        )
    )
    return "\n".join(lines) + "\n"


def walkback(
    conn: Connection,
    vault: Vault,
    *,
    object_kind: str,
    object_id: str,
) -> dict[str, Any]:
    if object_kind == "observation":
        observation_ids = [object_id]
    elif object_kind == "claim_version":
        _require_exists(conn, "desk.claim_version", "claim_version_id", object_id)
        observation_ids = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT observation_id
                FROM desk.claim_version_observation_basis
                WHERE claim_version_id = %s
                ORDER BY admission_order
                """,
                (object_id,),
            ).fetchall()
        ]
    elif object_kind == "discrepancy_version":
        _require_exists(
            conn,
            "desk.discrepancy_version",
            "discrepancy_version_id",
            object_id,
        )
        observation_ids = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT observation_id
                FROM desk.discrepancy_observation_ref
                WHERE discrepancy_version_id = %s
                UNION
                SELECT basis.observation_id
                FROM desk.discrepancy_claim_ref claim_ref
                JOIN desk.claim_version_observation_basis basis
                  ON basis.claim_version_id = claim_ref.claim_version_id
                WHERE claim_ref.discrepancy_version_id = %s
                """,
                (object_id, object_id),
            ).fetchall()
        ]
    else:
        raise EvidenceContractError("Unsupported walkback object kind")

    if not observation_ids:
        raise EvidenceContractError("Record object has no Observation evidence path")
    file_public_ids = [
        str(row[0])
        for row in conn.execute(
            """
            SELECT DISTINCT f.public_id
            FROM desk.file_observation fo
            JOIN desk.file f ON f.file_id = fo.file_id
            WHERE fo.observation_id = ANY(%s::uuid[])
            ORDER BY f.public_id
            """,
            (observation_ids,),
        ).fetchall()
    ]
    if not file_public_ids:
        raise EvidenceContractError("Observation evidence is not associated with a File")
    for file_public_id in file_public_ids:
        verify_file_evidence(conn, vault, file_public_id=file_public_id)
    observations = [_observation_walkback(conn, value) for value in observation_ids]
    return {
        "object_kind": object_kind,
        "object_id": object_id,
        "verified_file_public_ids": file_public_ids,
        "observations": observations,
    }


def _observation_walkback(
    conn: Connection,
    observation_id: str,
) -> dict[str, Any]:
    observation = conn.execute(
        """
        SELECT statement
        FROM desk.observation
        WHERE observation_id = %s
        """,
        (observation_id,),
    ).fetchone()
    if observation is None:
        raise RecordNotFoundError(f"Observation not found: {observation_id}")

    rows = conn.execute(
        """
        SELECT
            e.excerpt_id, e.exact_text,
            l.locator_id, l.locator_kind, l.contract_version,
            l.page_number, l.start_char, l.end_char, l.start_ms, l.end_ms,
            COALESCE(excerpt_surface.surface_id, located_surface.surface_id),
            COALESCE(excerpt_surface.surface_kind, located_surface.surface_kind),
            COALESCE(excerpt_surface.produced_by_method, located_surface.produced_by_method),
            COALESCE(excerpt_surface.produced_by_actor, located_surface.produced_by_actor),
            COALESCE(excerpt_surface.produced_by_version, located_surface.produced_by_version),
            COALESCE(excerpt_surface.produced_at, located_surface.produced_at),
            COALESCE(excerpt_surface.hash_algorithm, located_surface.hash_algorithm),
            COALESCE(excerpt_surface.digest, located_surface.digest),
            COALESCE(excerpt_surface.byte_size, located_surface.byte_size),
            COALESCE(excerpt_surface.media_type, located_surface.media_type),
            COALESCE(excerpt_surface.text_length, located_surface.text_length),
            COALESCE(excerpt_surface.vault_key, located_surface.vault_key),
            COALESCE(excerpt_surface.source_locator_id, located_surface.source_locator_id),
            a.artifact_id, a.hash_algorithm, a.digest, a.byte_size,
            a.media_type, a.vault_key, a.page_count, a.duration_ms,
            c.capture_id, c.acquisition_url, c.acquisition_host,
            c.retrieved_at, c.reported_media_type,
            c.expected_hash_algorithm, c.expected_digest, c.expected_byte_size,
            c.asserted_source_identity, c.asserted_by,
            c.identity_verification_state, c.identity_verification_basis,
            c.provenance_note
        FROM desk.observation_excerpt oe
        JOIN desk.excerpt e ON e.excerpt_id = oe.excerpt_id
        JOIN desk.locator l ON l.locator_id = e.locator_id
        LEFT JOIN desk.surface located_surface ON located_surface.surface_id = l.surface_id
        LEFT JOIN desk.surface excerpt_surface ON excerpt_surface.surface_id = e.surface_id
        JOIN desk.artifact a
          ON a.artifact_id = COALESCE(l.artifact_id, located_surface.artifact_id)
        JOIN desk.capture c ON c.capture_id = e.capture_id
        WHERE oe.observation_id = %s
        ORDER BY e.admission_order
        """,
        (observation_id,),
    ).fetchall()
    evidence = []
    for row in rows:
        (
            excerpt_id,
            exact_text,
            locator_id,
            locator_kind,
            contract_version,
            page_number,
            start_char,
            end_char,
            start_ms,
            end_ms,
            surface_id,
            surface_kind,
            produced_by_method,
            produced_by_actor,
            produced_by_version,
            produced_at,
            surface_hash_algorithm,
            surface_digest,
            surface_byte_size,
            surface_media_type,
            surface_text_length,
            surface_vault_key,
            source_locator_id,
            artifact_id,
            hash_algorithm,
            digest,
            byte_size,
            media_type,
            vault_key,
            page_count,
            duration_ms,
            capture_id,
            acquisition_url,
            acquisition_host,
            retrieved_at,
            reported_media_type,
            expected_hash_algorithm,
            expected_digest,
            expected_byte_size,
            asserted_source_identity,
            asserted_by,
            verification_state,
            verification_basis,
            provenance_note,
        ) = row
        evidence.append(
            {
                "excerpt": {
                    "excerpt_id": str(excerpt_id),
                    "exact_text": exact_text,
                    "exact_text_authority": "non_authoritative_convenience_copy",
                },
                "locator": {
                    "locator_id": str(locator_id),
                    "locator_kind": locator_kind,
                    "contract_version": contract_version,
                    "page_number": page_number,
                    "start_char": start_char,
                    "end_char": end_char,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                },
                "surface": (
                    {
                        "surface_id": str(surface_id),
                        "surface_kind": surface_kind,
                        "produced_by_method": produced_by_method,
                        "produced_by_actor": produced_by_actor,
                        "produced_by_version": produced_by_version,
                        "produced_at": _timestamp(produced_at),
                        "hash_algorithm": surface_hash_algorithm,
                        "digest": surface_digest,
                        "byte_size": surface_byte_size,
                        "media_type": surface_media_type,
                        "text_length": surface_text_length,
                        "vault_key": surface_vault_key,
                        "source_locator_id": str(source_locator_id),
                        "artifact_id": str(artifact_id),
                    }
                    if surface_id is not None
                    else None
                ),
                "artifact": {
                    "artifact_id": str(artifact_id),
                    "hash_algorithm": hash_algorithm,
                    "digest": digest,
                    "byte_size": byte_size,
                    "media_type": media_type,
                    "vault_key": vault_key,
                    "page_count": page_count,
                    "duration_ms": duration_ms,
                },
                "capture": {
                    "capture_id": str(capture_id),
                    "acquisition_url": acquisition_url,
                    "acquisition_host": acquisition_host,
                    "retrieved_at": _timestamp(retrieved_at),
                    "reported_media_type": reported_media_type,
                    "expected_hash_algorithm": expected_hash_algorithm,
                    "expected_digest": expected_digest,
                    "expected_byte_size": expected_byte_size,
                    "asserted_source_identity": asserted_source_identity,
                    "asserted_by": asserted_by,
                    "identity_verification_state": verification_state,
                    "identity_verification_basis": verification_basis,
                    "provenance_note": provenance_note,
                },
            }
        )
    if not evidence:
        raise EvidenceContractError("Observation has no Excerpt evidence path")
    return {
        "observation_id": observation_id,
        "statement": observation[0],
        "evidence": evidence,
    }


def _require_exists(
    conn: Connection,
    table: str,
    column: str,
    object_id: str,
) -> None:
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE {column} = %s",
        (object_id,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"Record object not found: {object_id}")


def _rows_or_empty(rows: Iterable[str]) -> list[str]:
    values = list(rows)
    return values or ["- None admitted."]


def _decision_lineage(
    supersedes: object | None,
    superseded_by: list[object] | None,
) -> str:
    details = []
    if supersedes is not None:
        details.append(f"supersedes H:{supersedes}")
    if superseded_by:
        details.append(
            "superseded by " + ", ".join(f"H:{decision_id}" for decision_id in superseded_by)
        )
    return "; " + "; ".join(details) if details else ""


def _timestamp(value: datetime) -> str:
    return value.isoformat()
