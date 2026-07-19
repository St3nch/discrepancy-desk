from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .binding import RevisionBundle, binding_bytes, revision_binding
from .db import begin_write

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "captured": {"research_needed", "research_ready", "drafting", "withdrawn"},
    "research_needed": {"research_ready", "withdrawn"},
    "research_ready": {"drafting", "withdrawn"},
    "drafting": {"human_review_needed", "withdrawn"},
    "human_review_needed": {"approved", "rejected", "drafting", "evidence_blocked"},
    "approved": {"manual_ready", "human_review_needed", "evidence_blocked", "withdrawn"},
    "manual_ready": {"published", "human_review_needed", "publication_mismatch", "evidence_blocked", "withdrawn"},
    "published": set(),
    "rejected": {"drafting"},
    "withdrawn": {"drafting"},
    "publication_mismatch": {"human_review_needed", "published"},
    "evidence_blocked": {"human_review_needed", "drafting"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def append_audit(
    connection: sqlite3.Connection,
    *,
    actor_type: str,
    actor_id: str,
    operation: str,
    record_type: str,
    record_id: str,
    payload: object,
) -> str:
    previous = connection.execute(
        "SELECT chain_sha256 FROM audit_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous[0] if previous else None
    event_id = str(uuid4())
    occurred_at = utc_now()
    payload_bytes = _json_bytes(payload)
    event_material = _json_bytes(
        {
            "id": event_id,
            "occurred_at": occurred_at,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "operation": operation,
            "record_type": record_type,
            "record_id": record_id,
            "payload_sha256": _hash(payload_bytes),
            "previous_chain_sha256": previous_hash,
        }
    )
    event_hash = _hash(event_material)
    chain_hash = _hash(((previous_hash or "") + event_hash).encode("ascii"))
    connection.execute(
        """INSERT INTO audit_events
        (id, occurred_at, actor_type, actor_id, operation, record_type, record_id,
         payload_json, previous_chain_sha256, event_sha256, chain_sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            occurred_at,
            actor_type,
            actor_id,
            operation,
            record_type,
            record_id,
            payload_bytes,
            previous_hash,
            event_hash,
            chain_hash,
        ),
    )
    return event_id


def verify_audit_chain(connection: sqlite3.Connection) -> bool:
    previous: str | None = None
    for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence"):
        payload_hash = _hash(bytes(row[8]))
        material = _json_bytes(
            {
                "id": row[1],
                "occurred_at": row[2],
                "actor_type": row[3],
                "actor_id": row[4],
                "operation": row[5],
                "record_type": row[6],
                "record_id": row[7],
                "payload_sha256": payload_hash,
                "previous_chain_sha256": previous,
            }
        )
        event_hash = _hash(material)
        chain_hash = _hash(((previous or "") + event_hash).encode("ascii"))
        if row[9] != previous or row[10] != event_hash or row[11] != chain_hash:
            return False
        previous = chain_hash
    return True


def transition_work_item(
    connection: sqlite3.Connection,
    work_item_id: str,
    target_state: str,
    *,
    actor_id: str,
) -> None:
    begin_write(connection)
    try:
        row = connection.execute("SELECT state FROM work_items WHERE id = ?", (work_item_id,)).fetchone()
        if row is None:
            raise ValueError("unknown work item")
        source_state = row[0]
        if target_state in {"approved", "manual_ready", "published", "publication_mismatch"}:
            raise ValueError(
                f"illegal transition: {target_state} requires dedicated governed operation"
            )
        if target_state not in LEGAL_TRANSITIONS.get(source_state, set()):
            raise ValueError(f"illegal transition: {source_state} -> {target_state}")
        now = utc_now()
        connection.execute(
            "UPDATE work_items SET state = ?, updated_at = ? WHERE id = ?",
            (target_state, now, work_item_id),
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="transition",
            record_type="work_item",
            record_id=work_item_id,
            payload={"from": source_state, "to": target_state},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def register_evidence(
    connection: sqlite3.Connection,
    evidence_root: Path,
    *,
    evidence_id: str,
    work_item_id: str,
    relative_path: str,
    expected_sha256: str,
) -> None:
    candidate = (evidence_root / relative_path).resolve()
    root = evidence_root.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("evidence path escapes governed root")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    data = candidate.read_bytes()
    actual_hash = _hash(data)
    if actual_hash != expected_sha256:
        raise ValueError("evidence hash mismatch")
    begin_write(connection)
    try:
        connection.execute(
            """INSERT INTO evidence_refs
            (id, work_item_id, relative_path, sha256, byte_size, verification_state, captured_at)
            VALUES (?, ?, ?, ?, ?, 'verified', ?)""",
            (evidence_id, work_item_id, relative_path, actual_hash, len(data), utc_now()),
        )
        append_audit(
            connection,
            actor_type="system",
            actor_id="evidence-verifier",
            operation="register_evidence",
            record_type="evidence_ref",
            record_id=evidence_id,
            payload={"relative_path": relative_path, "sha256": actual_hash, "byte_size": len(data)},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def create_revision(
    connection: sqlite3.Connection,
    *,
    revision_id: str,
    work_item_id: str,
    owned_account_id: str,
    bundle: RevisionBundle,
) -> str:
    binding = revision_binding(bundle)
    begin_write(connection)
    try:
        connection.execute(
            """INSERT INTO revisions
            (id, work_item_id, platform, owned_account_id, authored_text, component_json,
             binding_version, binding_sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                revision_id,
                work_item_id,
                bundle.platform,
                owned_account_id,
                bundle.authored_text.encode("utf-8"),
                binding_bytes(bundle),
                binding,
                utc_now(),
            ),
        )
        append_audit(
            connection,
            actor_type="system",
            actor_id="revision-service",
            operation="create_revision",
            record_type="revision",
            record_id=revision_id,
            payload={"binding_sha256": binding, "bundle": asdict(bundle)},
        )
        connection.commit()
        return binding
    except Exception:
        connection.rollback()
        raise


def approve_revision(
    connection: sqlite3.Connection,
    *,
    approval_id: str,
    revision_id: str,
    binding_sha256: str,
    actor_id: str,
    action_id: str,
) -> None:
    begin_write(connection)
    try:
        row = connection.execute(
            "SELECT binding_sha256, work_item_id FROM revisions WHERE id = ?", (revision_id,)
        ).fetchone()
        if row is None or row[0] != binding_sha256:
            raise ValueError("stale, fabricated, or mismatched approval binding")
        connection.execute(
            """INSERT INTO approvals
            (id, revision_id, binding_sha256, decision, actor_id, decided_at, action_id)
            VALUES (?, ?, ?, 'approved', ?, ?, ?)""",
            (approval_id, revision_id, binding_sha256, actor_id, utc_now(), action_id),
        )
        cursor = connection.execute(
            "UPDATE work_items SET state='approved', updated_at=? WHERE id=? AND state='human_review_needed'",
            (utc_now(), row[1]),
        )
        if cursor.rowcount != 1:
            raise ValueError("approval requires human_review_needed state")
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="approve_revision",
            record_type="approval",
            record_id=approval_id,
            payload={"revision_id": revision_id, "binding_sha256": binding_sha256},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _request_hash(value: object) -> str:
    return _hash(_json_bytes(value))


def _existing_operation(
    connection: sqlite3.Connection, operation_type: str, operation_key: str, request_sha256: str
) -> str | None:
    row = connection.execute(
        "SELECT request_sha256, result_ref FROM operation_keys WHERE operation_type=? AND operation_key=?",
        (operation_type, operation_key),
    ).fetchone()
    if row is None:
        return None
    if row[0] != request_sha256:
        raise ValueError("idempotency key reused with conflicting content")
    return str(row[1])


def _record_operation(
    connection: sqlite3.Connection,
    *,
    operation_type: str,
    operation_key: str,
    request_sha256: str,
    result_ref: str,
) -> None:
    connection.execute(
        "INSERT INTO operation_keys VALUES (?, ?, ?, ?, ?)",
        (operation_type, operation_key, request_sha256, result_ref, utc_now()),
    )


def mark_manual_ready(
    connection: sqlite3.Connection,
    *,
    work_item_id: str,
    approval_id: str,
    actor_id: str,
    operation_key: str,
) -> str:
    request = {"work_item_id": work_item_id, "approval_id": approval_id, "actor_id": actor_id}
    request_sha256 = _request_hash(request)
    begin_write(connection)
    try:
        existing = _existing_operation(connection, "manual_ready", operation_key, request_sha256)
        if existing is not None:
            connection.commit()
            return existing
        row = connection.execute(
            """SELECT r.work_item_id, a.decision
            FROM approvals a JOIN revisions r ON r.id=a.revision_id WHERE a.id=?""",
            (approval_id,),
        ).fetchone()
        if row is None or row[0] != work_item_id or row[1] != "approved":
            raise ValueError("manual-ready requires a current approval for this work item")
        cursor = connection.execute(
            "UPDATE work_items SET state='manual_ready', updated_at=? WHERE id=? AND state='approved'",
            (utc_now(), work_item_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("manual-ready requires approved state")
        append_audit(
            connection, actor_type="human", actor_id=actor_id, operation="manual_ready",
            record_type="work_item", record_id=work_item_id, payload={"approval_id": approval_id},
        )
        _record_operation(
            connection, operation_type="manual_ready", operation_key=operation_key,
            request_sha256=request_sha256, result_ref=work_item_id,
        )
        connection.commit()
        return work_item_id
    except Exception:
        connection.rollback()
        raise


def record_publication(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    revision_id: str,
    approval_id: str,
    platform: str,
    owned_account_id: str,
    external_post_id: str,
    canonical_url: str,
    actor_id: str,
    operation_key: str,
) -> str:
    request = {
        "publication_id": publication_id, "revision_id": revision_id, "approval_id": approval_id,
        "platform": platform, "owned_account_id": owned_account_id,
        "external_post_id": external_post_id, "canonical_url": canonical_url,
    }
    request_sha256 = _request_hash(request)
    begin_write(connection)
    try:
        existing = _existing_operation(connection, "record_publication", operation_key, request_sha256)
        if existing is not None:
            connection.commit()
            return existing
        row = connection.execute(
            """SELECT r.work_item_id, r.platform, r.owned_account_id, r.binding_sha256,
                      a.binding_sha256, a.decision
               FROM revisions r JOIN approvals a ON a.revision_id=r.id
               WHERE r.id=? AND a.id=?""",
            (revision_id, approval_id),
        ).fetchone()
        if row is None:
            raise ValueError("publication requires linked revision and approval")
        if row[1] != platform or row[2] != owned_account_id or row[3] != row[4] or row[5] != "approved":
            raise ValueError("publication identity or approval binding mismatch")
        state = connection.execute("SELECT state FROM work_items WHERE id=?", (row[0],)).fetchone()
        if state is None or state[0] != "manual_ready":
            raise ValueError("publication requires manual_ready state")
        connection.execute(
            """INSERT INTO publications
            (id, revision_id, approval_id, platform, owned_account_id, external_post_id, canonical_url,
             verification_state, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'owner_confirmed', ?)""",
            (publication_id, revision_id, approval_id, platform, owned_account_id, external_post_id, canonical_url, utc_now()),
        )
        connection.execute("UPDATE approvals SET decision='consumed' WHERE id=?", (approval_id,))
        connection.execute("UPDATE work_items SET state='published', updated_at=? WHERE id=?", (utc_now(), row[0]))
        append_audit(
            connection, actor_type="human", actor_id=actor_id, operation="record_publication",
            record_type="publication", record_id=publication_id,
            payload={"revision_id": revision_id, "approval_id": approval_id, "external_post_id": external_post_id},
        )
        _record_operation(
            connection, operation_type="record_publication", operation_key=operation_key,
            request_sha256=request_sha256, result_ref=publication_id,
        )
        connection.commit()
        return publication_id
    except Exception:
        connection.rollback()
        raise


def record_metric_snapshot(
    connection: sqlite3.Connection,
    *,
    snapshot_id: str,
    publication_id: str,
    observation_method: str,
    capture_session_id: str,
    metric_set_version: int,
    metrics: object,
    observation_state: str,
    corrects_snapshot_id: str | None = None,
) -> str:
    request = {
        "snapshot_id": snapshot_id, "publication_id": publication_id,
        "observation_method": observation_method, "capture_session_id": capture_session_id,
        "metric_set_version": metric_set_version, "metrics": metrics,
        "observation_state": observation_state, "corrects_snapshot_id": corrects_snapshot_id,
    }
    request_sha256 = _request_hash(request)
    operation_key = f"{publication_id}:{observation_method}:{capture_session_id}"
    begin_write(connection)
    try:
        existing = _existing_operation(connection, "metric_snapshot", operation_key, request_sha256)
        if existing is not None:
            connection.commit()
            return existing
        if corrects_snapshot_id is not None:
            prior = connection.execute(
                "SELECT publication_id FROM metric_snapshots WHERE id=?", (corrects_snapshot_id,)
            ).fetchone()
            if prior is None or prior[0] != publication_id:
                raise ValueError("metric correction must reference a snapshot for the same publication")
        connection.execute(
            """INSERT INTO metric_snapshots
            (id, publication_id, observation_method, capture_session_id, captured_at, metric_set_version,
             metrics_json, observation_state, corrects_snapshot_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (snapshot_id, publication_id, observation_method, capture_session_id, utc_now(), metric_set_version,
             _json_bytes(metrics), observation_state, corrects_snapshot_id),
        )
        append_audit(
            connection, actor_type="human" if observation_method == "manual" else "system",
            actor_id="metric-recorder", operation="record_metric_snapshot",
            record_type="metric_snapshot", record_id=snapshot_id,
            payload={"publication_id": publication_id, "observation_method": observation_method,
                     "capture_session_id": capture_session_id, "observation_state": observation_state},
        )
        _record_operation(
            connection, operation_type="metric_snapshot", operation_key=operation_key,
            request_sha256=request_sha256, result_ref=snapshot_id,
        )
        connection.commit()
        return snapshot_id
    except Exception:
        connection.rollback()
        raise


OBSERVATION_STATES = frozenset({
    "observed_value", "observed_empty", "not_requested", "not_returned",
    "unavailable", "withheld", "malformed", "errored", "unsupported",
})


def query_metric_snapshots_by_state(
    connection: sqlite3.Connection, *, publication_id: str, states: set[str]
) -> list[sqlite3.Row]:
    if not states:
        raise ValueError("at least one explicit observation state is required")
    unknown = states - OBSERVATION_STATES
    if unknown:
        raise ValueError(f"unsupported observation states: {sorted(unknown)}")
    placeholders = ",".join("?" for _ in sorted(states))
    return list(
        connection.execute(
            f"""SELECT * FROM metric_snapshots
            WHERE publication_id=? AND observation_state IN ({placeholders})
            ORDER BY captured_at, id""",
            (publication_id, *sorted(states)),
        )
    )


def record_publication_mismatch(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    revision_id: str,
    approval_id: str,
    platform: str,
    owned_account_id: str,
    external_post_id: str,
    canonical_url: str,
    mismatch_reason: str,
    actor_id: str,
    operation_key: str,
) -> str:
    if not mismatch_reason.strip():
        raise ValueError("publication mismatch reason is required")
    request = {
        "publication_id": publication_id, "revision_id": revision_id,
        "approval_id": approval_id, "platform": platform,
        "owned_account_id": owned_account_id, "external_post_id": external_post_id,
        "canonical_url": canonical_url, "mismatch_reason": mismatch_reason,
    }
    request_sha256 = _request_hash(request)
    begin_write(connection)
    try:
        existing = _existing_operation(
            connection, "record_publication_mismatch", operation_key, request_sha256
        )
        if existing is not None:
            connection.commit()
            return existing
        row = connection.execute(
            """SELECT r.work_item_id, r.platform, r.owned_account_id, r.binding_sha256,
                      a.binding_sha256, a.decision
               FROM revisions r JOIN approvals a ON a.revision_id=r.id
               WHERE r.id=? AND a.id=?""",
            (revision_id, approval_id),
        ).fetchone()
        if row is None:
            raise ValueError("publication mismatch requires linked revision and approval")
        if row[1] != platform or row[2] != owned_account_id or row[3] != row[4] or row[5] != "approved":
            raise ValueError("publication mismatch identity or approval binding mismatch")
        state = connection.execute(
            "SELECT state FROM work_items WHERE id=?", (row[0],)
        ).fetchone()
        if state is None or state[0] != "manual_ready":
            raise ValueError("publication mismatch requires manual_ready state")
        connection.execute(
            """INSERT INTO publications
            (id, revision_id, approval_id, platform, owned_account_id, external_post_id,
             canonical_url, verification_state, observed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'verified_mismatch', ?)""",
            (publication_id, revision_id, approval_id, platform, owned_account_id,
             external_post_id, canonical_url, utc_now()),
        )
        connection.execute("UPDATE approvals SET decision='consumed' WHERE id=?", (approval_id,))
        connection.execute(
            "UPDATE work_items SET state='publication_mismatch', updated_at=? WHERE id=?",
            (utc_now(), row[0]),
        )
        append_audit(
            connection, actor_type="human", actor_id=actor_id,
            operation="record_publication_mismatch", record_type="publication",
            record_id=publication_id, payload={
                "revision_id": revision_id, "approval_id": approval_id,
                "external_post_id": external_post_id, "mismatch_reason": mismatch_reason,
            },
        )
        _record_operation(
            connection, operation_type="record_publication_mismatch",
            operation_key=operation_key, request_sha256=request_sha256,
            result_ref=publication_id,
        )
        connection.commit()
        return publication_id
    except Exception:
        connection.rollback()
        raise


def detector_advice(
    *, work_item_id: str, detector_name: str, outcome: str, detail: str | None = None
) -> dict[str, str | None]:
    if outcome not in {"flagged", "not_detected", "errored"}:
        raise ValueError("unsupported detector outcome")
    return {
        "work_item_id": work_item_id,
        "detector_name": detector_name,
        "outcome": outcome,
        "detail": detail,
        "authority": "advisory_only",
    }
