"""Shared recorded-observation builders for the Proof A tests.

Kept out of the test modules so the evaluation tests and the release-gate tests
assert against one definition of "what a correct run looks like" rather than two
that can drift apart.

These are recorded values, not a database simulation. Reconciliation section 11
forbids simulating a live database and calling the result a physical proof.
"""

from __future__ import annotations

from tools.postgres_foundation_proofs.proof_a import (
    LABEL_A,
    LABEL_B,
    LABEL_D,
    ProofAObservations,
)

A_PID = 101
B_PID = 202


def passing_proof_a_observations() -> ProofAObservations:
    """The observation set a correct PostgreSQL 18 run should produce."""
    return ProofAObservations(
        a_pid=A_PID,
        b_pid=B_PID,
        a_ordinal=1,
        b_ordinal=2,
        c_ordinal=3,
        d_ordinal=4,
        observer_lock_rows=[
            [A_PID, True, None, None, "idle in transaction"],
            [B_PID, False, "Lock", "advisory", "active"],
        ],
        observer_poll_count=3,
        blocking_pids=[A_PID],
        sequence_last_value_while_b_blocked=1,
        b_before_lock="2026-08-29T12:00:00+00:00",
        b_after_lock="2026-08-29T12:00:01+00:00",
        committed_rows=[[1, LABEL_A], [2, LABEL_B], [4, LABEL_D]],
    )
