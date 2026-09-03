"""Durable File, Observation, Claim, Decision, and Discrepancy writes."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from psycopg import Connection

from discrepancy_desk.db import admission
from discrepancy_desk.errors import EvidenceContractError, RecordNotFoundError

_FILE_ID = re.compile(r"^DD-[0-9]{4}$")
_DISCREPANCY_ID = re.compile(r"^D[0-9]{2}$")
_RELATIONS = {"supports", "contradicts"}
_POSTURES = {"open", "supported", "not_supported", "unresolved"}
_LIFECYCLES = {"open", "narrowed", "adequately_explained", "closed"}


@dataclass(frozen=True, slots=True)
class ClaimRef:
    claim_id: str
    claim_version_id: str
    version_number: int


@dataclass(frozen=True, slots=True)
class DiscrepancyRef:
    discrepancy_id: str
    discrepancy_version_id: str
    version_number: int


def open_file(
    conn: Connection,
    *,
    public_id: str,
    subject: str,
    investigation_question: str,
) -> str:
    if not _FILE_ID.fullmatch(public_id):
        raise EvidenceContractError("File identifier must match DD-####")
    _require_text(subject, "File subject")
    _require_text(investigation_question, "File investigation question")
    file_id = str(uuid.uuid4())
    with admission(conn, label=f"open File {public_id}") as admission_order:
        conn.execute(
            """
            INSERT INTO desk.file (
                file_id, public_id, subject, investigation_question, admission_order
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (file_id, public_id, subject, investigation_question, admission_order),
        )
    return file_id


def admit_observation(
    conn: Connection,
    *,
    file_public_id: str,
    statement: str,
    excerpt_ids: Sequence[str],
) -> str:
    _require_text(statement, "Observation statement")
    if not excerpt_ids:
        raise EvidenceContractError("Observation requires at least one Excerpt")
    observation_id = str(uuid.uuid4())
    with admission(conn, label="admit Observation") as admission_order:
        file_id = _file_id(conn, file_public_id)
        _require_rows(conn, "desk.excerpt", "excerpt_id", excerpt_ids, "Excerpt")
        conn.execute(
            """
            INSERT INTO desk.observation (observation_id, statement, admission_order)
            VALUES (%s, %s, %s)
            """,
            (observation_id, statement, admission_order),
        )
        conn.execute(
            """
            INSERT INTO desk.file_observation
                (file_id, observation_id, admission_order)
            VALUES (%s, %s, %s)
            """,
            (file_id, observation_id, admission_order),
        )
        _execute_many(
            conn,
            """
            INSERT INTO desk.observation_excerpt
                (observation_id, excerpt_id, admission_order)
            VALUES (%s, %s, %s)
            """,
            [(observation_id, excerpt_id, admission_order) for excerpt_id in _unique(excerpt_ids)],
        )
    return observation_id


def propose_claim(
    conn: Connection,
    *,
    file_public_id: str,
    proposition: str,
    relevance_note: str,
    observation_basis: Sequence[tuple[str, str]],
) -> ClaimRef:
    _require_text(proposition, "Claim proposition")
    _require_text(relevance_note, "Claim File relevance")
    if not observation_basis:
        raise EvidenceContractError("Claim requires an Observation basis")
    for _, relation_kind in observation_basis:
        if relation_kind not in _RELATIONS:
            raise EvidenceContractError("Claim basis must support or contradict")

    claim_id = str(uuid.uuid4())
    claim_version_id = str(uuid.uuid4())
    with admission(conn, label="propose Claim") as admission_order:
        file_id = _file_id(conn, file_public_id)
        observation_ids = [item[0] for item in observation_basis]
        _require_file_observations(conn, file_id, observation_ids)
        conn.execute(
            "INSERT INTO desk.claim (claim_id, admission_order) VALUES (%s, %s)",
            (claim_id, admission_order),
        )
        conn.execute(
            """
            INSERT INTO desk.claim_version (
                claim_version_id, claim_id, version_number, proposition, admission_order
            )
            VALUES (%s, %s, 1, %s, %s)
            """,
            (claim_version_id, claim_id, proposition, admission_order),
        )
        conn.execute(
            """
            INSERT INTO desk.file_claim
                (file_id, claim_id, relevance_note, admission_order)
            VALUES (%s, %s, %s, %s)
            """,
            (file_id, claim_id, relevance_note, admission_order),
        )
        _execute_many(
            conn,
            """
            INSERT INTO desk.claim_version_observation_basis (
                claim_version_id, observation_id, relation_kind, admission_order
            )
            VALUES (%s, %s, %s, %s)
            """,
            [
                (claim_version_id, observation_id, relation_kind, admission_order)
                for observation_id, relation_kind in _unique(observation_basis)
            ],
        )
    return ClaimRef(claim_id, claim_version_id, 1)


def record_decision(
    conn: Connection,
    *,
    claim_version_id: str,
    authorized_by: str,
    decision_text: str,
    posture: str,
    supersedes_decision_id: str | None = None,
) -> str:
    _require_text(authorized_by, "Decision authority")
    _require_text(decision_text, "Decision text")
    if posture not in _POSTURES:
        raise EvidenceContractError("Unsupported Claim posture")
    decision_id = str(uuid.uuid4())
    with admission(conn, label="record human Decision") as admission_order:
        _require_rows(
            conn,
            "desk.claim_version",
            "claim_version_id",
            [claim_version_id],
            "Claim version",
        )
        if supersedes_decision_id is not None:
            _require_rows(
                conn,
                "desk.decision",
                "decision_id",
                [supersedes_decision_id],
                "Decision",
            )
        conn.execute(
            """
            INSERT INTO desk.decision (
                decision_id, authorized_by, decision_text, admission_order
            )
            VALUES (%s, %s, %s, %s)
            """,
            (decision_id, authorized_by, decision_text, admission_order),
        )
        conn.execute(
            """
            INSERT INTO desk.claim_posture_decision_effect (
                decision_id, claim_version_id, posture, admission_order
            )
            VALUES (%s, %s, %s, %s)
            """,
            (decision_id, claim_version_id, posture, admission_order),
        )
        if supersedes_decision_id is not None:
            conn.execute(
                """
                INSERT INTO desk.decision_supersession (
                    decision_id, supersedes_decision_id, admission_order
                )
                VALUES (%s, %s, %s)
                """,
                (decision_id, supersedes_decision_id, admission_order),
            )
    return decision_id


def open_discrepancy(
    conn: Connection,
    *,
    file_public_id: str,
    local_id: str,
    question: str,
    lifecycle_state: str,
    observation_ids: Sequence[str],
    claim_version_ids: Sequence[str],
) -> DiscrepancyRef:
    if not _DISCREPANCY_ID.fullmatch(local_id):
        raise EvidenceContractError("Discrepancy identifier must match D##")
    return _write_discrepancy(
        conn,
        file_public_id=file_public_id,
        local_id=local_id,
        question=question,
        lifecycle_state=lifecycle_state,
        observation_ids=observation_ids,
        claim_version_ids=claim_version_ids,
        existing=None,
    )


def revise_discrepancy(
    conn: Connection,
    *,
    file_public_id: str,
    local_id: str,
    question: str,
    lifecycle_state: str,
    observation_ids: Sequence[str],
    claim_version_ids: Sequence[str],
) -> DiscrepancyRef:
    file_id = _file_id(conn, file_public_id)
    row = conn.execute(
        """
        SELECT d.discrepancy_id, max(dv.version_number)
        FROM desk.discrepancy d
        JOIN desk.discrepancy_version dv
          ON dv.discrepancy_id = d.discrepancy_id
        WHERE d.file_id = %s AND d.local_id = %s
        GROUP BY d.discrepancy_id
        """,
        (file_id, local_id),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"Discrepancy not found: {file_public_id}/{local_id}")
    return _write_discrepancy(
        conn,
        file_public_id=file_public_id,
        local_id=local_id,
        question=question,
        lifecycle_state=lifecycle_state,
        observation_ids=observation_ids,
        claim_version_ids=claim_version_ids,
        existing=(str(row[0]), row[1] + 1),
    )


def _write_discrepancy(
    conn: Connection,
    *,
    file_public_id: str,
    local_id: str,
    question: str,
    lifecycle_state: str,
    observation_ids: Sequence[str],
    claim_version_ids: Sequence[str],
    existing: tuple[str, int] | None,
) -> DiscrepancyRef:
    _require_text(question, "Discrepancy question")
    if lifecycle_state not in _LIFECYCLES:
        raise EvidenceContractError("Unsupported Discrepancy lifecycle state")
    if not observation_ids and not claim_version_ids:
        raise EvidenceContractError("Discrepancy requires Record references")

    discrepancy_id = existing[0] if existing else str(uuid.uuid4())
    version_number = existing[1] if existing else 1
    discrepancy_version_id = str(uuid.uuid4())
    with admission(conn, label=f"record Discrepancy {local_id}") as admission_order:
        file_id = _file_id(conn, file_public_id)
        _require_file_observations(conn, file_id, observation_ids)
        _require_file_claim_versions(conn, file_id, claim_version_ids)
        if existing is None:
            conn.execute(
                """
                INSERT INTO desk.discrepancy (
                    discrepancy_id, file_id, local_id, admission_order
                )
                VALUES (%s, %s, %s, %s)
                """,
                (discrepancy_id, file_id, local_id, admission_order),
            )
        conn.execute(
            """
            INSERT INTO desk.discrepancy_version (
                discrepancy_version_id, discrepancy_id, version_number,
                question, lifecycle_state, admission_order
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                discrepancy_version_id,
                discrepancy_id,
                version_number,
                question,
                lifecycle_state,
                admission_order,
            ),
        )
        _execute_many(
            conn,
            """
            INSERT INTO desk.discrepancy_observation_ref (
                discrepancy_version_id, observation_id, admission_order
            )
            VALUES (%s, %s, %s)
            """,
            [
                (discrepancy_version_id, observation_id, admission_order)
                for observation_id in _unique(observation_ids)
            ],
        )
        _execute_many(
            conn,
            """
            INSERT INTO desk.discrepancy_claim_ref (
                discrepancy_version_id, claim_version_id, admission_order
            )
            VALUES (%s, %s, %s)
            """,
            [
                (discrepancy_version_id, claim_version_id, admission_order)
                for claim_version_id in _unique(claim_version_ids)
            ],
        )
    return DiscrepancyRef(discrepancy_id, discrepancy_version_id, version_number)


def _file_id(conn: Connection, public_id: str) -> str:
    row = conn.execute(
        "SELECT file_id FROM desk.file WHERE public_id = %s",
        (public_id,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError(f"File not found: {public_id}")
    return str(row[0])


def _require_file_observations(
    conn: Connection,
    file_id: str,
    observation_ids: Sequence[str],
) -> None:
    for observation_id in _unique(observation_ids):
        row = conn.execute(
            """
            SELECT 1 FROM desk.file_observation
            WHERE file_id = %s AND observation_id = %s
            """,
            (file_id, observation_id),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(
                f"Observation is not associated with this File: {observation_id}"
            )


def _require_file_claim_versions(
    conn: Connection,
    file_id: str,
    claim_version_ids: Sequence[str],
) -> None:
    for claim_version_id in _unique(claim_version_ids):
        row = conn.execute(
            """
            SELECT 1
            FROM desk.claim_version cv
            JOIN desk.file_claim fc ON fc.claim_id = cv.claim_id
            WHERE fc.file_id = %s AND cv.claim_version_id = %s
            """,
            (file_id, claim_version_id),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(
                f"Claim version is not associated with this File: {claim_version_id}"
            )


def _require_rows(
    conn: Connection,
    table: str,
    column: str,
    values: Sequence[str],
    label: str,
) -> None:
    for value in _unique(values):
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = %s",
            (value,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"{label} not found: {value}")


def _execute_many(conn: Connection, query: str, params: Sequence[tuple]) -> None:
    with conn.cursor() as cursor:
        cursor.executemany(query, params)


def _unique(values: Sequence):
    return list(dict.fromkeys(values))


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise EvidenceContractError(f"{label} is required")
