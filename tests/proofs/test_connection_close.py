"""Connection-close failure aggregation and precedence.

Reconciliation section 5 makes ``DROP DATABASE ... WITH (FORCE)`` a cleanup
backstop, not a substitute for closing runner-owned connections. Suppressing a
close failure would quietly hand the work to FORCE and let the proof still read
as clean, so a close failure must become visible evidence and force a non-zero
result -- without displacing an already-recorded primary failure.

Fake connection objects stand in for the driver here; no PostgreSQL is used.
"""

from __future__ import annotations

import psycopg
import pytest

from tools.postgres_foundation_proofs.databases import close_connections
from tools.postgres_foundation_proofs.errors import ErrorCategory
from tools.postgres_foundation_proofs.evidence import Outcome, ProofResult, assert_that
from tools.postgres_foundation_proofs.runner import apply_close_failure_precedence


class FakeConnection:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        if self.error is not None:
            raise self.error


def test_successful_closes_are_recorded():
    conn = FakeConnection()
    outcomes = close_connections([("session_a", conn)])
    assert outcomes == [{"connection": "session_a", "closed": True}]
    assert conn.close_attempts == 1


def test_none_connections_are_skipped_not_recorded():
    assert close_connections([("observer", None)]) == []


def test_a_close_failure_is_recorded_rather_than_suppressed():
    outcomes = close_connections([("session_b", FakeConnection(RuntimeError("boom")))])
    assert outcomes[0]["closed"] is False
    assert outcomes[0]["error_category"] == str(ErrorCategory.CONNECTION_CLOSE_FAILED)


def test_close_failure_message_is_runner_authored():
    error = psycopg.errors.AdminShutdown("terminating connection due to administrator command")
    outcomes = close_connections([("session_a", FakeConnection(error))])
    assert "could not close runner-owned connection" in outcomes[0]["message"]
    assert "administrator command" not in outcomes[0]["message"]


def test_one_failure_does_not_prevent_the_remaining_closes():
    observer = FakeConnection(RuntimeError("boom"))
    session_b = FakeConnection()
    session_a = FakeConnection()

    outcomes = close_connections(
        [("observer", observer), ("session_b", session_b), ("session_a", session_a)]
    )

    assert [o["closed"] for o in outcomes] == [False, True, True]
    assert observer.close_attempts == 1
    assert session_b.close_attempts == 1
    assert session_a.close_attempts == 1


def test_every_connection_can_fail_and_all_are_still_attempted():
    conns = [FakeConnection(RuntimeError("boom")) for _ in range(3)]
    outcomes = close_connections([(f"c{i}", c) for i, c in enumerate(conns)])
    assert all(o["closed"] is False for o in outcomes)
    assert all(c.close_attempts == 1 for c in conns)


def test_close_connections_never_raises():
    # Ordinary driver and runtime errors are recorded, never propagated.
    assert close_connections([("c", FakeConnection(OSError("gone")))])[0]["closed"] is False


def _passing_result() -> ProofResult:
    result = ProofResult(proof="A", title="t")
    result.assertions.append(assert_that("x", 1, 1))
    return result


def test_a_proof_that_could_not_close_its_connections_cannot_pass():
    result = _passing_result()
    assert result.outcome is Outcome.PASS
    result.connection_closures = [{"connection": "session_a", "closed": False}]
    assert result.close_failures
    assert result.outcome is Outcome.FAIL


def test_successful_closes_do_not_affect_the_outcome():
    result = _passing_result()
    result.connection_closures = [{"connection": "session_a", "closed": True}]
    assert result.close_failures == []
    assert result.outcome is Outcome.PASS


def test_precedence_records_a_close_failure_when_nothing_else_failed():
    result = _passing_result()
    result.connection_closures = [{"connection": "observer", "closed": False}]

    apply_close_failure_precedence(result)

    assert result.failure_category == str(ErrorCategory.CONNECTION_CLOSE_FAILED)
    assert "backstop, not a substitute" in result.failure_message
    assert result.outcome is Outcome.FAIL


def test_precedence_never_overwrites_an_existing_primary_failure():
    result = _passing_result()
    result.failure_category = str(ErrorCategory.DEADLINE_EXCEEDED)
    result.failure_message = "the original cause"
    result.connection_closures = [{"connection": "observer", "closed": False}]

    apply_close_failure_precedence(result)

    assert result.failure_category == str(ErrorCategory.DEADLINE_EXCEEDED)
    assert result.failure_message == "the original cause"
    # The close failures remain visible as evidence alongside it.
    assert result.close_failures
    assert result.outcome is Outcome.FAIL


def test_precedence_is_a_no_op_without_close_failures():
    result = _passing_result()
    apply_close_failure_precedence(result)
    assert result.failure_category is None
    assert result.outcome is Outcome.PASS


def test_precedence_is_idempotent():
    result = _passing_result()
    result.connection_closures = [{"connection": "observer", "closed": False}]
    apply_close_failure_precedence(result)
    first = result.failure_message
    apply_close_failure_precedence(result)
    assert result.failure_message == first


@pytest.mark.parametrize("count", [1, 2, 3])
def test_the_message_names_how_many_connections_leaked(count):
    result = _passing_result()
    result.connection_closures = [{"connection": f"c{i}", "closed": False} for i in range(count)]
    apply_close_failure_precedence(result)
    assert f"close {count} runner-owned connection(s)" in result.failure_message


def test_close_failures_reach_the_serialized_report():
    result = _passing_result()
    result.connection_closures = [{"connection": "observer", "closed": False}]
    payload = result.to_json()
    assert payload["connection_close_failures"] == result.close_failures
    assert payload["outcome"] == "FAIL"
