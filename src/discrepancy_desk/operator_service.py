from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
    record_publication_mismatch,
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
        stable_identity = connection.execute(
            """SELECT id, username FROM owned_accounts
            WHERE platform=? AND external_account_id=?""",
            (platform, external_account_id),
        ).fetchone()
        if stable_identity is not None:
            existing_account_id = str(stable_identity["id"])
            existing_username = stable_identity["username"]
            resolved_username = username if username is not None else existing_username
            if resolved_username != existing_username:
                connection.execute(
                    "UPDATE owned_accounts SET username=? WHERE id=?",
                    (resolved_username, existing_account_id),
                )
                append_audit(
                    connection,
                    actor_type="human",
                    actor_id=actor_id,
                    operation="update_owned_account_metadata",
                    record_type="owned_account",
                    record_id=existing_account_id,
                    payload={
                        "platform": platform,
                        "external_account_id": external_account_id,
                        "previous_username": existing_username,
                        "username": resolved_username,
                    },
                )
            record_operation(
                connection,
                operation_type="create_owned_account",
                operation_key=operation_key,
                request_sha256=request_sha256,
                result_ref=existing_account_id,
            )
            connection.commit()
            return existing_account_id
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
        "SELECT id, platform, owned_account_id, binding_sha256, created_at, supersedes_revision_id FROM revisions WHERE work_item_id=? ORDER BY created_at, id",
        (work_item_id,),
    ).fetchall()
    publications = connection.execute(
        """SELECT p.* FROM publications p
        JOIN revisions r ON r.id=p.revision_id
        WHERE r.work_item_id=? ORDER BY p.observed_at, p.id""",
        (work_item_id,),
    ).fetchall()
    publication = publications[-1] if publications else None
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
        "publications": [dict(row) for row in publications],
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


M04_LANES = {"archive", "docket", "flash_release"}


def _parse_utc(value: str | None, *, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized = sorted({tag.strip().lower() for tag in tags if tag.strip()})
    if len(normalized) != len([tag for tag in tags if tag.strip()]):
        # duplicates are accepted only through normalization into one durable value
        pass
    if any(len(tag) > 64 for tag in normalized):
        raise ValueError("tag exceeds 64 characters")
    return normalized


def _require_profile_account(
    connection: sqlite3.Connection, work_item_id: str, account_id: str
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM editorial_profiles WHERE work_item_id=?", (work_item_id,)
    ).fetchone()
    if row is None:
        raise ValueError("work item must be organized before scheduling")
    if str(row["account_id"]) != account_id:
        raise ValueError("account scope mismatch")
    return row


def organize_work_item(
    connection: sqlite3.Connection,
    *,
    work_item_id: str,
    account_id: str,
    lane: str,
    topic: str | None,
    priority: int,
    operator_notes: str | None,
    is_dormant: bool,
    actor_id: str,
    operation_key: str,
) -> str:
    if lane not in M04_LANES:
        raise ValueError("invalid editorial lane")
    if priority not in range(1, 6):
        raise ValueError("priority must be between 1 and 5")
    normalized_topic = topic.strip() if topic else None
    if normalized_topic is not None and len(normalized_topic) > 200:
        raise ValueError("topic exceeds 200 characters")
    request = {
        "work_item_id": work_item_id,
        "account_id": account_id,
        "lane": lane,
        "topic": normalized_topic,
        "priority": priority,
        "operator_notes": operator_notes,
        "is_dormant": is_dormant,
    }
    digest = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "organize_work_item", operation_key, digest)
        if existing is not None:
            connection.commit()
            return existing
        if connection.execute("SELECT 1 FROM work_items WHERE id=?", (work_item_id,)).fetchone() is None:
            raise ValueError("unknown work item")
        if connection.execute("SELECT 1 FROM owned_accounts WHERE id=?", (account_id,)).fetchone() is None:
            raise ValueError("unknown account")
        current = connection.execute(
            "SELECT account_id FROM editorial_profiles WHERE work_item_id=?", (work_item_id,)
        ).fetchone()
        if current is not None and str(current[0]) != account_id:
            raise ValueError("organized account cannot be changed")
        if is_dormant and connection.execute(
            "SELECT 1 FROM schedule_slots WHERE work_item_id=? AND status='active'", (work_item_id,)
        ).fetchone() is not None:
            raise ValueError("unschedule work before marking it dormant")
        now = utc_now()
        connection.execute(
            """INSERT INTO editorial_profiles
            (work_item_id,account_id,lane,topic,priority,operator_notes,is_dormant,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(work_item_id) DO UPDATE SET lane=excluded.lane, topic=excluded.topic,
            priority=excluded.priority, operator_notes=excluded.operator_notes,
            is_dormant=excluded.is_dormant, updated_at=excluded.updated_at""",
            (
                work_item_id,
                account_id,
                lane,
                normalized_topic,
                priority,
                operator_notes.encode("utf-8") if operator_notes is not None else None,
                int(is_dormant),
                now,
                now,
            ),
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="organize_work_item",
            record_type="editorial_profile",
            record_id=work_item_id,
            payload=request,
        )
        record_operation(
            connection,
            operation_type="organize_work_item",
            operation_key=operation_key,
            request_sha256=digest,
            result_ref=work_item_id,
        )
        connection.commit()
        return work_item_id
    except Exception:
        connection.rollback()
        raise


def set_work_item_tags(
    connection: sqlite3.Connection,
    *,
    work_item_id: str,
    account_id: str,
    tags: list[str],
    actor_id: str,
    operation_key: str,
) -> str:
    normalized = _normalize_tags(tags)
    request = {"work_item_id": work_item_id, "account_id": account_id, "tags": normalized}
    digest = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "set_work_item_tags", operation_key, digest)
        if existing is not None:
            connection.commit()
            return existing
        _require_profile_account(connection, work_item_id, account_id)
        connection.execute("DELETE FROM work_item_tags WHERE work_item_id=?", (work_item_id,))
        connection.executemany(
            "INSERT INTO work_item_tags(work_item_id,tag) VALUES (?,?)",
            [(work_item_id, tag) for tag in normalized],
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="set_work_item_tags",
            record_type="work_item",
            record_id=work_item_id,
            payload={"account_id": account_id, "tags": normalized},
        )
        record_operation(
            connection,
            operation_type="set_work_item_tags",
            operation_key=operation_key,
            request_sha256=digest,
            result_ref=work_item_id,
        )
        connection.commit()
        return work_item_id
    except Exception:
        connection.rollback()
        raise


def _validate_schedule_dates(
    *,
    scheduled_for: str | None,
    preferred_window_start: str | None,
    preferred_window_end: str | None,
    earliest_useful_at: str | None,
    stale_after: str | None,
    hard_deadline_at: str | None,
    now: datetime,
) -> None:
    scheduled = _parse_utc(scheduled_for, field="scheduled_for")
    window_start = _parse_utc(preferred_window_start, field="preferred_window_start")
    window_end = _parse_utc(preferred_window_end, field="preferred_window_end")
    earliest = _parse_utc(earliest_useful_at, field="earliest_useful_at")
    stale = _parse_utc(stale_after, field="stale_after")
    deadline = _parse_utc(hard_deadline_at, field="hard_deadline_at")
    if scheduled is not None and scheduled > now + timedelta(days=90):
        raise ValueError("scheduled time exceeds rolling 90-day horizon")
    if window_start and window_end and window_end < window_start:
        raise ValueError("preferred window end precedes start")
    if earliest and stale and stale < earliest:
        raise ValueError("stale-after precedes earliest useful time")
    if earliest and deadline and deadline < earliest:
        raise ValueError("hard deadline precedes earliest useful time")


def schedule_work_item(
    connection: sqlite3.Connection,
    *,
    schedule_id: str,
    work_item_id: str,
    account_id: str,
    scheduled_for: str | None,
    preferred_window_start: str | None,
    preferred_window_end: str | None,
    earliest_useful_at: str | None,
    stale_after: str | None,
    hard_deadline_at: str | None,
    is_evergreen: bool,
    actor_id: str,
    operation_key: str,
    now: datetime | None = None,
) -> str:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _validate_schedule_dates(
        scheduled_for=scheduled_for,
        preferred_window_start=preferred_window_start,
        preferred_window_end=preferred_window_end,
        earliest_useful_at=earliest_useful_at,
        stale_after=stale_after,
        hard_deadline_at=hard_deadline_at,
        now=current_time,
    )
    request = {
        "schedule_id": schedule_id,
        "work_item_id": work_item_id,
        "account_id": account_id,
        "scheduled_for": scheduled_for,
        "preferred_window_start": preferred_window_start,
        "preferred_window_end": preferred_window_end,
        "earliest_useful_at": earliest_useful_at,
        "stale_after": stale_after,
        "hard_deadline_at": hard_deadline_at,
        "is_evergreen": is_evergreen,
    }
    digest = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "schedule_work_item", operation_key, digest)
        if existing is not None:
            connection.commit()
            return existing
        profile = _require_profile_account(connection, work_item_id, account_id)
        if int(profile["is_dormant"]):
            raise ValueError("dormant work cannot be actively scheduled")
        if connection.execute(
            "SELECT 1 FROM schedule_slots WHERE work_item_id=? AND status='active'", (work_item_id,)
        ).fetchone() is not None:
            raise ValueError("work item already has an active schedule")
        approval = connection.execute(
            """SELECT r.id FROM revisions r JOIN approvals a ON a.revision_id=r.id
            WHERE r.work_item_id=? AND r.owned_account_id=? AND a.decision='approved'
            ORDER BY a.decided_at DESC LIMIT 1""",
            (work_item_id, account_id),
        ).fetchone()
        approved_revision_id = str(approval[0]) if approval else None
        connection.execute(
            """INSERT INTO schedule_slots
            (id,work_item_id,account_id,approved_revision_id,scheduled_for,preferred_window_start,
             preferred_window_end,earliest_useful_at,stale_after,hard_deadline_at,is_evergreen,
             status,supersedes_schedule_id,created_at,created_by,operation_key)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',NULL,?,?,?)""",
            (
                schedule_id, work_item_id, account_id, approved_revision_id, scheduled_for,
                preferred_window_start, preferred_window_end, earliest_useful_at, stale_after,
                hard_deadline_at, int(is_evergreen), current_time.isoformat(), actor_id, operation_key,
            ),
        )
        append_audit(
            connection, actor_type="human", actor_id=actor_id, operation="schedule_work_item",
            record_type="schedule_slot", record_id=schedule_id,
            payload={**request, "approved_revision_id": approved_revision_id},
        )
        record_operation(
            connection, operation_type="schedule_work_item", operation_key=operation_key,
            request_sha256=digest, result_ref=schedule_id,
        )
        connection.commit()
        return schedule_id
    except Exception:
        connection.rollback()
        raise


def _replace_schedule(
    connection: sqlite3.Connection,
    *,
    operation_type: str,
    schedule_id: str,
    prior_schedule_id: str,
    account_id: str,
    actor_id: str,
    operation_key: str,
    fields: dict[str, object],
) -> str:
    request = {"schedule_id": schedule_id, "prior_schedule_id": prior_schedule_id,
               "account_id": account_id, **fields}
    digest = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, operation_type, operation_key, digest)
        if existing is not None:
            connection.commit()
            return existing
        prior = connection.execute(
            "SELECT * FROM schedule_slots WHERE id=? AND status='active'", (prior_schedule_id,)
        ).fetchone()
        if prior is None:
            raise ValueError("active prior schedule not found")
        if str(prior["account_id"]) != account_id:
            raise ValueError("account scope mismatch")
        connection.execute("UPDATE schedule_slots SET status='superseded' WHERE id=?", (prior_schedule_id,))
        values = {
            "work_item_id": prior["work_item_id"],
            "approved_revision_id": prior["approved_revision_id"],
            "scheduled_for": prior["scheduled_for"],
            "preferred_window_start": prior["preferred_window_start"],
            "preferred_window_end": prior["preferred_window_end"],
            "earliest_useful_at": prior["earliest_useful_at"],
            "stale_after": prior["stale_after"],
            "hard_deadline_at": prior["hard_deadline_at"],
            "is_evergreen": prior["is_evergreen"],
        }
        values.update(fields)
        status = "unscheduled" if operation_type == "unschedule_work_item" else "active"
        connection.execute(
            """INSERT INTO schedule_slots
            (id,work_item_id,account_id,approved_revision_id,scheduled_for,preferred_window_start,
             preferred_window_end,earliest_useful_at,stale_after,hard_deadline_at,is_evergreen,
             status,supersedes_schedule_id,created_at,created_by,operation_key)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                schedule_id, values["work_item_id"], account_id, values["approved_revision_id"],
                values["scheduled_for"], values["preferred_window_start"], values["preferred_window_end"],
                values["earliest_useful_at"], values["stale_after"], values["hard_deadline_at"],
                values["is_evergreen"], status, prior_schedule_id, utc_now(), actor_id, operation_key,
            ),
        )
        append_audit(
            connection, actor_type="human", actor_id=actor_id, operation=operation_type,
            record_type="schedule_slot", record_id=schedule_id, payload=request,
        )
        record_operation(
            connection, operation_type=operation_type, operation_key=operation_key,
            request_sha256=digest, result_ref=schedule_id,
        )
        connection.commit()
        return schedule_id
    except Exception:
        connection.rollback()
        raise


def reschedule_work_item(
    connection: sqlite3.Connection,
    *, schedule_id: str, prior_schedule_id: str, account_id: str,
    scheduled_for: str | None, preferred_window_start: str | None,
    preferred_window_end: str | None, earliest_useful_at: str | None,
    stale_after: str | None, hard_deadline_at: str | None, is_evergreen: bool,
    actor_id: str, operation_key: str, now: datetime | None = None,
) -> str:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _validate_schedule_dates(
        scheduled_for=scheduled_for, preferred_window_start=preferred_window_start,
        preferred_window_end=preferred_window_end, earliest_useful_at=earliest_useful_at,
        stale_after=stale_after, hard_deadline_at=hard_deadline_at, now=current_time,
    )
    return _replace_schedule(
        connection, operation_type="reschedule_work_item", schedule_id=schedule_id,
        prior_schedule_id=prior_schedule_id, account_id=account_id, actor_id=actor_id,
        operation_key=operation_key, fields={
            "scheduled_for": scheduled_for, "preferred_window_start": preferred_window_start,
            "preferred_window_end": preferred_window_end, "earliest_useful_at": earliest_useful_at,
            "stale_after": stale_after, "hard_deadline_at": hard_deadline_at,
            "is_evergreen": int(is_evergreen),
        },
    )


def unschedule_work_item(
    connection: sqlite3.Connection,
    *, schedule_id: str, prior_schedule_id: str, account_id: str,
    actor_id: str, operation_key: str,
) -> str:
    return _replace_schedule(
        connection, operation_type="unschedule_work_item", schedule_id=schedule_id,
        prior_schedule_id=prior_schedule_id, account_id=account_id, actor_id=actor_id,
        operation_key=operation_key, fields={"scheduled_for": None},
    )


def set_editorial_target(
    connection: sqlite3.Connection,
    *, target_id: str, account_id: str, target_kind: str, window_days: int,
    target_value: int, effective_from: str, effective_until: str | None,
    source_note: str, actor_id: str, operation_key: str,
) -> str:
    if not target_kind.strip() or not source_note.strip():
        raise ValueError("target kind and source note are required")
    if not 1 <= window_days <= 366 or target_value < 0:
        raise ValueError("invalid editorial target")
    start = _parse_utc(effective_from, field="effective_from")
    end = _parse_utc(effective_until, field="effective_until")
    if end is not None and start is not None and end < start:
        raise ValueError("effective-until precedes effective-from")
    request = {"target_id": target_id, "account_id": account_id, "target_kind": target_kind,
               "window_days": window_days, "target_value": target_value,
               "effective_from": effective_from, "effective_until": effective_until,
               "source_note": source_note}
    digest = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(connection, "set_editorial_target", operation_key, digest)
        if existing is not None:
            connection.commit()
            return existing
        if connection.execute("SELECT 1 FROM owned_accounts WHERE id=?", (account_id,)).fetchone() is None:
            raise ValueError("unknown account")
        connection.execute(
            "INSERT INTO editorial_targets VALUES (?,?,?,?,?,?,?,?,?,?)",
            (target_id, account_id, target_kind.strip(), window_days, target_value,
             effective_from, effective_until, source_note.strip(), utc_now(), actor_id),
        )
        append_audit(connection, actor_type="human", actor_id=actor_id,
                     operation="set_editorial_target", record_type="editorial_target",
                     record_id=target_id, payload=request)
        record_operation(connection, operation_type="set_editorial_target",
                         operation_key=operation_key, request_sha256=digest, result_ref=target_id)
        connection.commit()
        return target_id
    except Exception:
        connection.rollback()
        raise


def record_manual_metric_observation(
    connection: sqlite3.Connection,
    *,
    snapshot_id: str,
    publication_id: str,
    account_id: str,
    capture_session_id: str,
    metric_set_version: int,
    metrics: object,
    observation_state: str,
    actor_id: str,
    operation_key: str,
    corrects_snapshot_id: str | None = None,
) -> str:
    publication = connection.execute(
        "SELECT owned_account_id FROM publications WHERE id=?", (publication_id,)
    ).fetchone()
    if publication is None:
        raise ValueError("unknown publication")
    if publication[0] != account_id:
        raise ValueError("publication account mismatch")
    return record_metric_snapshot(
        connection,
        snapshot_id=snapshot_id,
        publication_id=publication_id,
        observation_method="manual",
        capture_session_id=capture_session_id,
        metric_set_version=metric_set_version,
        metrics=metrics,
        observation_state=observation_state,
        corrects_snapshot_id=corrects_snapshot_id,
        actor_id=actor_id,
        operation_key=operation_key,
    )


def record_manual_publication_result(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    revision_id: str,
    approval_id: str,
    platform: str,
    account_id: str,
    external_post_id: str,
    canonical_url: str,
    matched: bool,
    mismatch_reason: str | None,
    actor_id: str,
    operation_key: str,
) -> str:
    if matched:
        if mismatch_reason is not None and mismatch_reason.strip():
            raise ValueError("matched publication cannot include mismatch reason")
        return record_publication(
            connection,
            publication_id=publication_id,
            revision_id=revision_id,
            approval_id=approval_id,
            platform=platform,
            owned_account_id=account_id,
            external_post_id=external_post_id,
            canonical_url=canonical_url,
            actor_id=actor_id,
            operation_key=operation_key,
        )
    if mismatch_reason is None or not mismatch_reason.strip():
        raise ValueError("mismatched publication requires reason")
    return record_publication_mismatch(
        connection,
        publication_id=publication_id,
        revision_id=revision_id,
        approval_id=approval_id,
        platform=platform,
        owned_account_id=account_id,
        external_post_id=external_post_id,
        canonical_url=canonical_url,
        mismatch_reason=mismatch_reason,
        actor_id=actor_id,
        operation_key=operation_key,
    )


def reconcile_publication_result(
    connection: sqlite3.Connection,
    *,
    publication_id: str,
    account_id: str,
    matched: bool,
    mismatch_reason: str | None,
    actor_id: str,
    operation_key: str,
) -> str:
    request = {
        "publication_id": publication_id,
        "account_id": account_id,
        "matched": matched,
        "mismatch_reason": mismatch_reason,
    }
    digest = request_hash(request)
    begin_write(connection)
    try:
        existing = existing_operation(
            connection, "reconcile_publication_result", operation_key, digest
        )
        if existing is not None:
            connection.commit()
            return existing
        row = connection.execute(
            """SELECT p.owned_account_id, p.verification_state, r.work_item_id
            FROM publications p JOIN revisions r ON r.id=p.revision_id
            WHERE p.id=?""",
            (publication_id,),
        ).fetchone()
        if row is None:
            raise ValueError("unknown publication")
        if row[0] != account_id:
            raise ValueError("publication account mismatch")
        if row[1] not in {"owner_confirmed", "platform_observed"}:
            raise ValueError("publication already reconciled")
        if matched:
            if mismatch_reason is not None and mismatch_reason.strip():
                raise ValueError("matched publication cannot include mismatch reason")
            verification_state = "verified_match"
            work_state = "published"
        else:
            if mismatch_reason is None or not mismatch_reason.strip():
                raise ValueError("mismatched publication requires reason")
            verification_state = "verified_mismatch"
            work_state = "publication_mismatch"
        connection.execute(
            "UPDATE publications SET verification_state=? WHERE id=?",
            (verification_state, publication_id),
        )
        connection.execute(
            "UPDATE work_items SET state=?, updated_at=? WHERE id=?",
            (work_state, utc_now(), row[2]),
        )
        append_audit(
            connection,
            actor_type="human",
            actor_id=actor_id,
            operation="reconcile_publication_result",
            record_type="publication",
            record_id=publication_id,
            payload={
                "verification_state": verification_state,
                "mismatch_reason": mismatch_reason,
            },
        )
        record_operation(
            connection,
            operation_type="reconcile_publication_result",
            operation_key=operation_key,
            request_sha256=digest,
            result_ref=publication_id,
        )
        connection.commit()
        return publication_id
    except Exception:
        connection.rollback()
        raise
