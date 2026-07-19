from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .binding import RevisionBundle
from .db import begin_write
from .persistence import (
    existing_operation,
    record_operation,
    request_hash,
    append_audit,
    approve_revision,
    create_revision,
    mark_manual_ready,
    query_metric_snapshots_by_state,
    record_metric_snapshot,
    record_publication,
    register_evidence,
    transition_work_item,
    utc_now,
)


@dataclass(frozen=True)
class OperatorLoopResult:
    work_item_id: str
    revision_id: str
    approval_id: str
    publication_id: str
    metric_snapshot_id: str | None


def create_owned_account(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    platform: str,
    external_account_id: str,
    username: str | None,
    operation_key: str,
    actor_id: str,
) -> str:
    request = {
        "account_id": account_id,
        "platform": platform,
        "external_account_id": external_account_id,
        "username": username,
    }
    request_sha256 = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(
            connection, "create_owned_account", operation_key, request_sha256
        )
        if existing is not None:
            connection.commit()
            return existing
        connection.execute(
            "INSERT INTO owned_accounts VALUES (?, ?, ?, ?, 1)",
            (account_id, platform, external_account_id, username),
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="create_owned_account",
            record_type="owned_account",
            record_id=account_id,
            payload={
                "platform": platform,
                "external_account_id": external_account_id,
                "username": username,
            },
        )
        record_operation(
            connection,
            operation_type="create_owned_account",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=account_id,
        )
        connection.commit()
        return account_id
    except Exception:
        connection.rollback()
        raise


def capture_work_item(
    connection: sqlite3.Connection,
    *,
    work_item_id: str,
    title: str,
    operation_key: str,
    actor_id: str,
) -> str:
    if not title.strip():
        raise ValueError("work item title is required")
    request = {"work_item_id": work_item_id, "title": title}
    request_sha256 = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "capture_work_item", operation_key, request_sha256)
        if existing is not None:
            connection.commit()
            return existing
        now = utc_now()
        connection.execute(
            "INSERT INTO work_items VALUES (?, 'captured', ?, ?, ?)",
            (work_item_id, title, now, now),
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="capture_work_item",
            record_type="work_item",
            record_id=work_item_id,
            payload={"title": title},
        )
        record_operation(
            connection,
            operation_type="capture_work_item",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=work_item_id,
        )
        connection.commit()
        return work_item_id
    except Exception:
        connection.rollback()
        raise


def add_source_record(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    work_item_id: str,
    source_kind: str,
    locator: str | None,
    note_text: str | None,
    operation_key: str,
    actor_id: str,
) -> str:
    if locator is None and note_text is None:
        raise ValueError("source locator or note is required")
    request = {
        "source_id": source_id,
        "work_item_id": work_item_id,
        "source_kind": source_kind,
        "locator": locator,
        "note_text": note_text,
    }
    request_sha256 = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "add_source_record", operation_key, request_sha256)
        if existing is not None:
            connection.commit()
            return existing
        connection.execute(
            """INSERT INTO source_records
            (id, work_item_id, source_kind, locator, note_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                work_item_id,
                source_kind,
                locator,
                note_text.encode("utf-8") if note_text is not None else None,
                utc_now(),
            ),
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="add_source_record",
            record_type="source_record",
            record_id=source_id,
            payload={
                "work_item_id": work_item_id,
                "source_kind": source_kind,
                "locator": locator,
                "note_sha256": (
                    hashlib.sha256(note_text.encode("utf-8")).hexdigest()
                    if note_text is not None
                    else None
                ),
            },
        )
        record_operation(
            connection,
            operation_type="add_source_record",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=source_id,
        )
        connection.commit()
        return source_id
    except Exception:
        connection.rollback()
        raise


def reject_review(
    connection: sqlite3.Connection,
    *,
    work_item_id: str,
    reason: str,
    actor_id: str,
    operation_key: str,
) -> str:
    if not reason.strip():
        raise ValueError("rejection reason is required")
    request = {"work_item_id": work_item_id, "reason": reason, "actor_id": actor_id}
    request_sha256 = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "reject_review", operation_key, request_sha256)
        if existing is not None:
            connection.commit()
            return existing
        cursor = connection.execute(
            "UPDATE work_items SET state='rejected', updated_at=? WHERE id=? AND state='human_review_needed'",
            (utc_now(), work_item_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("rejection requires human_review_needed state")
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="reject_review",
            record_type="work_item",
            record_id=work_item_id,
            payload={"reason": reason},
        )
        record_operation(
            connection,
            operation_type="reject_review",
            operation_key=operation_key,
            request_sha256=request_sha256,
            result_ref=work_item_id,
        )
        connection.commit()
        return work_item_id
    except Exception:
        connection.rollback()
        raise


def get_control_room_item(connection: sqlite3.Connection, work_item_id: str) -> dict[str, object]:
    work = connection.execute("SELECT * FROM work_items WHERE id=?", (work_item_id,)).fetchone()
    if work is None:
        raise ValueError("unknown work item")
    sources = connection.execute(
        "SELECT id, source_kind, locator, note_text, created_at FROM source_records WHERE work_item_id=? ORDER BY created_at, id",
        (work_item_id,),
    ).fetchall()
    evidence = connection.execute(
        "SELECT id, relative_path, sha256, byte_size, verification_state FROM evidence_refs WHERE work_item_id=? ORDER BY id",
        (work_item_id,),
    ).fetchall()
    revisions = connection.execute(
        "SELECT id, platform, owned_account_id, binding_sha256, created_at FROM revisions WHERE work_item_id=? ORDER BY created_at, id",
        (work_item_id,),
    ).fetchall()
    publication = connection.execute(
        """SELECT p.* FROM publications p
        JOIN revisions r ON r.id=p.revision_id
        WHERE r.work_item_id=? ORDER BY p.observed_at DESC LIMIT 1""",
        (work_item_id,),
    ).fetchone()
    metrics: list[dict[str, object]] = []
    if publication is not None:
        rows = query_metric_snapshots_by_state(
            connection,
            publication_id=str(publication["id"]),
            states={
                "observed_value",
                "observed_empty",
                "not_requested",
                "not_returned",
                "unavailable",
                "withheld",
                "malformed",
                "errored",
                "unsupported",
            },
        )
        metrics = [
            {
                "id": row["id"],
                "observation_method": row["observation_method"],
                "capture_session_id": row["capture_session_id"],
                "captured_at": row["captured_at"],
                "observation_state": row["observation_state"],
                "metrics": json.loads(bytes(row["metrics_json"]).decode("utf-8")),
            }
            for row in rows
        ]
    return {
        "work_item": dict(work),
        "sources": [
            {
                "id": row["id"],
                "source_kind": row["source_kind"],
                "locator": row["locator"],
                "note_text": (
                    bytes(row["note_text"]).decode("utf-8") if row["note_text"] is not None else None
                ),
                "created_at": row["created_at"],
            }
            for row in sources
        ],
        "evidence": [dict(row) for row in evidence],
        "revisions": [dict(row) for row in revisions],
        "publication": dict(publication) if publication is not None else None,
        "metrics": metrics,
    }


def run_matched_operator_loop(
    connection: sqlite3.Connection,
    evidence_root: Path,
    *,
    account_id: str,
    external_account_id: str,
    username: str,
    work_item_id: str,
    title: str,
    source_id: str,
    source_locator: str,
    evidence_id: str,
    evidence_relative_path: str,
    evidence_sha256: str,
    revision_id: str,
    authored_text: str,
    approval_id: str,
    publication_id: str,
    external_post_id: str,
    canonical_url: str,
    metric_snapshot_id: str | None,
    metric_capture_session_id: str | None,
    metrics: dict[str, int] | None,
    actor_id: str,
    operation_prefix: str,
) -> OperatorLoopResult:
    create_owned_account(
        connection,
        account_id=account_id,
        platform="x",
        external_account_id=external_account_id,
        username=username,
        operation_key=f"{operation_prefix}:account",
        actor_id=actor_id,
    )
    capture_work_item(
        connection,
        work_item_id=work_item_id,
        title=title,
        operation_key=f"{operation_prefix}:capture",
        actor_id=actor_id,
    )
    add_source_record(
        connection,
        source_id=source_id,
        work_item_id=work_item_id,
        source_kind="url",
        locator=source_locator,
        note_text=None,
        operation_key=f"{operation_prefix}:source",
        actor_id=actor_id,
    )
    register_evidence(
        connection,
        evidence_root,
        evidence_id=evidence_id,
        work_item_id=work_item_id,
        relative_path=evidence_relative_path,
        expected_sha256=evidence_sha256,
    )
    transition_work_item(connection, work_item_id, "drafting", actor_id=actor_id)
    binding = create_revision(
        connection,
        revision_id=revision_id,
        work_item_id=work_item_id,
        owned_account_id=account_id,
        bundle=RevisionBundle("x", account_id, authored_text),
    )
    transition_work_item(connection, work_item_id, "human_review_needed", actor_id=actor_id)
    approve_revision(
        connection,
        approval_id=approval_id,
        revision_id=revision_id,
        binding_sha256=binding,
        actor_id=actor_id,
        action_id=f"{operation_prefix}:approval-action",
    )
    mark_manual_ready(
        connection,
        work_item_id=work_item_id,
        approval_id=approval_id,
        actor_id=actor_id,
        operation_key=f"{operation_prefix}:manual-ready",
    )
    record_publication(
        connection,
        publication_id=publication_id,
        revision_id=revision_id,
        approval_id=approval_id,
        platform="x",
        owned_account_id=account_id,
        external_post_id=external_post_id,
        canonical_url=canonical_url,
        actor_id=actor_id,
        operation_key=f"{operation_prefix}:publication",
    )
    if metric_snapshot_id is not None:
        if metric_capture_session_id is None or metrics is None:
            raise ValueError("metric snapshot requires capture session and metrics")
        record_metric_snapshot(
            connection,
            snapshot_id=metric_snapshot_id,
            publication_id=publication_id,
            observation_method="manual",
            capture_session_id=metric_capture_session_id,
            metric_set_version=1,
            metrics=metrics,
            observation_state="observed_value",
        )
    return OperatorLoopResult(
        work_item_id=work_item_id,
        revision_id=revision_id,
        approval_id=approval_id,
        publication_id=publication_id,
        metric_snapshot_id=metric_snapshot_id,
    )
