"""Proof A -- admission ordering under concurrency.

Harness section 2 as corrected by reconciliation section 2.

The original harness choreography was a tautology: because Session B starts
second, B's ordinal is higher than A's whether or not the advisory lock does
anything. The load-bearing evidence is therefore the *observer* -- a third
connection that catches B waiting on the lock while A still holds it, and
catches the sequence still standing at A's already-allocated ordinal.

Reconciliation section 2.1 also fixed the ordering: A allocates its ordinal
BEFORE B attempts the lock, so the sequence observation has a value to compare
against. ``pg_sleep(8)`` is not normative here and is not used; A's transaction
is held open by a client-side synchronization gate instead.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import psycopg

from . import sql
from .databases import close_connections
from .deadline import Deadline
from .errors import DeadlineExceeded, ErrorCategory, ProofRunError
from .evidence import Assertion, ProofResult, assert_that
from .execution import StepRecorder, run_setup

#: How long the observer may wait for B to register as blocked, and how long B
#: may take to acquire the lock once A commits.
OBSERVER_DEADLINE_SECONDS = 30.0
ACQUIRE_DEADLINE_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.05

LABEL_A = "A-delayed-commit"
LABEL_B = "B-waits-for-A"
LABEL_C = "C-rolls-back"
LABEL_D = "D-after-rollback"


@dataclass
class ProofAObservations:
    """Everything Proof A recorded, sufficient to re-derive every assertion."""

    a_pid: int | None = None
    b_pid: int | None = None
    a_ordinal: int | None = None
    b_ordinal: int | None = None
    c_ordinal: int | None = None
    d_ordinal: int | None = None
    observer_lock_rows: list[Any] = field(default_factory=list)
    observer_poll_count: int = 0
    blocking_pids: list[int] = field(default_factory=list)
    sequence_last_value_while_b_blocked: int | None = None
    b_before_lock: str | None = None
    b_after_lock: str | None = None
    committed_rows: list[Any] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "a_backend_pid": self.a_pid,
            "b_backend_pid": self.b_pid,
            "a_ordinal": self.a_ordinal,
            "b_ordinal": self.b_ordinal,
            "c_allocated_ordinal_rolled_back": self.c_ordinal,
            "d_ordinal": self.d_ordinal,
            "observer_lock_rows": self.observer_lock_rows,
            "observer_poll_count": self.observer_poll_count,
            "blocking_pids_of_b": self.blocking_pids,
            "sequence_last_value_while_b_blocked": self.sequence_last_value_while_b_blocked,
            "b_before_lock": self.b_before_lock,
            "b_after_lock": self.b_after_lock,
            "committed_rows": self.committed_rows,
        }


def _lock_row(rows: list[Any], pid: int | None) -> tuple | None:
    """Find the advisory-lock row belonging to ``pid``."""
    for row in rows:
        if row and row[0] == pid:
            return tuple(row)
    return None


def observer_expectations(obs: ProofAObservations) -> dict[str, tuple[Any, Any]]:
    """The five observer facts, as ``name -> (expected, observed)`` pairs.

    Reconciliation section 2.1 requires all five to be observed *before*
    Session A commits, and the same five appear as report assertions. Deriving
    both from this one function keeps the release gate and the recorded
    verdict from drifting apart.
    """
    a_row = _lock_row(obs.observer_lock_rows, obs.a_pid)
    b_row = _lock_row(obs.observer_lock_rows, obs.b_pid)
    return {
        "observer_saw_A_holding_advisory_lock": (True, bool(a_row[1]) if a_row else None),
        "observer_saw_B_waiting_on_advisory_lock": (False, bool(b_row[1]) if b_row else None),
        "observer_saw_B_wait_event_type_Lock": ("Lock", b_row[2] if b_row else None),
        "pg_blocking_pids_of_B_contains_A": (
            True,
            obs.a_pid in obs.blocking_pids if obs.a_pid is not None else None,
        ),
        # Paired with the allocation flag so an unobserved sequence cannot
        # satisfy this condition by comparing None against a missing ordinal.
        "sequence_unadvanced_while_B_blocked": (
            {"a_ordinal_allocated": True, "sequence_last_value": obs.a_ordinal},
            {
                "a_ordinal_allocated": obs.a_ordinal is not None,
                "sequence_last_value": obs.sequence_last_value_while_b_blocked,
            },
        ),
    }


def observer_conditions(obs: ProofAObservations) -> dict[str, bool]:
    """Whether each observer fact currently holds. Pure and database-free."""
    return {
        name: expected == observed
        for name, (expected, observed) in observer_expectations(obs).items()
    }


def evaluate_proof_a(obs: ProofAObservations) -> list[Assertion]:
    """Decide Proof A from recorded observations. Pure and database-free."""
    committed_orders = [row[0] for row in obs.committed_rows]

    return [
        # -- Observed blocking. This, not elapsed time, is the proof. ----------
        *(
            assert_that(name, expected, observed)
            for name, (expected, observed) in observer_expectations(obs).items()
        ),
        # -- Serialized gate order. -------------------------------------------
        assert_that(
            "A_ordinal_lower_than_B_ordinal",
            True,
            (
                obs.a_ordinal is not None
                and obs.b_ordinal is not None
                and obs.a_ordinal < obs.b_ordinal
            ),
        ),
        # -- Rollback gap (reconciliation section 2.2). ------------------------
        assert_that(
            "rolled_back_ordinal_absent_from_table",
            True,
            obs.c_ordinal is not None and obs.c_ordinal not in committed_orders,
        ),
        assert_that(
            "D_ordinal_strictly_greater_than_rolled_back_C_ordinal",
            True,
            (
                obs.c_ordinal is not None
                and obs.d_ordinal is not None
                and obs.d_ordinal > obs.c_ordinal
            ),
        ),
        assert_that(
            "committed_table_holds_exactly_A_B_D",
            [[obs.a_ordinal, LABEL_A], [obs.b_ordinal, LABEL_B], [obs.d_ordinal, LABEL_D]],
            [list(row) for row in obs.committed_rows],
        ),
    ]


class _SessionB:
    """Runs Session B on its own thread so its lock wait is genuinely blocking."""

    def __init__(self, conn: psycopg.Connection, recorder: StepRecorder) -> None:
        self._conn = conn
        self._recorder = recorder
        self.before_lock: str | None = None
        self.after_lock: str | None = None
        self.ordinal: int | None = None
        self.error: BaseException | None = None
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self._run, name="fnd-pg01-session-b", daemon=True)

    def _run(self) -> None:
        try:
            rows = self._recorder.run(self._conn, "A.b.before_lock", sql.SELECT_CLOCK_TIMESTAMP)
            self.before_lock = str(rows[0][0])

            # Blocks here until Session A's transaction ends.
            self._recorder.run(
                self._conn,
                "A.b.acquire_advisory_xact_lock",
                sql.ACQUIRE_ADVISORY_XACT_LOCK,
                {"lock_key": sql.PROOF_A_LOCK_KEY},
            )
            rows = self._recorder.run(self._conn, "A.b.after_lock", sql.SELECT_CLOCK_TIMESTAMP)
            self.after_lock = str(rows[0][0])

            rows = self._recorder.run(
                self._conn, "A.b.insert", sql.PROOF_A_INSERT, {"label": LABEL_B}
            )
            self.ordinal = rows[0][0]
            self._conn.commit()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the main thread
            self.error = exc
        finally:
            self.finished.set()


def _poll_until_observer_evidence_complete(
    observer: psycopg.Connection,
    recorder: StepRecorder,
    obs: ProofAObservations,
    deadline: Deadline,
) -> None:
    """Block until every observer condition holds, or fail closed.

    This is the release gate for Session A's commit. Reconciliation section 2.1
    is explicit: "Only after all observer assertions pass does the runner commit
    A." Committing on a partial observation -- say, B registered as waiting but
    ``pg_blocking_pids`` not yet naming A -- would leave the decisive evidence
    to be gathered after the very transaction it was supposed to constrain.

    If the deadline elapses, this raises and Session A is never committed. The
    caller's failure handling unwinds, cancels, rolls back and closes, and
    database cleanup still runs.
    """
    if obs.a_pid is None or obs.b_pid is None or obs.a_ordinal is None:
        raise ProofRunError(
            ErrorCategory.INTERNAL_ERROR,
            "observer gate reached before session A allocated its ordinal",
        )

    lock_params = {"lock_key": sql.PROOF_A_LOCK_KEY, "pids": [obs.a_pid, obs.b_pid]}
    pid_params = {"pid": obs.b_pid}
    while True:
        deadline.check(
            "complete observer evidence that session B is blocked by session A on the advisory lock"
        )
        obs.observer_poll_count += 1
        with observer.cursor() as cur:
            cur.execute(sql.OBSERVER_ADVISORY_LOCKS, lock_params)
            lock_rows = [list(row) for row in cur.fetchall()]
            cur.execute(sql.OBSERVER_BLOCKING_PIDS, pid_params)
            blocking_pids = list(cur.fetchone()[0] or [])
            cur.execute(sql.OBSERVER_SEQUENCE_LAST_VALUE)
            last_value = cur.fetchone()[0]

        obs.observer_lock_rows = lock_rows
        obs.blocking_pids = blocking_pids
        obs.sequence_last_value_while_b_blocked = last_value

        if all(observer_conditions(obs).values()):
            # Record exactly the readings that satisfied the gate. Earlier polls
            # differ only in that the evidence was not yet complete.
            recorder.record_rows(
                "A.observer.advisory_locks_while_B_blocked",
                sql.OBSERVER_ADVISORY_LOCKS,
                lock_params,
                lock_rows,
            )
            recorder.record_rows(
                "A.observer.blocking_pids_while_B_blocked",
                sql.OBSERVER_BLOCKING_PIDS,
                pid_params,
                [[blocking_pids]],
            )
            recorder.record_rows(
                "A.observer.sequence_last_value_while_B_blocked",
                sql.OBSERVER_SEQUENCE_LAST_VALUE,
                None,
                [[last_value]],
            )
            return
        time.sleep(_POLL_INTERVAL_SECONDS)


def run_proof_a(
    connect_fn: Any,
    database: str,
    result: ProofResult,
) -> ProofAObservations:
    """Execute Proof A. Raises :class:`ProofRunError` on a hard failure."""
    recorder = StepRecorder(result)
    obs = ProofAObservations()

    conn_a = connect_fn(database, "fnd_pg01_proof_a_session_a", False)
    conn_b = None
    observer = None
    session_b = None
    try:
        run_setup(recorder, conn_a, sql.PROOF_A_SETUP, "A")

        conn_b = connect_fn(database, "fnd_pg01_proof_a_session_b", False)
        observer = connect_fn(database, "fnd_pg01_proof_a_observer", True)

        # 1-2. A begins, records its pid, and takes the lock.
        obs.a_pid = recorder.run(conn_a, "A.a.backend_pid", sql.SELECT_BACKEND_PID)[0][0]
        recorder.run(
            conn_a,
            "A.a.acquire_advisory_xact_lock",
            sql.ACQUIRE_ADVISORY_XACT_LOCK,
            {"lock_key": sql.PROOF_A_LOCK_KEY},
        )

        # 3. A allocates its ordinal and holds the transaction open on a
        #    client-side gate. Reconciliation section 2.1 requires the
        #    allocation to happen before B attempts the lock.
        obs.a_ordinal = recorder.run(conn_a, "A.a.insert", sql.PROOF_A_INSERT, {"label": LABEL_A})[
            0
        ][0]

        # 4. B begins and records its pid before it can block.
        obs.b_pid = recorder.run(conn_b, "A.b.backend_pid", sql.SELECT_BACKEND_PID)[0][0]

        # 5. B attempts the lock on an independent execution path.
        session_b = _SessionB(conn_b, recorder)
        session_b.thread.start()

        # 6. The release gate. Every observer condition must hold before A is
        #    allowed to commit; a missed deadline fails the proof instead.
        _poll_until_observer_evidence_complete(
            observer, recorder, obs, Deadline(OBSERVER_DEADLINE_SECONDS)
        )

        # 7. Only after all observer conditions passed does A commit.
        conn_a.commit()

        # 8. B must acquire within a bounded deadline.
        acquire_deadline = Deadline(ACQUIRE_DEADLINE_SECONDS)
        session_b.finished.wait(timeout=acquire_deadline.remaining())
        if not session_b.finished.is_set():
            _cancel_quietly(conn_b)
            raise DeadlineExceeded(
                "session B did not complete within "
                f"{ACQUIRE_DEADLINE_SECONDS:g}s after session A committed"
            )
        if session_b.error is not None:
            raise ProofRunError(
                ErrorCategory.PROOF_STEP_UNEXPECTED,
                "session B failed while acquiring the advisory lock or inserting",
            ) from None

        obs.b_ordinal = session_b.ordinal
        obs.b_before_lock = session_b.before_lock
        obs.b_after_lock = session_b.after_lock
        session_b.thread.join(timeout=5)

        # -- Rollback gap (harness section 2.3, reconciliation section 2.2). ---
        recorder.run(
            conn_a,
            "A.c.acquire_advisory_xact_lock",
            sql.ACQUIRE_ADVISORY_XACT_LOCK,
            {"lock_key": sql.PROOF_A_LOCK_KEY},
        )
        obs.c_ordinal = recorder.run(conn_a, "A.c.insert", sql.PROOF_A_INSERT, {"label": LABEL_C})[
            0
        ][0]
        conn_a.rollback()

        recorder.run(
            conn_a,
            "A.d.acquire_advisory_xact_lock",
            sql.ACQUIRE_ADVISORY_XACT_LOCK,
            {"lock_key": sql.PROOF_A_LOCK_KEY},
        )
        obs.d_ordinal = recorder.run(conn_a, "A.d.insert", sql.PROOF_A_INSERT, {"label": LABEL_D})[
            0
        ][0]
        conn_a.commit()

        obs.committed_rows = [
            list(row) for row in recorder.run(conn_a, "A.final.table", sql.PROOF_A_TABLE_DUMP)
        ]
        conn_a.commit()
        return obs
    finally:
        # Unwind, cancel, roll back, then close. Runner-owned connections are
        # closed here so DROP DATABASE has nothing of ours left to
        # force-terminate (reconciliation section 5).
        if session_b is not None and session_b.thread.is_alive():
            _cancel_quietly(conn_b)
            session_b.thread.join(timeout=5)
        for conn in (conn_a, conn_b):
            _rollback_quietly(conn)
        result.connection_closures.extend(
            close_connections(
                [("observer", observer), ("session_b", conn_b), ("session_a", conn_a)]
            )
        )


def _cancel_quietly(conn: psycopg.Connection | None) -> None:
    """Best-effort unblocking of a stuck session during failure handling."""
    if conn is None:
        return
    with contextlib.suppress(Exception):
        conn.cancel()


def _rollback_quietly(conn: psycopg.Connection | None) -> None:
    """Discard any transaction left open by a failure path.

    Best-effort: closing would roll back anyway, and a rollback failure is
    subsumed by the close outcome, which *is* recorded.
    """
    if conn is None:
        return
    with contextlib.suppress(Exception):
        conn.rollback()
