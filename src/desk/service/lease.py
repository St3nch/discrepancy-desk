"""Run claim leases and claim tokens (ADR 8 / ticket 06 / F-25).

Refresh is centralized: every run-touching executor tool calls
``validate_and_refresh_claim`` so tickets 07+ inherit the same rule.

F-25a: only a currently valid, unexpired claimed lease may be refreshed.
An expired lease fails closed; the stale executor cannot renew it.

F-25b: each claim instance has an opaque claim_token (not executor identity).
Tools must present the token from the claimed-run packet; a wrong or missing
token fails as RUN_CLAIM_STALE. Reclaim clears the token.

Expiry is evaluated, not scheduled: reclaim_expired_leases runs when something
looks at claimable work (claim_next_run, approve_run, list_runs). No sweeper.

Note: reclaim_expired_leases is also invoked from list_runs (a GET). Lazy
evaluation means that read path mutates expired claimed → approved. Do not
"clean up" that side effect without moving expiry evaluation elsewhere — it is
intentional, not an accident.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hmac import compare_digest

from sqlalchemy import Connection, select, update

from desk.db.schema import runs
from desk.refusals import DeskRefusal

# Default lease length. Tests may pass a shorter ttl_seconds.
LEASE_TTL_SECONDS = 15 * 60  # 15 minutes


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def format_utc(dt: datetime) -> str:
    """Canonical write format: ISO-8601 with explicit +00:00 (never Z)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def parse_utc(value: str) -> datetime:
    """Parse lease timestamps written by format_utc (always +00:00, never Z).

    A trailing Z is accepted only for externally-supplied or legacy values; no
    Desk writer emits Z.
    """
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def lease_deadline(now: datetime | None = None, *, ttl_seconds: int = LEASE_TTL_SECONDS) -> str:
    base = now or utc_now()
    return format_utc(base + timedelta(seconds=ttl_seconds))


def new_claim_token() -> str:
    """Opaque claim-instance token (not an executor id)."""
    return secrets.token_urlsafe(32)


def validate_claim(
    conn: Connection,
    run_id: int,
    claim_token: str,
    *,
    now: datetime | None = None,
    ttl_seconds: int = LEASE_TTL_SECONDS,
    refresh: bool = True,
    allow_suspended: bool = False,
) -> None:
    """Validate claim token (and lease when claimed).

    Shared choke point for run-touching executor tools.

    * ``refresh=True`` (default): extend the lease when status is claimed.
      Use ``refresh=False`` when the next write will clear the lease (e.g.
      suspend_run) so validation does not perform a pointless write.
    * ``allow_suspended=True``: accept status suspended with a matching token
      and no lease (human wait). Work tools that mutate captures/claims must
      leave this false.
    """
    base = now or utc_now()
    row = conn.execute(
        select(
            runs.c.id,
            runs.c.status,
            runs.c.lease_expires_at,
            runs.c.claim_token,
        ).where(runs.c.id == run_id)
    ).one_or_none()
    if row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {run_id}.",
            what_was_preserved="No run lease or token was changed.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Call claim_next_run to obtain a work packet.",
        )

    status = str(row.status)
    allowed = {"claimed", "suspended"} if allow_suspended else {"claimed"}
    if status not in allowed:
        raise DeskRefusal(
            code="RUN_NOT_CLAIMED",
            what_happened=(
                f"Run {run_id} is in status {status!r}; only a claimed run "
                "accepts executor work tools."
                if not allow_suspended
                else (
                    f"Run {run_id} is in status {status!r}; this tool requires "
                    "a claimed or suspended run held by this claim_token."
                )
            ),
            what_was_preserved="No run lease or token was changed.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Call claim_next_run to claim (or reclaim) a run.",
        )

    presented = (claim_token or "").strip()
    stored = row.claim_token
    if not presented or stored is None or not compare_digest(presented, str(stored)):
        raise DeskRefusal(
            code="RUN_CLAIM_STALE",
            what_happened=(
                f"Claim token does not match the active claim on run {run_id} "
                "(missing, wrong, or superseded by a later claim)."
            ),
            what_was_preserved="No run lease was extended; partial work is intact.",
            what_was_not_changed="Run status, lease, and token are unchanged.",
            what_you_can_do=(
                "Call claim_next_run again and use the new claim_token; "
                "do not retry with the old token."
            ),
        )

    # Suspended: token holds identity; no lease to check or refresh.
    if status == "suspended":
        return

    expires_raw = row.lease_expires_at
    if expires_raw is None:
        raise DeskRefusal(
            code="RUN_LEASE_EXPIRED",
            what_happened=f"Run {run_id} is claimed but has no lease_expires_at.",
            what_was_preserved="No run lease was extended; partial work is intact.",
            what_was_not_changed="Run status and token are unchanged.",
            what_you_can_do="Call claim_next_run to reclaim the run.",
        )
    expires_at = parse_utc(str(expires_raw))
    if expires_at <= base:
        raise DeskRefusal(
            code="RUN_LEASE_EXPIRED",
            what_happened=(
                f"Lease on run {run_id} expired at {expires_raw}; this claim can "
                "no longer work the run."
            ),
            what_was_preserved="No run lease was extended; partial work is intact.",
            what_was_not_changed=(
                "Run status and token are unchanged (reclaim via claim_next_run)."
            ),
            what_you_can_do=(
                "Call claim_next_run to reclaim the run; do not retry with the expired claim."
            ),
        )

    if not refresh:
        return

    new_expires = lease_deadline(base, ttl_seconds=ttl_seconds)
    conn.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .where(runs.c.status == "claimed")
        .where(runs.c.claim_token == presented)
        .values(lease_expires_at=new_expires, updated_at=format_utc(base))
    )


def validate_and_refresh_claim(
    conn: Connection,
    run_id: int,
    claim_token: str,
    *,
    now: datetime | None = None,
    ttl_seconds: int = LEASE_TTL_SECONDS,
) -> None:
    """Validate claim token + unexpired lease, then refresh the lease.

    Convenience for mutative work tools (capture_url, read_capture, propose_claim).
    """
    validate_claim(
        conn,
        run_id,
        claim_token,
        now=now,
        ttl_seconds=ttl_seconds,
        refresh=True,
        allow_suspended=False,
    )


def reclaim_expired_leases(
    conn: Connection,
    *,
    now: datetime | None = None,
) -> int:
    """Revert claimed runs past lease_expires_at to approved.

    Partial work (captures, claims) is left intact. Clears lease and claim_token
    so a stale packet can never match again.

    Compares *parsed* datetimes (not lexicographic strings) so format variants
    cannot invert order.
    """
    base = now or utc_now()
    now_s = format_utc(base)
    rows = conn.execute(
        select(runs.c.id, runs.c.lease_expires_at)
        .where(runs.c.status == "claimed")
        .where(runs.c.lease_expires_at.is_not(None))
    ).all()
    expired_ids: list[int] = []
    for row in rows:
        try:
            expires_at = parse_utc(str(row.lease_expires_at))
        except ValueError:
            # Corrupt lease timestamp — treat as expired so the run is reclaimable.
            expired_ids.append(int(row.id))
            continue
        if expires_at <= base:
            expired_ids.append(int(row.id))

    if not expired_ids:
        return 0

    result = conn.execute(
        update(runs)
        .where(runs.c.id.in_(expired_ids))
        .where(runs.c.status == "claimed")
        .values(
            status="approved",
            lease_expires_at=None,
            claim_token=None,
            updated_at=now_s,
        )
    )
    return int(result.rowcount or 0)
