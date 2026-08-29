"""The per-proof preflight probe is a runner-owned connection too.

Reconciliation section 5 makes ``DROP DATABASE ... WITH (FORCE)`` a backstop
rather than a substitute for closing owned connections. The probe opens against
the temporary proof database exactly as the proof sessions do, so a probe that
cannot be closed is the same cleanup debt and must be visible as
``connection_close_failed`` -- not swallowed, and not blurred into a generic
internal error.

These tests drive the real orchestration path with fake connections. No
PostgreSQL is involved, and nothing here simulates a passing physical proof.
"""

from __future__ import annotations

from typing import Any

import pytest

from tools.postgres_foundation_proofs import runner
from tools.postgres_foundation_proofs.databases import ProofDatabaseRegistry
from tools.postgres_foundation_proofs.dsn import parse_dsn
from tools.postgres_foundation_proofs.errors import ErrorCategory, ProofRunError
from tools.postgres_foundation_proofs.evidence import Outcome, assert_that

DSN = parse_dsn("postgresql://vedaops:NOT_A_REAL_PASSWORD@127.0.0.1:49183/vedaops")


class FakeConnection:
    def __init__(self, close_error: Exception | None = None) -> None:
        self.close_error = close_error
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        if self.close_error is not None:
            raise self.close_error


class FakeObservations:
    def to_json(self) -> dict[str, Any]:
        return {"recorded": True}


def drive_proof(
    monkeypatch: pytest.MonkeyPatch,
    *,
    probe_close_error: Exception | None = None,
    preflight_error: Exception | None = None,
):
    """Run ``_run_one_proof`` against fakes and report what happened."""
    probe = FakeConnection(probe_close_error)
    proof_ran: list[str] = []
    dropped: list[str] = []

    monkeypatch.setattr(runner, "connect", lambda _dsn, **_kw: probe)
    monkeypatch.setattr(runner, "create_proof_database", lambda _conn, _name: None)
    monkeypatch.setattr(runner, "assert_database_empty", lambda _conn, _name: [])

    def fake_capture(_conn, *, context):
        if preflight_error is not None:
            raise preflight_error
        return {"context": context}

    monkeypatch.setattr(runner.preflight, "capture_preflight", fake_capture)

    def fake_run(_connect_fn, database, _result):
        proof_ran.append(database)
        return FakeObservations()

    result = runner._run_one_proof(
        "A",
        "admission ordering under concurrency",
        fake_run,
        lambda _obs: [assert_that("x", 1, 1)],
        DSN,
        FakeConnection(),
        ProofDatabaseRegistry(dropped.append),
    )
    return result, probe, proof_ran, dropped


def test_a_successful_probe_close_is_recorded_and_the_proof_runs(monkeypatch):
    result, probe, proof_ran, dropped = drive_proof(monkeypatch)

    assert probe.close_attempts == 1
    assert result.connection_closures == [{"connection": "preflight_probe", "closed": True}]
    assert result.close_failures == []
    assert proof_ran, "the proof should run when setup is clean"
    assert result.outcome is Outcome.PASS
    assert dropped == [result.database]


def test_a_failed_probe_close_is_visible_cleanup_evidence(monkeypatch):
    result, probe, _proof_ran, _dropped = drive_proof(
        monkeypatch, probe_close_error=RuntimeError("boom")
    )

    assert probe.close_attempts == 1
    assert result.close_failures
    assert result.close_failures[0]["connection"] == "preflight_probe"
    assert result.close_failures[0]["error_category"] == str(ErrorCategory.CONNECTION_CLOSE_FAILED)


def test_a_failed_probe_close_is_not_hidden_as_an_internal_error(monkeypatch):
    result, _probe, _proof_ran, _dropped = drive_proof(
        monkeypatch, probe_close_error=RuntimeError("boom")
    )

    assert result.failure_category == str(ErrorCategory.CONNECTION_CLOSE_FAILED)
    assert result.failure_category != str(ErrorCategory.INTERNAL_ERROR)
    assert "preflight probe" in result.failure_message


def test_a_failed_probe_close_forces_a_non_zero_outcome(monkeypatch):
    result, _probe, _proof_ran, _dropped = drive_proof(
        monkeypatch, probe_close_error=RuntimeError("boom")
    )
    assert result.outcome is Outcome.FAIL


def test_the_proof_does_not_run_when_the_probe_could_not_be_closed(monkeypatch):
    # Setup is not clean, so the substantive proof must not proceed as though
    # it were.
    _result, _probe, proof_ran, _dropped = drive_proof(
        monkeypatch, probe_close_error=RuntimeError("boom")
    )
    assert proof_ran == []


def test_force_backstop_still_drops_the_database_after_a_probe_close_failure(monkeypatch):
    result, _probe, _proof_ran, dropped = drive_proof(
        monkeypatch, probe_close_error=RuntimeError("boom")
    )
    assert dropped == [result.database]
    assert result.teardown["dropped"] is True


def test_a_preflight_failure_keeps_primary_precedence_over_a_probe_close_failure(monkeypatch):
    # Both go wrong at once: the version gate rejects the server AND the probe
    # cannot be closed. The original cause must stay the reported one.
    result, _probe, proof_ran, dropped = drive_proof(
        monkeypatch,
        preflight_error=ProofRunError(
            ErrorCategory.VERSION_GATE_FAILED, "connected server reports numeric major 17"
        ),
        probe_close_error=RuntimeError("boom"),
    )

    assert result.failure_category == str(ErrorCategory.VERSION_GATE_FAILED)
    assert "numeric major 17" in result.failure_message
    # The close failure is still visible alongside it.
    assert result.close_failures
    assert result.outcome is Outcome.FAIL
    assert proof_ran == []
    assert dropped == [result.database]


def test_a_preflight_failure_alone_leaves_a_clean_probe_close(monkeypatch):
    result, probe, proof_ran, _dropped = drive_proof(
        monkeypatch,
        preflight_error=ProofRunError(ErrorCategory.DATABASE_NOT_EMPTY, "not empty"),
    )

    assert probe.close_attempts == 1
    assert result.close_failures == []
    assert result.failure_category == str(ErrorCategory.DATABASE_NOT_EMPTY)
    assert proof_ran == []
    assert result.outcome is Outcome.FAIL
