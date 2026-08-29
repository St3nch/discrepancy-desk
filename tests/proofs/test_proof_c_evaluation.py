"""Proof C assertion evaluation over recorded observations.

Reconciliation section 11: no live database is simulated.

The regression guard that matters here is reconciliation section 4. The harness
prose listed the forward result as ``O4, D2, D20``, but its own ORDER BY returns
the decision rows first. A run that produced the harness's prose order must FAIL
the ordered assertion; silently downgrading to set-equality would be exactly the
"reinterpret failed assertions into a passing outcome" the ticket forbids.
"""

from __future__ import annotations

import copy

import pytest

from tools.postgres_foundation_proofs.proof_c import (
    ADVERSARIES,
    EXPECTED_FORWARD_ROWS,
    EXPECTED_REVERSE_ROWS,
    ProofCObservations,
    evaluate_proof_c,
)


def passing_observations() -> ProofCObservations:
    return ProofCObservations(
        forward_rows=copy.deepcopy(EXPECTED_FORWARD_ROWS),
        reverse_rows=copy.deepcopy(EXPECTED_REVERSE_ROWS),
        adversary_results={
            label: {
                "rejected": True,
                "sqlstate": "23503",
                "error_category": "rejected_by_postgresql",
            }
            for label, _statement, _savepoint in ADVERSARIES
        },
    )


def failed_names(obs: ProofCObservations) -> set[str]:
    return {a.name for a in evaluate_proof_c(obs) if not a.passed}


def test_a_correct_run_passes_every_assertion():
    assert failed_names(passing_observations()) == set()


def test_expected_forward_order_is_the_corrected_one():
    # decision sorts before observation, so D2 and D20 precede O4.
    assert EXPECTED_FORWARD_ROWS[0][:2] == ["decision", "D2"]
    assert EXPECTED_FORWARD_ROWS[1][:2] == ["decision", "D20"]
    assert EXPECTED_FORWARD_ROWS[2][:2] == ["observation", "O4"]


def test_harness_prose_order_fails_the_ordered_assertion():
    obs = passing_observations()
    obs.forward_rows = [
        ["observation", "O4", "supports"],
        ["decision", "D2", "identity_resolution"],
        ["decision", "D20", "claim_posture"],
    ]
    failures = failed_names(obs)
    assert "forward_traversal_exact_ordered_rows" in failures
    # The set is unchanged, so only the ordered assertion may fail. That is the
    # distinction the reconciliation drew.
    assert "forward_traversal_exact_set" not in failures


def test_missing_forward_edge_fails_both_ordered_and_set_assertions():
    obs = passing_observations()
    obs.forward_rows = obs.forward_rows[:2]
    failures = failed_names(obs)
    assert "forward_traversal_exact_ordered_rows" in failures
    assert "forward_traversal_exact_set" in failures


@pytest.mark.parametrize(
    ("key", "name"),
    [
        ("decision:D2", "reverse_traversal_decision_D2"),
        ("decision:D20", "reverse_traversal_decision_D20"),
        ("observation:O4", "reverse_traversal_observation_O4"),
    ],
)
def test_each_reverse_path_is_asserted(key, name):
    obs = passing_observations()
    obs.reverse_rows[key] = []
    assert name in failed_names(obs)


def test_forward_and_reverse_must_agree():
    obs = passing_observations()
    obs.reverse_rows["decision:D2"] = [["claim_version", "C7V1", "claim_posture"]]
    failures = failed_names(obs)
    assert "forward_and_reverse_traversals_agree" in failures


def test_reverse_pointing_at_another_dependent_breaks_agreement():
    obs = passing_observations()
    obs.reverse_rows["decision:D2"] = [["claim_version", "C9V1", "identity_resolution"]]
    assert "forward_and_reverse_traversals_agree" in failed_names(obs)


@pytest.mark.parametrize("label", [a[0] for a in ADVERSARIES])
def test_an_adversary_that_succeeds_is_a_proof_failure(label):
    obs = passing_observations()
    obs.adversary_results[label] = {
        "rejected": False,
        "sqlstate": None,
        "error_category": "unexpected_success",
    }
    assert f"{label}_rejected_by_postgresql" in failed_names(obs)


def test_all_three_adversaries_are_required():
    labels = {a[0] for a in ADVERSARIES}
    assert labels == {
        "C.adversary.nonexistent_fk",
        "C.adversary.invented_relation",
        "C.adversary.view_insert",
    }


def test_unrecorded_adversary_fails_closed():
    obs = passing_observations()
    obs.adversary_results = {}
    failures = failed_names(obs)
    for label, _statement, _savepoint in ADVERSARIES:
        assert f"{label}_rejected_by_postgresql" in failures


def test_empty_observations_fail_everything():
    assert len(failed_names(ProofCObservations())) >= 7
