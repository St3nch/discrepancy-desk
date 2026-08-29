"""Proof B -- identity triangle, conflict, repair, historical boundary.

Harness section 3 as amended by reconciliation section 3, which binds the
boundary as a SQL parameter and pins the connected-component projection the
harness described only in prose.

The three boundaries are the whole point: B=14 shows the pre-correction
cluster, B=16 shows that a bare ``distinct`` Decision produces a visible
CONFLICTED state rather than an arbitrary graph cut, and B=21 shows explicit
supersession repairing the graph. The final replay proves D9's existence did not
rewrite the historical B=14 answer.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

import psycopg

from . import sql
from .evidence import Assertion, ProofResult, assert_that
from .execution import StepRecorder, run_setup

BOUNDARIES = (14, 16, 21)

#: Reconciliation section 3 states these expectations directly.
EXPECTED_BOUNDARY_ROWS: dict[int, list[list[str]]] = {
    14: [
        ["operative", "D1", "same_identity", "E17", "E42"],
        ["operative", "D2", "same_identity", "E42", "E99"],
        ["operative", "D3", "same_identity", "E17", "E99"],
    ],
    16: [
        ["conflict", "D8", "CONFLICTED", "E17", "E42"],
        ["operative", "D1", "same_identity", "E17", "E42"],
        ["operative", "D2", "same_identity", "E42", "E99"],
        ["operative", "D3", "same_identity", "E17", "E99"],
        ["operative", "D8", "distinct", "E17", "E42"],
    ],
    21: [
        ["operative", "D2", "same_identity", "E42", "E99"],
        ["operative", "D9", "distinct", "E17", "E42"],
    ],
}

#: Reconciliation section 3, "Expected undirected reachable pairs".
EXPECTED_CLUSTER_PAIRS: dict[int, list[list[str]]] = {
    14: [["E17", "E42"], ["E17", "E99"], ["E42", "E99"]],
    16: [["E17", "E42"], ["E17", "E99"], ["E42", "E99"]],
    21: [["E42", "E99"]],
}


@dataclass
class ProofBObservations:
    boundary_rows: dict[int, list[Any]] = field(default_factory=dict)
    cluster_pairs: dict[int, list[Any]] = field(default_factory=dict)
    replay_boundary_rows_b14: list[Any] = field(default_factory=list)
    replay_cluster_pairs_b14: list[Any] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "boundary_rows": {str(k): v for k, v in self.boundary_rows.items()},
            "cluster_pairs": {str(k): v for k, v in self.cluster_pairs.items()},
            "replay_boundary_rows_b14": self.replay_boundary_rows_b14,
            "replay_cluster_pairs_b14": self.replay_cluster_pairs_b14,
        }


def evaluate_proof_b(obs: ProofBObservations) -> list[Assertion]:
    """Decide Proof B from recorded observations. Pure and database-free."""
    assertions: list[Assertion] = []

    for boundary in BOUNDARIES:
        assertions.append(
            assert_that(
                f"boundary_{boundary}_operative_and_conflict_rows",
                EXPECTED_BOUNDARY_ROWS[boundary],
                obs.boundary_rows.get(boundary),
            )
        )
        assertions.append(
            assert_that(
                f"boundary_{boundary}_connected_component_pairs",
                EXPECTED_CLUSTER_PAIRS[boundary],
                obs.cluster_pairs.get(boundary),
            )
        )

    # B=16 must expose the contradiction rather than resolve it by cutting an
    # edge. Both facts have to hold at once: the positive component survives
    # intact AND D8 is reported CONFLICTED.
    rows_16 = obs.boundary_rows.get(16) or []
    assertions.append(
        assert_that(
            "boundary_16_reports_D8_conflicted_without_cutting_an_edge",
            True,
            (
                ["conflict", "D8", "CONFLICTED", "E17", "E42"] in rows_16
                and obs.cluster_pairs.get(16) == EXPECTED_CLUSTER_PAIRS[14]
            ),
        )
    )

    # B=21: E17 is outside the surviving positive component and no conflict is
    # reported, because D9 explicitly superseded D1, D3 and D8.
    rows_21 = obs.boundary_rows.get(21) or []
    assertions.append(
        assert_that(
            "boundary_21_repaired_graph_reports_no_conflict",
            [],
            [row for row in rows_21 if row and row[0] == "conflict"],
        )
    )
    assertions.append(
        assert_that(
            "boundary_21_E17_outside_surviving_positive_component",
            True,
            all("E17" not in pair for pair in (obs.cluster_pairs.get(21) or [])),
        )
    )

    # The later existence of D9 must not alter the reconstructed B=14 answer.
    assertions.append(
        assert_that(
            "historical_b14_answer_stable_after_D9_exists",
            obs.boundary_rows.get(14),
            obs.replay_boundary_rows_b14,
        )
    )
    assertions.append(
        assert_that(
            "historical_b14_cluster_stable_after_D9_exists",
            obs.cluster_pairs.get(14),
            obs.replay_cluster_pairs_b14,
        )
    )
    return assertions


def run_proof_b(
    connect_fn: Any,
    database: str,
    result: ProofResult,
) -> ProofBObservations:
    """Execute Proof B."""
    recorder = StepRecorder(result)
    obs = ProofBObservations()

    conn: psycopg.Connection | None = None
    try:
        conn = connect_fn(database, "fnd_pg01_proof_b", False)
        run_setup(recorder, conn, sql.PROOF_B_SETUP, "B")

        for boundary in BOUNDARIES:
            params = {"boundary": boundary}
            obs.boundary_rows[boundary] = [
                list(row)
                for row in recorder.run(
                    conn,
                    f"B.boundary_{boundary}.operative_conflict",
                    sql.PROOF_B_BOUNDARY_QUERY,
                    params,
                )
            ]
            obs.cluster_pairs[boundary] = [
                list(row)
                for row in recorder.run(
                    conn,
                    f"B.boundary_{boundary}.connected_components",
                    sql.PROOF_B_CLUSTER_QUERY,
                    params,
                )
            ]

        # Replay B=14 last, with D9 present the whole time, to show the
        # historical answer is reconstructed rather than overwritten.
        params = {"boundary": 14}
        obs.replay_boundary_rows_b14 = [
            list(row)
            for row in recorder.run(
                conn,
                "B.replay_boundary_14.operative_conflict",
                sql.PROOF_B_BOUNDARY_QUERY,
                params,
            )
        ]
        obs.replay_cluster_pairs_b14 = [
            list(row)
            for row in recorder.run(
                conn,
                "B.replay_boundary_14.connected_components",
                sql.PROOF_B_CLUSTER_QUERY,
                params,
            )
        ]
        conn.commit()
        return obs
    finally:
        if conn is not None:
            # A close failure must not mask the real proof result.
            with contextlib.suppress(Exception):
                conn.close()
