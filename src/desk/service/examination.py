"""Mark captures examined by explicit report (F-32).

Shared by close_run (executor) and attest_coverage (operator). Examined is
always reported, never inferred. A human reporting it is more authoritative
than an executor, not less.
"""

from __future__ import annotations

from sqlalchemy import Connection, select, update

from desk.db.schema import captures
from desk.refusals import DeskRefusal


def mark_reported_examined(
    conn: Connection,
    *,
    case_id: int,
    capture_ids: list[int],
    run_id: int | None = None,
) -> int:
    """Mark reported uncited captures as examined.

    Ownership (null-safe):
    - If ``run_id`` is set (close_run): capture belongs to that run **or** to
      the run's case (attached lead material).
    - If ``run_id`` is None (attest_coverage): capture must belong to the case.

    Cited stays cited (refusal). Already-examined continues idempotently.
    Omitted unexamined captures stay unexamined.
    """
    seen: set[int] = set()
    ordered: list[int] = []
    for raw_id in capture_ids:
        cid = int(raw_id)
        if cid in seen:
            continue
        seen.add(cid)
        ordered.append(cid)

    preserved = (
        "The run was not closed; no capture statuses changed."
        if run_id is not None
        else "No attestation was written; no capture statuses changed."
    )
    not_changed = "Nothing was written."

    marked = 0
    for cid in ordered:
        row = conn.execute(
            select(
                captures.c.id,
                captures.c.run_id,
                captures.c.case_id,
                captures.c.status,
            ).where(captures.c.id == cid)
        ).one_or_none()
        if row is None:
            raise DeskRefusal(
                code="CAPTURE_NOT_FOUND",
                what_happened=f"No capture exists with id {cid}.",
                what_was_preserved=preserved,
                what_was_not_changed=not_changed,
                what_you_can_do=(
                    "Pass capture ids from this run's capture_url results."
                    if run_id is not None
                    else "Pass capture ids that belong to this case."
                ),
            )

        owned_by_case = row.case_id is not None and int(row.case_id) == case_id
        owned_by_run = run_id is not None and row.run_id is not None and int(row.run_id) == run_id
        if run_id is not None:
            allowed = owned_by_run or owned_by_case
        else:
            allowed = owned_by_case

        if not allowed:
            run_label = "none" if row.run_id is None else str(int(row.run_id))
            case_label = "none" if row.case_id is None else str(int(row.case_id))
            if run_id is not None:
                what = (
                    f"Capture {cid} is not owned by run {run_id} or case {case_id} "
                    f"(capture run_id={run_label}, case_id={case_label})."
                )
                do = (
                    "Report only captures from this run, or lead material attached "
                    "to this run's case."
                )
                code = "CAPTURE_WRONG_RUN"
            else:
                what = (
                    f"Capture {cid} does not belong to case {case_id} "
                    f"(capture case_id={case_label})."
                )
                do = "Report only captures that belong to this case."
                code = "CAPTURE_WRONG_CASE"
            raise DeskRefusal(
                code=code,
                what_happened=what,
                what_was_preserved=preserved,
                what_was_not_changed=not_changed,
                what_you_can_do=do,
            )

        status = str(row.status)
        if status == "cited":
            raise DeskRefusal(
                code="EXAMINED_CAPTURE_ALREADY_CITED",
                what_happened=(
                    f"Capture {cid} is already cited by a claim; it cannot be "
                    "reported as examined-with-nothing-claimed."
                ),
                what_was_preserved=preserved,
                what_was_not_changed=not_changed,
                what_you_can_do="Omit cited captures from examined_capture_ids.",
            )
        if status == "examined":
            continue
        if status != "unexamined":
            raise DeskRefusal(
                code="CAPTURE_STATUS_INVALID",
                what_happened=(
                    f"Capture {cid} has status {status!r}; only unexamined "
                    "captures can be reported as examined."
                ),
                what_was_preserved=preserved,
                what_was_not_changed=not_changed,
                what_you_can_do="Report only unexamined, uncited captures.",
            )
        result = conn.execute(
            update(captures)
            .where(captures.c.id == cid)
            .where(captures.c.status == "unexamined")
            .values(status="examined")
        )
        if result.rowcount != 1:
            raise DeskRefusal(
                code="CAPTURE_STATUS_INVALID",
                what_happened=f"Could not mark capture {cid} examined (status changed).",
                what_was_preserved=preserved,
                what_was_not_changed=not_changed,
                what_you_can_do="Retry with a fresh view of capture statuses.",
            )
        marked += 1
    return marked
