"""Proof B assertion evaluation over recorded observations.

Reconciliation section 11: no live database is simulated and no simulation is
labelled a passing physical proof.

The failure modes under test are the ones the harness cares about: a silent
graph cut at B=16, a conflict hidden by choosing an edge implicitly, and a
current repair that destroys the historical B=14 answer.
"""

from __future__ import annotations

import copy

from tools.postgres_foundation_proofs.proof_b import (
    EXPECTED_BOUNDARY_ROWS,
    EXPECTED_CLUSTER_PAIRS,
    ProofBObservations,
    evaluate_proof_b,
)


def passing_observations() -> ProofBObservations:
    return ProofBObservations(
        boundary_rows=copy.deepcopy(EXPECTED_BOUNDARY_ROWS),
        cluster_pairs=copy.deepcopy(EXPECTED_CLUSTER_PAIRS),
        replay_boundary_rows_b14=copy.deepcopy(EXPECTED_BOUNDARY_ROWS[14]),
        replay_cluster_pairs_b14=copy.deepcopy(EXPECTED_CLUSTER_PAIRS[14]),
    )


def failed_names(obs: ProofBObservations) -> set[str]:
    return {a.name for a in evaluate_proof_b(obs) if not a.passed}


def test_a_correct_run_passes_every_assertion():
    assert failed_names(passing_observations()) == set()


def test_all_three_boundaries_are_asserted():
    names = {a.name for a in evaluate_proof_b(passing_observations())}
    for boundary in (14, 16, 21):
        assert f"boundary_{boundary}_operative_and_conflict_rows" in names
        assert f"boundary_{boundary}_connected_component_pairs" in names


def test_b14_reconstructs_the_pre_correction_cluster():
    obs = passing_observations()
    assert obs.cluster_pairs[14] == [["E17", "E42"], ["E17", "E99"], ["E42", "E99"]]
    assert failed_names(obs) == set()


def test_missing_conflict_at_b16_fails():
    # D8 silently overriding D1/D2/D3 is the headline failure mode.
    obs = passing_observations()
    obs.boundary_rows[16] = [r for r in obs.boundary_rows[16] if r[0] != "conflict"]
    failures = failed_names(obs)
    assert "boundary_16_operative_and_conflict_rows" in failures
    assert "boundary_16_reports_D8_conflicted_without_cutting_an_edge" in failures


def test_arbitrary_graph_cut_at_b16_fails():
    # Resolving the contradiction by dropping a positive edge is forbidden.
    obs = passing_observations()
    obs.cluster_pairs[16] = [["E42", "E99"]]
    failures = failed_names(obs)
    assert "boundary_16_connected_component_pairs" in failures
    assert "boundary_16_reports_D8_conflicted_without_cutting_an_edge" in failures


def test_conflict_surviving_the_repair_at_b21_fails():
    obs = passing_observations()
    obs.boundary_rows[21] = [
        ["conflict", "D9", "CONFLICTED", "E17", "E42"],
        *obs.boundary_rows[21],
    ]
    failures = failed_names(obs)
    assert "boundary_21_repaired_graph_reports_no_conflict" in failures


def test_e17_still_clustered_after_repair_fails():
    obs = passing_observations()
    obs.cluster_pairs[21] = [["E17", "E42"], ["E42", "E99"]]
    failures = failed_names(obs)
    assert "boundary_21_E17_outside_surviving_positive_component" in failures
    assert "boundary_21_connected_component_pairs" in failures


def test_repair_destroying_the_historical_answer_fails():
    # If D9's existence rewrote history, B=14 would no longer reconstruct the
    # original cluster. That is an explicit harness FAIL condition.
    obs = passing_observations()
    obs.replay_boundary_rows_b14 = copy.deepcopy(EXPECTED_BOUNDARY_ROWS[21])
    obs.replay_cluster_pairs_b14 = copy.deepcopy(EXPECTED_CLUSTER_PAIRS[21])
    failures = failed_names(obs)
    assert "historical_b14_answer_stable_after_D9_exists" in failures
    assert "historical_b14_cluster_stable_after_D9_exists" in failures


def test_row_order_is_part_of_the_assertion():
    obs = passing_observations()
    obs.boundary_rows[14] = list(reversed(obs.boundary_rows[14]))
    assert "boundary_14_operative_and_conflict_rows" in failed_names(obs)


def test_missing_boundary_results_fail_closed():
    obs = passing_observations()
    obs.boundary_rows.pop(21)
    obs.cluster_pairs.pop(21)
    failures = failed_names(obs)
    assert "boundary_21_operative_and_conflict_rows" in failures
    assert "boundary_21_connected_component_pairs" in failures


def test_empty_observations_fail_everything():
    assert len(failed_names(ProofBObservations())) >= 8
