from __future__ import annotations

import argparse
import json
import os
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
        "Migration and recovery compatibility through 0005",
        "Fresh and upgraded databases, dirty migration handling, archive evidence, backup, and restore proofs remain green at head 0005.",
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
    Invariant(
        "M05-G01",
        "Desktop API authority and parity",
        "Token-gated account-scoped desktop reads and mutations preserve the M04 authority contract through the full manual workflow.",
        (
            "tests/test_m05_desktop_api_contract.py",
        ),
    ),
    Invariant(
        "M05-G02",
        "Native lifecycle and process ownership",
        "Loopback startup, environment-only launch configuration, bounded proof exit, child cleanup, and supervisor fallback remain enforced.",
        (
            "tests/test_m05_sidecar_lifecycle.py",
        ),
    ),
    Invariant(
        "M05-G03",
        "Desktop capability and evidence-import boundary",
        "Tauri capabilities remain deny-by-default and native evidence import is bounded without direct database authority.",
        (
            "tests/test_m05_desktop_security.py",
        ),
    ),
    Invariant(
        "M05-G04",
        "Packaging and distribution boundary",
        "Current-user NSIS, no updater, admitted dependency locks, icons, and generated-output exclusions remain enforced.",
        (
            "tests/test_m05_packaging_contract.py",
        ),
    ),
    Invariant(
        "AC01-G01",
        "Lifecycle doctrine correction",
        "The accepted implemented transition table is exact and contains no dead mismatch-to-published path.",
        (
            "tests/test_lifecycle_contract.py",
        ),
    ),
    Invariant(
        "AC01-G02",
        "Durable test evidence separation",
        "Full-suite, focused, and hammer sessions resolve to distinct evidence paths.",
        (
            "tests/test_test_evidence_paths.py",
        ),
    ),
)


M06A_PHASE1_INVARIANTS = (
    Invariant("M06A-HT-001", "Vault isolation", "Two physical Vaults remain isolated.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_001_vault_isolation",)),
    Invariant("M06A-HT-002", "Wrong database rejection", "A copied or wrong Vault database fails identity verification.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_002_wrong_database_rejected",)),
    Invariant("M06A-HT-003", "Marker tamper rejection", "Modified Vault identity markers fail closed.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_003_marker_tamper_rejected",)),
    Invariant("M06A-HT-004", "Existing-file-only open", "Vault open never creates a missing database or root.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_004_open_never_creates_database",)),
    Invariant("M06A-HT-005", "Path traversal rejection", "Absolute, drive, UNC, and traversal roots are rejected.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_005_path_traversal_rejected",)),
    Invariant("M06A-HT-006", "Windows path rules", "Reserved names, trailing characters, and case collisions fail.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_006_windows_name_and_case_rules",)),
    Invariant("M06A-HT-007", "Reparse-point rejection", "Symlinks, junctions, and reparse points cannot become Vault authority.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_007_reparse_points_rejected",)),
    Invariant("M06A-HT-008", "Platform binding required", "Unbound platform accounts cannot combine with Vault authority.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_008_platform_binding_required",)),
    Invariant("M06A-HT-009", "Request actor impersonation", "Untrusted actor identifiers cannot resolve as human authority.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_009_request_actor_impersonation_rejected",)),
    Invariant("M06A-HT-010", "System human-authority rejection", "System actors cannot execute human-only decisions.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_010_system_human_authority_rejected",)),
    Invariant("M06A-HT-011", "Model authority rejection", "Model actors cannot promote candidate output to human authority.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_011_model_authority_rejected",)),
    Invariant("M06A-HT-012", "Actor status and scope", "Disabled or wrong-Vault actors fail closed.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_012_actor_status_and_scope_enforced",)),
    Invariant("M06A-HT-013", "Desktop token limitation", "A launch token is not a human identity.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_013_token_is_not_human_identity",)),
    Invariant("M06A-HT-014", "Vault audit integrity", "Append-only enforcement and chain verification detect tamper.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_014_audit_tamper_detected",)),
    Invariant("M06A-HT-015", "Vault idempotency scope", "Operation keys bind actor, Vault, correlation, and request.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_015_idempotency_scope_and_conflict",)),
    Invariant("M06A-HT-016", "Cross-database partial failure", "Partial provisioning becomes reconciliation-required, never success.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_016_cross_database_partial_failure_reconciles",)),
    Invariant("M06A-HT-017", "Receipt fabrication rejection", "Mismatched central and Vault receipts cannot reconcile.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_017_cross_database_receipt_fabrication_rejected",)),
    Invariant("M06A-HT-062", "Exact migration environment", "Config, env, template, manifest, and revision coverage are exact.", ("tests/test_m06a_migrations.py::test_m06a_ht_062_exact_migration_environment_enforced",)),
    Invariant("M06A-HT-063", "Dirty migration retention", "Interrupted Vault migration remains durably dirty.", ("tests/test_m06a_migrations.py::test_m06a_ht_063_partial_migration_remains_dirty",)),
    Invariant("M06A-HT-064", "Exact migration recovery", "Only identity, manifest, and head-matched recovery clears dirty state.", ("tests/test_m06a_migrations.py::test_m06a_ht_064_migration_recovery_is_exact",)),
    Invariant("M06A-HT-065", "Destructive downgrade refusal", "Governed Vault rows prevent destructive downgrade.", ("tests/test_m06a_migrations.py::test_m06a_ht_065_destructive_downgrade_refused",)),
    Invariant("M06A-HT-075", "Vault-scoped observability", "Health and error surfaces do not leak another Vault's path or data.", ("tests/test_m06a_desktop_workflow.py::test_m06a_ht_075_logs_cache_temp_are_vault_scoped",)),
    Invariant("M06A-HT-076", "Secret hygiene", "Phase 1 source and package resources contain no credential material.", ("tests/test_m06a_desktop_workflow.py::test_m06a_ht_076_secret_leakage_detected",)),
    Invariant("M06A-HT-088", "Brand Vault multi-platform binding", "One brand Vault binds multiple platform accounts without another Vault.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_088_brand_vault_binds_multiple_platform_accounts",)),
    Invariant("M06A-HT-089", "Account cannot select Vault", "A platform account identifier cannot create or select a Vault.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_089_platform_account_cannot_select_or_create_vault",)),
    Invariant("M06A-HT-090", "Wrong-brand binding rejection", "An actively bound account cannot silently bind to another brand Vault.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_090_wrong_brand_binding_fails",)),
    Invariant("M06A-HT-093", "One SQLite file per Vault", "Every physical Vault owns a distinct SQLite database.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_093_each_physical_vault_has_own_sqlite_file",)),
    Invariant("M06A-HT-094", "Registry mapping verification", "Wrong registry-to-root/database mappings fail before mutation.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_094_wrong_registry_database_mapping_fails",)),
    Invariant("M06A-HT-095", "Per-Vault migration state", "Dirty migration state cannot bleed between Vault databases.", ("tests/test_m06a_migrations.py::test_m06a_ht_095_migration_state_is_per_vault",)),
    Invariant("M06A-HT-097", "No cross-database atomicity claim", "Partial central/Vault work never reports atomic success.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_097_cross_database_atomicity_is_never_claimed",)),
    Invariant("M06A-HT-108", "Tauri-to-backend authority path", "The Tauri client uses the token-gated desktop API, which delegates to the governed Vault service with no browser mutation route.", ("tests/test_m06a_desktop_workflow.py::test_m06a_ht_108_tauri_api_uses_governed_service",)),
)

M06A_PHASE1_EXPECTED_IDS = (
    *(f"M06A-HT-{value:03d}" for value in range(1, 18)),
    *(f"M06A-HT-{value:03d}" for value in range(62, 66)),
    "M06A-HT-075",
    "M06A-HT-076",
    "M06A-HT-088",
    "M06A-HT-089",
    "M06A-HT-090",
    "M06A-HT-093",
    "M06A-HT-094",
    "M06A-HT-095",
    "M06A-HT-097",
    "M06A-HT-108",
)

SUITES = {
    "legacy": INVARIANTS,
    "m06a-phase1": M06A_PHASE1_INVARIANTS,
}


def git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


def working_tree_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
    )
    return bool(completed.stdout.strip())


def validate_suite(name: str, invariants: tuple[Invariant, ...]) -> None:
    ids = [invariant.invariant_id for invariant in invariants]
    if not ids:
        raise RuntimeError(f"{name} invariant suite is empty")
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"{name} invariant suite contains duplicate IDs")
    if name == "m06a-phase1" and tuple(ids) != M06A_PHASE1_EXPECTED_IDS:
        raise RuntimeError("M06-A Phase 1 invariant mapping diverges from the accepted set")
    for invariant in invariants:
        if invariant.disposition == "execute" and not invariant.tests:
            raise RuntimeError(f"{invariant.invariant_id} has no test mapping")


def run_invariant(invariant: Invariant, evidence_root: Path, expected_commit: str) -> dict[str, object]:
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
            "evidence_error": None,
        }
    evidence_path = evidence_root / f"{invariant.invariant_id}.json"
    evidence_path.unlink(missing_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", *invariant.tests]
    environment = os.environ.copy()
    environment["DISCREPANCY_DESK_PYTEST_EVIDENCE_PATH"] = str(evidence_path)
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False, env=environment
    )
    evidence_error: str | None = None
    evidence_payload: dict[str, object] | None = None
    if not evidence_path.is_file():
        evidence_error = "pytest evidence file is missing"
    else:
        try:
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            evidence_error = f"pytest evidence is unreadable: {type(exc).__name__}"
        if evidence_payload is not None:
            counts = evidence_payload.get("counts")
            if not isinstance(counts, dict):
                evidence_error = "pytest evidence counts are missing"
            elif int(counts.get("passed", 0)) <= 0:
                evidence_error = "pytest evidence reports zero passed tests"
            elif int(counts.get("failed", 0)) or int(counts.get("error", 0)):
                evidence_error = "pytest evidence reports failure or error counts"
            elif any(int(counts.get(name, 0)) for name in ("skipped", "xfailed", "xpassed")):
                evidence_error = "pytest evidence reports an unapproved skip or xfail outcome"
            elif evidence_payload.get("invariant_id") != invariant.invariant_id:
                evidence_error = "pytest evidence invariant ID diverges from the runner"
            elif evidence_payload.get("exit_status") != completed.returncode:
                evidence_error = "pytest evidence exit status diverges from the runner"
            elif evidence_payload.get("commit_sha") != expected_commit:
                evidence_error = "pytest evidence commit SHA diverges from the runner"
    passed = completed.returncode == 0 and evidence_error is None
    return {
        "invariant_id": invariant.invariant_id,
        "title": invariant.title,
        "disposition": invariant.disposition,
        "expected_result": invariant.expected_result,
        "tests": list(invariant.tests),
        "passed": passed,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "evidence_path": str(evidence_path).replace("\\", "/"),
        "evidence_error": evidence_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=sorted(SUITES), default="legacy")
    args = parser.parse_args()
    invariants = SUITES[args.suite]
    validate_suite(args.suite, invariants)
    expected_commit = git_sha()
    evidence_root = Path("runtime/test-evidence") / args.suite
    evidence_root.mkdir(parents=True, exist_ok=True)
    output_root = Path("runtime/ht-evidence") / args.suite
    output_root.mkdir(parents=True, exist_ok=True)
    results = [run_invariant(invariant, evidence_root, expected_commit) for invariant in invariants]
    payload = {
        "schema_version": 2,
        "suite": args.suite,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "commit_sha": expected_commit,
        "working_tree_dirty": working_tree_dirty(),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "command": f"uv run python scripts/run_ht_evidence.py --suite {args.suite}",
        "invariant_ids": [invariant.invariant_id for invariant in invariants],
        "results": results,
        "summary": {
            "required": len(invariants),
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
