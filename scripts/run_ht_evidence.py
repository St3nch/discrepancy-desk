from __future__ import annotations

import json
import platform
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    title: str
    expected_result: str
    tests: tuple[str, ...]
    disposition: str = "execute"


INVARIANTS = (
    Invariant(
        "HT-01",
        "Exact authored-text approval binding",
        "All byte-significant mutations produce distinct bindings.",
        ("tests/test_persistence_hammer.py::test_exact_binding_changes_for_whitespace_unicode_and_platform",),
    ),
    Invariant(
        "HT-02",
        "Approval freshness and exact revision",
        "Stale or wrong-state approval fails atomically; successor revision supersedes active approval.",
        (
            "tests/test_persistence_hammer.py::test_stale_approval_binding_is_rejected_atomically",
            "tests/test_integrity_and_restore.py::test_approval_wrong_state_rolls_back_even_after_prior_changes",
            "tests/test_revision_and_publication_lineage.py::test_successor_revision_supersedes_active_approval_atomically",
        ),
    ),
    Invariant(
        "HT-03",
        "Lifecycle legality and invalidation",
        "Illegal or generic authority-bypassing transitions fail without partial state or audit.",
        (
            "tests/test_persistence_hammer.py::test_illegal_transition_rolls_back_without_audit",
            "tests/test_recovery_authority_and_mismatch.py::test_generic_transition_cannot_bypass_approval_gate",
            "tests/test_operator_service_loop.py::test_rejection_requires_review_state_and_preserves_reason_in_audit",
        ),
    ),
    Invariant(
        "HT-04",
        "Stable external identity",
        "Fabricated identities fail; stable account identity replays and mutable metadata updates remain singular.",
        (
            "tests/test_persistence_hammer.py::test_foreign_keys_reject_fabricated_identity",
            "tests/test_operator_service_loop.py::test_owned_account_stable_identity_replay_uses_existing_record",
            "tests/test_operator_service_loop.py::test_owned_account_stable_identity_updates_mutable_username_metadata",
        ),
    ),
    Invariant(
        "HT-05",
        "Canonical evidence integrity",
        "Path escape, missing file, or hash mismatch fails closed.",
        ("tests/test_persistence_hammer.py::test_evidence_hash_and_path_fail_closed",),
    ),
    Invariant(
        "HT-06",
        "Database/filesystem reconciliation",
        "Missing, orphaned, or byte-disagreeing evidence fails restore verification.",
        (
            "tests/test_integrity_and_restore.py::test_backup_restore_verifies_database_evidence_and_audit",
            "tests/test_integrity_and_restore.py::test_restore_rejects_orphan_evidence",
            "tests/test_integrity_and_restore.py::test_restore_rejects_database_hash_disagreement",
        ),
    ),
    Invariant(
        "HT-07",
        "Connection foreign-key enforcement",
        "Every governed connection enables foreign keys and rejects fabricated relationships.",
        (
            "tests/test_persistence_hammer.py::test_connection_contract",
            "tests/test_persistence_hammer.py::test_foreign_keys_reject_fabricated_identity",
        ),
    ),
    Invariant(
        "HT-08",
        "Uniqueness and idempotency",
        "Exact replay is a no-op; conflicting key reuse and duplicate publication identity fail.",
        (
            "tests/test_persistence_operations_hammer.py::test_manual_ready_replay_is_idempotent_and_conflict_fails",
            "tests/test_persistence_operations_hammer.py::test_publication_replay_and_platform_mismatch_fail_closed",
            "tests/test_persistence_hammer.py::test_duplicate_external_publication_identity_is_rejected",
            "tests/test_operator_service_loop.py::test_account_capture_and_source_idempotency_conflicts",
        ),
    ),
    Invariant(
        "HT-09",
        "Transaction atomicity",
        "Lifecycle, approval, publication, and rejection failures leave no partial state or audit.",
        (
            "tests/test_persistence_hammer.py::test_illegal_transition_rolls_back_without_audit",
            "tests/test_integrity_and_restore.py::test_approval_wrong_state_rolls_back_even_after_prior_changes",
            "tests/test_persistence_operations_hammer.py::test_publication_replay_and_platform_mismatch_fail_closed",
        ),
    ),
    Invariant(
        "HT-10",
        "Concurrency and busy handling",
        "An overlapping writer receives a clean busy failure with no partial write.",
        ("tests/test_persistence_operations_hammer.py::test_busy_writer_rejects_cleanly_without_partial_write",),
    ),
    Invariant(
        "HT-11",
        "Audit integrity",
        "Audit rows are append-only and out-of-band chain tampering is detected.",
        (
            "tests/test_persistence_hammer.py::test_audit_events_are_append_only",
            "tests/test_persistence_operations_hammer.py::test_out_of_band_audit_tamper_is_detected",
        ),
    ),
    Invariant(
        "HT-12",
        "Metric observations",
        "Snapshot replay is idempotent, conflicts fail, and corrections append against the same publication.",
        ("tests/test_persistence_operations_hammer.py::test_metric_snapshot_replay_conflict_and_correction",),
    ),
    Invariant(
        "HT-13",
        "Explicit unknown states",
        "Queries require explicit supported observation states and reject invented state vocabulary.",
        ("tests/test_recovery_authority_and_mismatch.py::test_metric_queries_require_explicit_supported_states",),
    ),
    Invariant(
        "HT-14",
        "Mention classification",
        "Deferred by approved M03 scope; no classifier is admitted in this milestone.",
        (),
        disposition="deferred_by_scope",
    ),
    Invariant(
        "HT-15",
        "Platform isolation",
        "A revision or approval cannot cross platform/account boundaries during publication.",
        ("tests/test_persistence_operations_hammer.py::test_publication_replay_and_platform_mismatch_fail_closed",),
    ),
    Invariant(
        "HT-16",
        "Dirty migration state",
        "Dirty state blocks startup/upgrade and only the matching operation may clear it.",
        (
            "tests/test_persistence_operations_hammer.py::test_dirty_migration_marker_blocks_and_requires_matching_clear",
            "tests/test_web_control_room.py::test_startup_refuses_dirty_migration_state",
        ),
    ),
    Invariant(
        "HT-17",
        "Interrupted migration recovery",
        "Failure retains the marker; verified completion or bounded empty discard are the only recovery paths.",
        (
            "tests/test_migration_archive_evidence.py::test_guarded_migration_failure_retains_dirty_marker",
            "tests/test_recovery_authority_and_mismatch.py::test_recover_completed_migration_requires_verified_database",
            "tests/test_recovery_authority_and_mismatch.py::test_completed_recovery_refuses_wrong_operation_and_missing_version",
            "tests/test_recovery_authority_and_mismatch.py::test_discard_failed_empty_migration_is_bounded",
        ),
    ),
    Invariant(
        "HT-18",
        "Backup and disposable restore",
        "Backup, deterministic archive, real age encryption/decryption, and disposable verification succeed; tampering fails.",
        (
            "tests/test_integrity_and_restore.py::test_backup_restore_verifies_database_evidence_and_audit",
            "tests/test_integrity_and_restore.py::test_backup_tamper_is_rejected",
            "tests/test_migration_archive_evidence.py::test_deterministic_zip_is_byte_identical",
            "tests/test_migration_archive_evidence.py::test_age_encryption_and_manifest",
            "tests/test_migration_archive_evidence.py::test_age_failure_removes_partial_output",
        ),
    ),
    Invariant(
        "HT-19",
        "Three-way restore reconciliation",
        "Database, manifest, and raw bytes must agree; repaired-manifest concealment still fails.",
        (
            "tests/test_integrity_and_restore.py::test_restore_rejects_orphan_evidence",
            "tests/test_integrity_and_restore.py::test_restore_rejects_database_hash_disagreement",
        ),
    ),
    Invariant(
        "HT-20",
        "Detector/classifier non-authority",
        "Flagged, non-detected, and errored detector outcomes remain advisory; generic approval bypass fails.",
        (
            "tests/test_recovery_authority_and_mismatch.py::test_generic_transition_cannot_bypass_approval_gate",
            "tests/test_recovery_authority_and_mismatch.py::test_detector_results_are_advisory_and_do_not_change_state",
        ),
    ),
    Invariant(
        "M04-G01",
        "Editorial organization and schedule authority",
        "Account scope, closed lanes, normalized tags, horizon checks, lineage, replay, dormancy, and dated targets pass on real SQLite.",
        (
            "tests/test_m04_editorial_schedule_contract.py",
        ),
    ),
    Invariant(
        "M04-G02",
        "Derived query isolation and anti-filler behavior",
        "Command Center, schedule, Reserve, Ready-to-Post, and Need-a-Post remain account-scoped and deterministic.",
        (
            "tests/test_m04_operator_queries.py",
        ),
    ),
    Invariant(
        "M04-G03",
        "Functional web control room",
        "Account-scoped organization, scheduling, pipeline, and refusal behavior work through admitted routes.",
        (
            "tests/test_m04_web_workflow.py",
            "tests/test_web_control_room.py",
        ),
    ),
    Invariant(
        "M04-G04",
        "Realistic editorial week and correction lineage",
        "Two accounts, all three lanes, reschedule, Reserve, approval preservation/invalidation, match, mismatch, replacement, honest metrics, empty-slot, and replay proof pass.",
        (
            "tests/test_m04_editorial_week_scenario.py",
        ),
    ),
    Invariant(
        "M04-G05",
        "Migration and recovery compatibility through 0004",
        "Fresh and upgraded databases, dirty migration handling, archive evidence, backup, and restore proofs remain green at head 0004.",
        (
            "tests/test_migration_archive_evidence.py",
            "tests/test_integrity_and_restore.py",
            "tests/test_recovery_authority_and_mismatch.py",
        ),
    ),
    Invariant(
        "M04-G06",
        "Authority and publication regression",
        "M03 lifecycle, revision, approval, publication, metric, idempotency, concurrency, and audit contracts remain intact under M04.",
        (
            "tests/test_persistence_hammer.py",
            "tests/test_persistence_operations_hammer.py",
            "tests/test_operator_service_loop.py",
            "tests/test_revision_and_publication_lineage.py",
        ),
    ),
)


def git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def run_invariant(invariant: Invariant) -> dict[str, object]:
    if invariant.disposition != "execute":
        return {
            "invariant_id": invariant.invariant_id,
            "title": invariant.title,
            "disposition": invariant.disposition,
            "expected_result": invariant.expected_result,
            "tests": [],
            "passed": None,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }
    command = [sys.executable, "-m", "pytest", "-q", *invariant.tests]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "invariant_id": invariant.invariant_id,
        "title": invariant.title,
        "disposition": invariant.disposition,
        "expected_result": invariant.expected_result,
        "tests": list(invariant.tests),
        "passed": completed.returncode == 0,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    output_root = Path("runtime/ht-evidence")
    output_root.mkdir(parents=True, exist_ok=True)
    results = [run_invariant(invariant) for invariant in INVARIANTS]
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "commit_sha": git_sha(),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "command": "uv run python scripts/run_ht_evidence.py",
        "results": results,
        "summary": {
            "executed": sum(result["disposition"] == "execute" for result in results),
            "passed": sum(result["passed"] is True for result in results),
            "failed": sum(result["passed"] is False for result in results),
            "deferred_by_scope": sum(
                result["disposition"] == "deferred_by_scope" for result in results
            ),
        },
    }
    destination = output_root / "latest-ht-evidence.json"
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["summary"], sort_keys=True))
    print(destination)
    return 1 if payload["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
