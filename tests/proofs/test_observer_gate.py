"""Proof A's release gate for Session A's commit.

Reconciliation section 2.1: "Only after all observer assertions pass does the
runner commit A." Committing on partial evidence -- B registered as waiting but
``pg_blocking_pids`` not yet naming A, say -- would gather the decisive evidence
after the very transaction it was supposed to constrain.

These tests exercise the pure condition function the gate and the recorded
verdict both use. No database is involved.
"""

from __future__ import annotations

import pytest

from tests.proofs.observations import A_PID, B_PID, passing_proof_a_observations
from tools.postgres_foundation_proofs.proof_a import (
    ProofAObservations,
    observer_conditions,
    observer_expectations,
)

passing_observations = passing_proof_a_observations

CONDITION_NAMES = (
    "observer_saw_A_holding_advisory_lock",
    "observer_saw_B_waiting_on_advisory_lock",
    "observer_saw_B_wait_event_type_Lock",
    "pg_blocking_pids_of_B_contains_A",
    "sequence_unadvanced_while_B_blocked",
)


def test_complete_evidence_opens_the_gate():
    conditions = observer_conditions(passing_observations())
    assert set(conditions) == set(CONDITION_NAMES)
    assert all(conditions.values())


def test_no_observation_at_all_keeps_the_gate_shut():
    assert not any(observer_conditions(ProofAObservations()).values())


def test_gate_and_verdict_derive_from_one_source():
    # The release gate and the reported assertions must not drift apart.
    obs = passing_observations()
    assert set(observer_expectations(obs)) == set(observer_conditions(obs))


def test_a_lock_not_yet_granted_keeps_the_gate_shut():
    obs = passing_observations()
    obs.observer_lock_rows = [
        [A_PID, False, "Lock", "advisory", "active"],
        [B_PID, False, "Lock", "advisory", "active"],
    ]
    conditions = observer_conditions(obs)
    assert conditions["observer_saw_A_holding_advisory_lock"] is False
    assert not all(conditions.values())


def test_b_row_absent_keeps_the_gate_shut():
    # B has not registered its lock request yet: the gate must keep waiting.
    obs = passing_observations()
    obs.observer_lock_rows = [[A_PID, True, None, None, "idle in transaction"]]
    conditions = observer_conditions(obs)
    assert conditions["observer_saw_B_waiting_on_advisory_lock"] is False
    assert conditions["observer_saw_B_wait_event_type_Lock"] is False


def test_wait_event_not_yet_lock_keeps_the_gate_shut():
    obs = passing_observations()
    obs.observer_lock_rows[1] = [B_PID, False, None, None, "active"]
    assert observer_conditions(obs)["observer_saw_B_wait_event_type_Lock"] is False


def test_blocking_pids_not_yet_naming_a_keeps_the_gate_shut():
    # The precise partial state the old code would have committed A on.
    obs = passing_observations()
    obs.blocking_pids = []
    conditions = observer_conditions(obs)
    assert conditions["observer_saw_A_holding_advisory_lock"] is True
    assert conditions["observer_saw_B_waiting_on_advisory_lock"] is True
    assert conditions["pg_blocking_pids_of_B_contains_A"] is False
    assert not all(conditions.values())


def test_sequence_already_advanced_keeps_the_gate_shut():
    obs = passing_observations()
    obs.sequence_last_value_while_b_blocked = obs.a_ordinal + 1
    assert observer_conditions(obs)["sequence_unadvanced_while_B_blocked"] is False


def test_sequence_not_yet_read_keeps_the_gate_shut():
    obs = passing_observations()
    obs.sequence_last_value_while_b_blocked = None
    assert observer_conditions(obs)["sequence_unadvanced_while_B_blocked"] is False


@pytest.mark.parametrize("name", CONDITION_NAMES)
def test_every_condition_is_individually_load_bearing(name):
    """Falsifying any single condition must close the gate."""
    obs = passing_observations()
    breakers = {
        "observer_saw_A_holding_advisory_lock": lambda o: o.observer_lock_rows.__setitem__(
            0, [A_PID, False, "Lock", "advisory", "active"]
        ),
        "observer_saw_B_waiting_on_advisory_lock": lambda o: o.observer_lock_rows.__setitem__(
            1, [B_PID, True, None, None, "active"]
        ),
        "observer_saw_B_wait_event_type_Lock": lambda o: o.observer_lock_rows.__setitem__(
            1, [B_PID, False, "Client", "ClientRead", "active"]
        ),
        "pg_blocking_pids_of_B_contains_A": lambda o: setattr(o, "blocking_pids", [9999]),
        "sequence_unadvanced_while_B_blocked": lambda o: setattr(
            o, "sequence_last_value_while_b_blocked", 42
        ),
    }
    breakers[name](obs)
    conditions = observer_conditions(obs)
    assert conditions[name] is False
    assert not all(conditions.values())
