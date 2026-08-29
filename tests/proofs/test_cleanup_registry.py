"""Cleanup registry behaviour under injected failures.

Reconciliation section 5: register immediately after creation, attempt
proof-local cleanup plus a process-level backstop sweep, and force the overall
result to FAIL when any cleanup fails. The drop function is injected, so no
database is involved.
"""

from __future__ import annotations

import psycopg
import pytest

from tools.postgres_foundation_proofs.databases import ProofDatabaseRegistry
from tools.postgres_foundation_proofs.errors import ErrorCategory, ProofRunError


def test_successful_drop_clears_the_registry():
    dropped: list[str] = []
    registry = ProofDatabaseRegistry(dropped.append)
    registry.register("fndpg01_a_00")
    assert registry.outstanding == ("fndpg01_a_00",)

    result = registry.drop("fndpg01_a_00")

    assert result["dropped"] is True
    assert dropped == ["fndpg01_a_00"]
    assert registry.outstanding == ()
    assert registry.all_dropped is True
    assert registry.failures == []


def test_failed_drop_is_recorded_and_keeps_the_database_outstanding():
    def boom(_name: str) -> None:
        raise ProofRunError(ErrorCategory.CLEANUP_FAILED, "simulated drop failure")

    registry = ProofDatabaseRegistry(boom)
    registry.register("fndpg01_b_01")

    result = registry.drop("fndpg01_b_01")

    assert result["dropped"] is False
    assert result["error_category"] == str(ErrorCategory.CLEANUP_FAILED)
    assert registry.outstanding == ("fndpg01_b_01",)
    assert registry.all_dropped is False
    assert registry.failures == [result]


def test_drop_never_raises_so_the_run_can_still_report():
    def boom(_name: str) -> None:
        raise RuntimeError("unexpected")

    registry = ProofDatabaseRegistry(boom)
    registry.register("fndpg01_c_02")
    registry.drop("fndpg01_c_02")  # must not raise
    assert registry.all_dropped is False


def test_driver_error_message_is_runner_authored():
    error = psycopg.errors.ObjectInUse("database is being accessed by other users")

    def boom(_name: str) -> None:
        raise error

    registry = ProofDatabaseRegistry(boom)
    registry.register("fndpg01_a_03")
    result = registry.drop("fndpg01_a_03")

    assert "could not drop proof database" in result["message"]
    assert "being accessed by other users" not in result["message"]


def test_sweep_is_the_backstop_for_anything_still_registered():
    dropped: list[str] = []
    registry = ProofDatabaseRegistry(dropped.append)
    registry.register("fndpg01_a_04")
    registry.register("fndpg01_b_05")

    results = registry.sweep()

    assert dropped == ["fndpg01_a_04", "fndpg01_b_05"]
    assert all(r["dropped"] for r in results)
    assert registry.outstanding == ()


def test_sweep_after_a_partial_failure_still_reports_failure():
    def only_b_fails(name: str) -> None:
        if name.startswith("fndpg01_b"):
            raise ProofRunError(ErrorCategory.CLEANUP_FAILED, "simulated")

    registry = ProofDatabaseRegistry(only_b_fails)
    registry.register("fndpg01_a_06")
    registry.register("fndpg01_b_07")

    registry.sweep()

    assert registry.outstanding == ("fndpg01_b_07",)
    assert registry.all_dropped is False


def test_registering_the_same_database_twice_is_idempotent():
    registry = ProofDatabaseRegistry(lambda _name: None)
    registry.register("fndpg01_a_08")
    registry.register("fndpg01_a_08")
    assert registry.outstanding == ("fndpg01_a_08",)


@pytest.mark.parametrize("name", ["fndpg01_a_09", "fndpg01_c_10"])
def test_dropping_an_unregistered_database_is_still_recorded(name):
    registry = ProofDatabaseRegistry(lambda _name: None)
    result = registry.drop(name)
    assert result["dropped"] is True
    assert registry.results == [result]
