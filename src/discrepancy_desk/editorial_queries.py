from __future__ import annotations

import sqlite3
from datetime import datetime


PIPELINE_VIEWS = frozenset(
    {
        "needs_my_review",
        "approved_unscheduled",
        "manual_ready",
        "awaiting_reconciliation",
        "publication_mismatches",
        "blocked",
        "recently_published",
    }
)


def _require_account(connection: sqlite3.Connection, account_id: str) -> None:
    if not account_id:
        raise ValueError("account scope is required")
    if connection.execute("SELECT 1 FROM owned_accounts WHERE id=?", (account_id,)).fetchone() is None:
        raise ValueError("unknown account")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def list_schedule(
    connection: sqlite3.Connection, *, account_id: str, start: str, end: str
) -> list[dict[str, object]]:
    _require_account(connection, account_id)
    if _parse(end) < _parse(start):
        raise ValueError("schedule range end precedes start")
    rows = connection.execute(
        """SELECT s.*, w.title, ep.lane, ep.topic, ep.priority
        FROM schedule_slots s
        JOIN work_items w ON w.id=s.work_item_id
        JOIN editorial_profiles ep ON ep.work_item_id=s.work_item_id
        WHERE s.account_id=? AND s.status='active'
          AND s.scheduled_for IS NOT NULL
          AND s.scheduled_for>=? AND s.scheduled_for<=?
        ORDER BY s.scheduled_for, s.id""",
        (account_id, start, end),
    ).fetchall()
    return [dict(row) for row in rows]


def list_unscheduled_reserve(
    connection: sqlite3.Connection, *, account_id: str
) -> list[dict[str, object]]:
    _require_account(connection, account_id)
    rows = connection.execute(
        """SELECT w.id, w.title, w.state, ep.lane, ep.topic, ep.priority, ep.is_dormant
        FROM work_items w
        JOIN editorial_profiles ep ON ep.work_item_id=w.id
        WHERE ep.account_id=? AND ep.is_dormant=0
          AND NOT EXISTS (
            SELECT 1 FROM schedule_slots s
            WHERE s.work_item_id=w.id AND s.status='active'
          )
        ORDER BY ep.priority DESC, w.updated_at DESC, w.id""",
        (account_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def evaluate_ready_to_post(
    connection: sqlite3.Connection, *, work_item_id: str, account_id: str, now: str
) -> dict[str, object]:
    _require_account(connection, account_id)
    profile = connection.execute(
        """SELECT w.state, ep.is_dormant
        FROM work_items w JOIN editorial_profiles ep ON ep.work_item_id=w.id
        WHERE w.id=? AND ep.account_id=?""",
        (work_item_id, account_id),
    ).fetchone()
    if profile is None:
        raise ValueError("work item/account scope mismatch")

    reasons: list[str] = []
    if profile[1]:
        reasons.append("dormant")
    if profile[0] in {"evidence_blocked", "publication_mismatch", "withdrawn", "rejected"}:
        reasons.append(f"state:{profile[0]}")

    revision = connection.execute(
        """SELECT r.id, r.binding_sha256
        FROM revisions r
        WHERE r.work_item_id=? AND r.owned_account_id=?
        ORDER BY r.created_at DESC, r.id DESC LIMIT 1""",
        (work_item_id, account_id),
    ).fetchone()
    approval_id: str | None = None
    if revision is None:
        reasons.append("no_current_revision")
    else:
        approval = connection.execute(
            """SELECT id, decision FROM approvals
            WHERE revision_id=? AND binding_sha256=?
            ORDER BY decided_at DESC, id DESC LIMIT 1""",
            (revision[0], revision[1]),
        ).fetchone()
        if approval is None or approval[1] != "approved":
            reasons.append("no_live_approval")
        else:
            approval_id = str(approval[0])
        if connection.execute(
            "SELECT 1 FROM publications WHERE revision_id=? OR approval_id=? LIMIT 1",
            (revision[0], approval_id or ""),
        ).fetchone() is not None:
            reasons.append("authority_consumed")
        schedule = connection.execute(
            """SELECT approved_revision_id, stale_after
            FROM schedule_slots WHERE work_item_id=? AND account_id=? AND status='active'""",
            (work_item_id, account_id),
        ).fetchone()
        if schedule is not None:
            if schedule[0] is not None and schedule[0] != revision[0]:
                reasons.append("schedule_revision_mismatch")
            if schedule[1] is not None and _parse(schedule[1]) < _parse(now):
                reasons.append("expired")

    bad_evidence = connection.execute(
        """SELECT 1 FROM evidence_refs
        WHERE work_item_id=? AND verification_state!='verified' LIMIT 1""",
        (work_item_id,),
    ).fetchone()
    if bad_evidence is not None:
        reasons.append("evidence_not_verified")

    return {
        "work_item_id": work_item_id,
        "account_id": account_id,
        "ready": not reasons,
        "reasons": reasons,
        "revision_id": None if revision is None else revision[0],
        "approval_id": approval_id,
    }


def list_pipeline_view(
    connection: sqlite3.Connection, *, account_id: str, view_name: str, now: str
) -> list[dict[str, object]]:
    _require_account(connection, account_id)
    if view_name not in PIPELINE_VIEWS:
        raise ValueError("unknown pipeline view")
    rows = connection.execute(
        """SELECT w.id, w.title, w.state, w.updated_at, ep.lane, ep.topic, ep.priority
        FROM work_items w JOIN editorial_profiles ep ON ep.work_item_id=w.id
        WHERE ep.account_id=? ORDER BY w.updated_at DESC, w.id""",
        (account_id,),
    ).fetchall()
    results: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        state = str(item["state"])
        include = False
        if view_name == "needs_my_review":
            include = state == "human_review_needed"
        elif view_name == "manual_ready":
            include = state == "manual_ready"
        elif view_name == "awaiting_reconciliation":
            include = state == "published" and connection.execute(
                """SELECT 1 FROM publications p JOIN revisions r ON r.id=p.revision_id
                WHERE r.work_item_id=? AND p.verification_state='owner_confirmed' LIMIT 1""",
                (item["id"],),
            ).fetchone() is not None
        elif view_name == "publication_mismatches":
            include = state == "publication_mismatch"
        elif view_name == "blocked":
            include = state in {"evidence_blocked", "withdrawn", "rejected"}
        elif view_name == "recently_published":
            include = state == "published"
        elif view_name == "approved_unscheduled":
            ready = evaluate_ready_to_post(
                connection, work_item_id=str(item["id"]), account_id=account_id, now=now
            )
            include = bool(ready["ready"]) and connection.execute(
                "SELECT 1 FROM schedule_slots WHERE work_item_id=? AND status='active'",
                (item["id"],),
            ).fetchone() is None
        if include:
            results.append(item)
    return results


def get_command_center(
    connection: sqlite3.Connection, *, account_id: str, now: str
) -> dict[str, object]:
    _require_account(connection, account_id)
    return {
        "needs_my_review": list_pipeline_view(
            connection, account_id=account_id, view_name="needs_my_review", now=now
        ),
        "approved_unscheduled": list_pipeline_view(
            connection, account_id=account_id, view_name="approved_unscheduled", now=now
        ),
        "manual_ready": list_pipeline_view(
            connection, account_id=account_id, view_name="manual_ready", now=now
        ),
        "awaiting_reconciliation": list_pipeline_view(
            connection, account_id=account_id, view_name="awaiting_reconciliation", now=now
        ),
        "publication_mismatches": list_pipeline_view(
            connection, account_id=account_id, view_name="publication_mismatches", now=now
        ),
        "blocked": list_pipeline_view(
            connection, account_id=account_id, view_name="blocked", now=now
        ),
        "recently_published": list_pipeline_view(
            connection, account_id=account_id, view_name="recently_published", now=now
        ),
        "reserve": list_unscheduled_reserve(connection, account_id=account_id),
    }


def recommend_need_a_post(
    connection: sqlite3.Connection,
    *,
    account_id: str,
    slot_start: str,
    slot_end: str,
    now: str,
) -> dict[str, object]:
    _require_account(connection, account_id)
    if _parse(slot_end) < _parse(slot_start):
        raise ValueError("slot end precedes start")
    candidates = []
    for item in list_unscheduled_reserve(connection, account_id=account_id):
        result = evaluate_ready_to_post(
            connection, work_item_id=str(item["id"]), account_id=account_id, now=now
        )
        if result["ready"]:
            candidates.append(
                {
                    **item,
                    "rationale": "approved, account-scoped, unscheduled inventory",
                }
            )
    candidates.sort(key=lambda row: (-int(row["priority"]), str(row["id"])))
    return {
        "slot_start": slot_start,
        "slot_end": slot_end,
        "candidates": candidates,
        "leave_empty": not candidates,
        "rationale": (
            "No strong governed candidate exists; leaving the slot empty is correct."
            if not candidates
            else "Ranked from existing governed inventory; no content was created or scheduled."
        ),
    }
