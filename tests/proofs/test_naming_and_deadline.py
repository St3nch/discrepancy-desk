"""Proof-database naming and hard client-side deadlines.

Reconciliation section 6: identifiers are runner-generated and deadlines are
mandatory on every wait. The deadline clock is injected so these tests never
sleep.
"""

from __future__ import annotations

import pytest

from tools.postgres_foundation_proofs.deadline import Deadline
from tools.postgres_foundation_proofs.errors import DeadlineExceeded
from tools.postgres_foundation_proofs.naming import (
    MAX_IDENTIFIER_LENGTH,
    PROOF_DATABASE_PREFIX,
    new_token,
    proof_database_name,
)


def test_generated_name_is_safe_and_prefixed():
    name = proof_database_name("a", "0123456789ab")
    assert name == f"{PROOF_DATABASE_PREFIX}_a_0123456789ab"
    assert len(name.encode()) <= MAX_IDENTIFIER_LENGTH


def test_names_are_unique_across_calls():
    names = {proof_database_name("a", new_token()) for _ in range(200)}
    assert len(names) == 200


@pytest.mark.parametrize("proof", ["a b", "a-b", "1a", "", "a;DROP DATABASE x", "a'"])
def test_unsafe_proof_key_is_refused_not_sanitized(proof):
    with pytest.raises(ValueError):
        proof_database_name(proof, "0123456789ab")


@pytest.mark.parametrize("token", ["", "XYZ", "abc-def", "abc def", "'"])
def test_non_hex_token_is_refused(token):
    with pytest.raises(ValueError):
        proof_database_name("a", token)


def test_overlong_name_is_refused():
    with pytest.raises(ValueError):
        proof_database_name("a", "0" * 80)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_deadline_reports_remaining_and_expiry():
    clock = FakeClock()
    deadline = Deadline(10.0, clock=clock)
    assert deadline.remaining() == 10.0
    assert not deadline.expired()
    clock.now = 9.5
    deadline.check("something")
    clock.now = 10.0
    assert deadline.expired()


def test_expired_deadline_fails_closed_with_context():
    clock = FakeClock()
    deadline = Deadline(5.0, clock=clock)
    clock.now = 5.1
    with pytest.raises(DeadlineExceeded) as excinfo:
        deadline.check("session B to register as waiting")
    assert "session B to register as waiting" in excinfo.value.message
    assert "5s exceeded" in excinfo.value.message


def test_non_positive_deadline_is_rejected():
    with pytest.raises(ValueError):
        Deadline(0)
