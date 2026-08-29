"""Evidence bounds and proof-outcome logic.

Reconciliation section 6 forbids silent truncation of the runner's own
evidence, so exceeding a bound is a failure rather than a shortened record.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tools.postgres_foundation_proofs.errors import ErrorCategory, ProofRunError
from tools.postgres_foundation_proofs.evidence import (
    MAX_ROWS_PER_STEP,
    MAX_VALUE_CHARS,
    Outcome,
    ProofResult,
    SqlStep,
    assert_that,
    bounded_rows,
    jsonable,
)


def test_ordinary_rows_pass_through():
    assert bounded_rows([(1, "a"), (2, "b")], "label") == [[1, "a"], [2, "b"]]


def test_exceeding_the_row_bound_fails_rather_than_truncating():
    rows = [(i,) for i in range(MAX_ROWS_PER_STEP + 1)]
    with pytest.raises(ProofRunError) as excinfo:
        bounded_rows(rows, "greedy.step")
    assert excinfo.value.category is ErrorCategory.EVIDENCE_INCOMPLETE
    assert "rather than truncating evidence" in excinfo.value.message


def test_exceeding_the_value_bound_fails_rather_than_truncating():
    with pytest.raises(ProofRunError) as excinfo:
        jsonable("x" * (MAX_VALUE_CHARS + 1))
    assert excinfo.value.category is ErrorCategory.EVIDENCE_INCOMPLETE


def test_driver_types_render_json_safely():
    moment = dt.datetime(2026, 8, 29, 12, 0, tzinfo=dt.UTC)
    assert jsonable(moment) == "2026-08-29T12:00:00+00:00"
    assert jsonable(b"\x00\xff") == "00ff"
    assert jsonable([1, (2, 3)]) == [1, [2, 3]]
    assert jsonable(None) is None


def test_a_proof_with_no_assertions_cannot_pass():
    # Closes the "skipped proof becomes PASS" fail-open path.
    assert ProofResult(proof="A", title="t").outcome is Outcome.FAIL


def test_a_proof_with_only_passing_assertions_passes():
    result = ProofResult(proof="A", title="t")
    result.assertions.append(assert_that("x", 1, 1))
    assert result.outcome is Outcome.PASS


def test_a_failed_assertion_fails_the_proof():
    result = ProofResult(proof="A", title="t")
    result.assertions.append(assert_that("x", 1, 2))
    assert result.outcome is Outcome.FAIL


def test_a_recorded_failure_category_fails_the_proof():
    result = ProofResult(proof="A", title="t")
    result.assertions.append(assert_that("x", 1, 1))
    result.failure_category = str(ErrorCategory.DEADLINE_EXCEEDED)
    assert result.outcome is Outcome.FAIL


def test_an_adversary_that_unexpectedly_succeeds_fails_the_proof():
    result = ProofResult(proof="C", title="t")
    result.assertions.append(assert_that("x", 1, 1))
    result.steps.append(
        SqlStep(label="adv", sql="INSERT ...", succeeded=True, expected_failure=True)
    )
    assert result.outcome is Outcome.FAIL
    assert [s.label for s in result.unexpected_steps] == ["adv"]


def test_a_normal_step_that_unexpectedly_fails_fails_the_proof():
    result = ProofResult(proof="B", title="t")
    result.assertions.append(assert_that("x", 1, 1))
    result.steps.append(SqlStep(label="q", sql="SELECT 1", succeeded=False, expected_failure=False))
    assert result.outcome is Outcome.FAIL


def test_an_adversary_that_is_rejected_is_expected():
    step = SqlStep(label="adv", sql="INSERT ...", succeeded=False, expected_failure=True)
    assert step.unexpected is False


def test_serialized_proof_carries_the_decision_trail():
    result = ProofResult(proof="A", title="t")
    result.assertions.append(assert_that("x", 1, 2))
    payload = result.to_json()
    assert payload["outcome"] == "FAIL"
    assert payload["failed_assertion_names"] == ["x"]
    assert payload["evidence_class"] == "runner_proved"
