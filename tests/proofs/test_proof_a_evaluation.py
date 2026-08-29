"""Proof A assertion evaluation over recorded observations.

Reconciliation section 11: these tests must not simulate a live database and
label the simulation a passing physical proof. They exercise only the pure
decision function over recorded observation values. Physical PASS evidence
exists solely when the Steward later runs the reviewed runner through VedaOps.

The regression that matters most here is the tautology the Steward's
reconciliation removed: an observation set where B was never seen blocked must
FAIL even though A's ordinal is lower than B's, because ordering alone is
guaranteed by start order and proves nothing about the advisory lock.
"""

from __future__ import annotations

import pytest

from tests.proofs.observations import A_PID, B_PID, passing_proof_a_observations
from tools.postgres_foundation_proofs.proof_a import (
    LABEL_A,
    LABEL_B,
    LABEL_D,
    ProofAObservations,
    evaluate_proof_a,
)

passing_observations = passing_proof_a_observations


def failed_names(obs: ProofAObservations) -> set[str]:
    return {a.name for a in evaluate_proof_a(obs) if not a.passed}


def test_a_correct_run_passes_every_assertion():
    assert failed_names(passing_observations()) == set()


def test_evaluation_produces_the_full_assertion_set():
    names = {a.name for a in evaluate_proof_a(passing_observations())}
    assert names == {
        "observer_saw_A_holding_advisory_lock",
        "observer_saw_B_waiting_on_advisory_lock",
        "observer_saw_B_wait_event_type_Lock",
        "pg_blocking_pids_of_B_contains_A",
        "sequence_unadvanced_while_B_blocked",
        "A_ordinal_lower_than_B_ordinal",
        "rolled_back_ordinal_absent_from_table",
        "D_ordinal_strictly_greater_than_rolled_back_C_ordinal",
        "committed_table_holds_exactly_A_B_D",
    }


def test_ordering_alone_cannot_pass_the_proof():
    # The tautology guard. Ordinals are still 1 < 2, but no blocking was
    # observed, so the proof must fail.
    obs = passing_observations()
    obs.observer_lock_rows = []
    obs.blocking_pids = []
    failures = failed_names(obs)
    assert "A_ordinal_lower_than_B_ordinal" not in failures
    assert {
        "observer_saw_A_holding_advisory_lock",
        "observer_saw_B_waiting_on_advisory_lock",
        "observer_saw_B_wait_event_type_Lock",
        "pg_blocking_pids_of_B_contains_A",
    } <= failures


def test_b_lock_already_granted_fails():
    obs = passing_observations()
    obs.observer_lock_rows = [
        [A_PID, True, None, None, "idle in transaction"],
        [B_PID, True, None, None, "active"],
    ]
    assert "observer_saw_B_waiting_on_advisory_lock" in failed_names(obs)


def test_b_waiting_on_something_other_than_a_lock_fails():
    obs = passing_observations()
    obs.observer_lock_rows[1] = [B_PID, False, "Client", "ClientRead", "active"]
    assert "observer_saw_B_wait_event_type_Lock" in failed_names(obs)


def test_blocker_other_than_a_fails():
    obs = passing_observations()
    obs.blocking_pids = [999]
    assert "pg_blocking_pids_of_B_contains_A" in failed_names(obs)


def test_sequence_advancing_while_b_blocked_fails():
    # If the sequence moved while B was blocked, B allocated its ordinal
    # without holding the lock, which is exactly the FND-002 failure mode.
    obs = passing_observations()
    obs.sequence_last_value_while_b_blocked = 2
    assert "sequence_unadvanced_while_B_blocked" in failed_names(obs)


def test_sequence_never_observed_fails():
    obs = passing_observations()
    obs.sequence_last_value_while_b_blocked = None
    assert "sequence_unadvanced_while_B_blocked" in failed_names(obs)


def test_inverted_ordinals_fail():
    obs = passing_observations()
    obs.a_ordinal, obs.b_ordinal = 2, 1
    assert "A_ordinal_lower_than_B_ordinal" in failed_names(obs)


def test_rolled_back_ordinal_present_in_table_fails():
    obs = passing_observations()
    obs.committed_rows = [[1, LABEL_A], [2, LABEL_B], [3, "C-rolls-back"], [4, LABEL_D]]
    assert "rolled_back_ordinal_absent_from_table" in failed_names(obs)
    assert "committed_table_holds_exactly_A_B_D" in failed_names(obs)


def test_d_not_greater_than_c_fails():
    obs = passing_observations()
    obs.c_ordinal, obs.d_ordinal = 4, 3
    assert "D_ordinal_strictly_greater_than_rolled_back_C_ordinal" in failed_names(obs)


def test_gap_is_permitted_and_carries_no_meaning():
    # A larger gap between C and D is still a pass: sequence gaps have no
    # semantic meaning (schema sketch section 2).
    obs = passing_observations()
    obs.c_ordinal, obs.d_ordinal = 3, 97
    obs.committed_rows = [[1, LABEL_A], [2, LABEL_B], [97, LABEL_D]]
    assert failed_names(obs) == set()


@pytest.mark.parametrize("missing", ["a_ordinal", "b_ordinal", "c_ordinal", "d_ordinal"])
def test_missing_ordinal_fails_closed(missing):
    obs = passing_observations()
    setattr(obs, missing, None)
    assert failed_names(obs)
