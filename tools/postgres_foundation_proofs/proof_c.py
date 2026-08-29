"""Proof C -- typed forward/reverse provenance.

Harness section 4 as corrected by reconciliation section 4.

Two corrections matter. First, the harness's prose listed the forward result as
``O4, D2, D20``, but its own ``ORDER BY source_type, source_id, relation_kind``
returns the decision rows first, because 'decision' sorts before 'observation'.
The exact ordered result below is the corrected one, and it is asserted as both
an ordered sequence and a set. Second, the harness asserted in prose that the
UNION ALL view is a read-only traversal surface but never tested it, so a third
adversary attempts a mutation through the view and requires rejection.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

import psycopg

from . import sql
from .evidence import Assertion, ProofResult, SqlStep, assert_that
from .execution import StepRecorder, run_setup

DEPENDENT_CLAIM_VERSION = "C7V1"

#: Reconciliation section 4: "The exact ordered rows are therefore ..."
EXPECTED_FORWARD_ROWS: list[list[str]] = [
    ["decision", "D2", "identity_resolution"],
    ["decision", "D20", "claim_posture"],
    ["observation", "O4", "supports"],
]

#: Harness section 4.2 requires the other reverse paths as well as D2.
REVERSE_TARGETS: tuple[tuple[str, str], ...] = (
    ("decision", "D2"),
    ("decision", "D20"),
    ("observation", "O4"),
)

EXPECTED_REVERSE_ROWS: dict[str, list[list[str]]] = {
    "decision:D2": [["claim_version", "C7V1", "identity_resolution"]],
    "decision:D20": [["claim_version", "C7V1", "claim_posture"]],
    "observation:O4": [["claim_version", "C7V1", "supports"]],
}

ADVERSARIES: tuple[tuple[str, str, str], ...] = (
    ("C.adversary.nonexistent_fk", sql.PROOF_C_ADVERSARY_NONEXISTENT_FK, "bad_fk"),
    ("C.adversary.invented_relation", sql.PROOF_C_ADVERSARY_INVENTED_RELATION, "bad_kind"),
    ("C.adversary.view_insert", sql.PROOF_C_ADVERSARY_VIEW_INSERT, "bad_view_insert"),
)


@dataclass
class ProofCObservations:
    forward_rows: list[Any] = field(default_factory=list)
    reverse_rows: dict[str, list[Any]] = field(default_factory=dict)
    adversary_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "forward_rows": self.forward_rows,
            "reverse_rows": self.reverse_rows,
            "adversary_results": self.adversary_results,
        }


def _forward_edge_set(forward_rows: list[Any]) -> set[tuple[str, str, str]]:
    return {(row[0], row[1], row[2]) for row in forward_rows}


def _reverse_edge_set(reverse_rows: dict[str, list[Any]]) -> set[tuple[str, str, str]]:
    """Rebuild the same edges from the reverse direction.

    Each reverse key is ``<source_type>:<source_id>``, and each returned row is
    ``(dependent_type, dependent_id, relation_kind)``. Projecting both back into
    a common triple lets forward and reverse be compared directly, which is the
    ticket's projection-completeness requirement.
    """
    edges: set[tuple[str, str, str]] = set()
    for key, rows in reverse_rows.items():
        source_type, source_id = key.split(":", 1)
        for row in rows:
            if row[0] == "claim_version" and row[1] == DEPENDENT_CLAIM_VERSION:
                edges.add((source_type, source_id, row[2]))
    return edges


def evaluate_proof_c(obs: ProofCObservations) -> list[Assertion]:
    """Decide Proof C from recorded observations. Pure and database-free."""
    assertions = [
        assert_that(
            "forward_traversal_exact_ordered_rows",
            EXPECTED_FORWARD_ROWS,
            [list(row) for row in obs.forward_rows],
        ),
        assert_that(
            "forward_traversal_exact_set",
            {tuple(row) for row in EXPECTED_FORWARD_ROWS},
            _forward_edge_set(obs.forward_rows),
        ),
    ]

    for source_type, source_id in REVERSE_TARGETS:
        key = f"{source_type}:{source_id}"
        assertions.append(
            assert_that(
                f"reverse_traversal_{source_type}_{source_id}",
                EXPECTED_REVERSE_ROWS[key],
                [list(row) for row in obs.reverse_rows.get(key, [])],
            )
        )

    assertions.append(
        assert_that(
            "forward_and_reverse_traversals_agree",
            _forward_edge_set(obs.forward_rows),
            _reverse_edge_set(obs.reverse_rows),
        )
    )

    for label, _statement, _savepoint in ADVERSARIES:
        recorded = obs.adversary_results.get(label, {})
        assertions.append(
            assert_that(
                f"{label}_rejected_by_postgresql",
                True,
                recorded.get("rejected"),
            )
        )
    return assertions


def run_proof_c(
    connect_fn: Any,
    database: str,
    result: ProofResult,
) -> ProofCObservations:
    """Execute Proof C."""
    recorder = StepRecorder(result)
    obs = ProofCObservations()

    conn: psycopg.Connection | None = None
    try:
        conn = connect_fn(database, "fnd_pg01_proof_c", False)
        run_setup(recorder, conn, sql.PROOF_C_SETUP, "C")

        obs.forward_rows = [
            list(row)
            for row in recorder.run(
                conn,
                "C.forward.claim_version_C7V1",
                sql.PROOF_C_FORWARD,
                {"dependent_id": DEPENDENT_CLAIM_VERSION},
            )
        ]

        for source_type, source_id in REVERSE_TARGETS:
            key = f"{source_type}:{source_id}"
            obs.reverse_rows[key] = [
                list(row)
                for row in recorder.run(
                    conn,
                    f"C.reverse.{source_type}_{source_id}",
                    sql.PROOF_C_REVERSE,
                    {"source_type": source_type, "source_id": source_id},
                )
            ]

        for label, statement, savepoint in ADVERSARIES:
            step: SqlStep = recorder.run_expecting_failure(conn, label, statement, savepoint)
            obs.adversary_results[label] = {
                "rejected": not step.succeeded,
                "sqlstate": step.sqlstate,
                "error_category": step.error_category,
            }

        conn.commit()
        return obs
    finally:
        if conn is not None:
            # A close failure must not mask the real proof result.
            with contextlib.suppress(Exception):
                conn.close()
