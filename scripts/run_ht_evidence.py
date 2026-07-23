from __future__ import annotations

import argparse
import hashlib
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

M06A_PHASE2_INVARIANTS = (
    Invariant("M06A-HT-018", "Observation chain required", "Acquisition without its governed observation chain is rejected.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_018_observation_chain_required",)),
    Invariant("M06A-HT-019", "Truthful acquisition lifecycle", "Acquisitions start pending and finalize with a truthful terminal outcome.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_019_truthful_acquisition_lifecycle",)),
    Invariant("M06A-HT-020", "Locator is not remote acquisition", "Locator-only intake records no acquired bytes and no false success.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_020_locator_is_not_acquisition",)),
    Invariant("M06A-HT-021", "Duplicate bytes preserve encounters", "One immutable object may retain multiple acquisition encounters.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_021_repeated_identical_bytes_preserve_encounters",)),
    Invariant("M06A-HT-022", "Artifact overwrite refusal", "Existing object mismatch or tamper blocks reuse and overwrite.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_022_artifact_overwrite_or_hash_mismatch_rejected",)),
    Invariant("M06A-HT-023", "Temporary partial write reconciliation", "Oversized or interrupted temporary intake leaves no canonical object.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_023_temp_partial_write_reconciles",)),
    Invariant("M06A-HT-024", "Orphan object reconciliation", "Object-finalized/database-failed state remains non-authoritative and reconciliation-required.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_024_orphan_object_reconciliation",)),
    Invariant("M06A-HT-025", "Provenance composition", "The service does not accept caller-selected parent IDs and preserves exact branches.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_025_cross_provenance_composition_rejected",)),
    Invariant("M06A-HT-027", "Unknown rights fail closed", "Unknown rights reject before byte admission.", ("tests/test_m06a_policy_context.py::test_m06a_ht_027_unknown_rights_fail_closed",)),
    Invariant("M06A-HT-029", "Policy binding lineage", "Policy changes append immutable successor bindings.", ("tests/test_m06a_policy_context.py::test_m06a_ht_029_policy_binding_is_versioned",)),
    Invariant("M06A-HT-030", "Timed-deletion rejection", "Timed-deletion material is rejected before admission with no purge promise.", ("tests/test_m06a_policy_context.py::test_m06a_ht_030_timed_deletion_material_rejected",)),
    Invariant("M06A-HT-066", "Missing original recovery failure", "Backup or restore fails when a required original is missing.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_066_missing_original_fails_backup_or_restore",)),
    Invariant("M06A-HT-067", "Backup tamper detection", "Manifest and artifact tamper are detected.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_067_manifest_and_artifact_tamper_detected",)),
    Invariant("M06A-HT-068", "Wrong-account restore refusal", "A generation cannot restore as another Vault.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_068_wrong_account_restore_rejected",)),
    Invariant("M06A-HT-069", "Dirty restore target refusal", "Disposable restore never overwrites or mixes an existing target.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_069_dirty_restore_target_rejected",)),
    Invariant("M06A-HT-070", "Partial backup reconciliation", "A generation without COMPLETE is not restorable.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_070_partial_backup_reconciliation",)),
    Invariant("M06A-HT-073", "Derived snapshot honesty", "Derived state is explicitly non-authoritative in backup manifests.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_073_derived_snapshot_rows_are_non_authoritative",)),
    Invariant("M06A-HT-092", "Cross-platform brand Vault continuity", "Platform labels remain records inside one selected brand Vault.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_092_cross_platform_research_stays_in_brand_vault",)),
    Invariant("M06A-HT-096", "Per-Vault backup isolation", "Backup and restore contain exactly one selected Vault.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_096_backup_restore_is_per_vault",)),
    Invariant("M06A-HT-098", "Pre-byte timed-deletion gate", "Ineligible material is refused before any byte stream is accepted.", ("tests/test_m06a_policy_context.py::test_m06a_ht_098_timed_deletion_rejected_before_byte_admission",)),
    Invariant("M06A-HT-099", "Content-free rejection receipt", "Unknown-retention rejection retains only safe classification metadata.", ("tests/test_m06a_policy_context.py::test_m06a_ht_099_unknown_retention_and_rejection_receipt_fail_closed",)),
    Invariant("M06A-HT-100", "Rejected material has no downstream presence", "Rejected operations create no acquisition, artifact, backup, or other downstream authority.", ("tests/test_m06a_policy_context.py::test_m06a_ht_100_rejected_material_has_no_downstream_presence",)),
    Invariant("M06A-HT-101", "No purge bypass", "No delete-later scheduler or purge promise bypasses intake rejection.", ("tests/test_m06a_policy_context.py::test_m06a_ht_101_no_hidden_purge_or_delete_later_bypass",)),
    Invariant("M06A-HT-102", "Foundational backup schema timing", "V0002 contains the required backup and intake authority structures.", ("tests/test_m06a_migrations.py::test_m06a_ht_102_foundational_backup_schema_exists_by_phase_2",)),
    Invariant("M06A-HT-103", "Rejected content hashes never persist", "Rejected bytes and their content hashes are absent from durable outputs.", ("tests/test_m06a_policy_context.py::test_m06a_ht_103_rejected_content_hashes_never_persist",)),
    Invariant("M06A-HT-104", "No-artifact truthfulness", "no_artifact is restricted to locator-only operations and cannot mask failure.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_104_no_artifact_is_locator_only_and_cannot_mask_failure",)),
    Invariant("M06A-HT-105", "Temporary quarantine is noncanonical", "Temporary bytes are destroyed or remain blocked and never become parser/package authority.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_105_temporary_quarantine_is_noncanonical_and_reconciled",)),
    Invariant("M06A-HT-108", "Tauri-to-backend authority path", "Tauri uses the token-gated API and governed service with no browser mutation route.", ("tests/test_m06a_desktop_workflow.py::test_m06a_ht_108_tauri_api_uses_governed_service",)),
    Invariant("M06A-HT-007", "Inherited reparse rejection", "Reparse points remain unable to become Vault or artifact authority.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_007_reparse_points_rejected",)),
    Invariant("M06A-HT-014", "Inherited audit integrity", "Vault audit rows remain append-only and tamper-detecting.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_014_audit_tamper_detected",)),
    Invariant("M06A-HT-065", "Inherited downgrade refusal", "Governed Vault identity prevents destructive downgrade before schema change.", ("tests/test_m06a_migrations.py::test_m06a_ht_065_destructive_downgrade_refused",)),
    Invariant("M06A-HT-095", "Inherited per-Vault migration state", "V0002 migration state remains isolated by physical Vault.", ("tests/test_m06a_migrations.py::test_m06a_ht_095_migration_state_is_per_vault",)),
    Invariant("M06A-HT-097", "Inherited cross-database honesty", "Cross-database operations never claim impossible atomicity.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_097_cross_database_atomicity_is_never_claimed",)),
)

M06A_PHASE2_EXPECTED_IDS = (
    *(f"M06A-HT-{value:03d}" for value in range(18, 26)),
    "M06A-HT-027",
    "M06A-HT-029",
    "M06A-HT-030",
    *(f"M06A-HT-{value:03d}" for value in range(66, 71)),
    "M06A-HT-073",
    "M06A-HT-092",
    "M06A-HT-096",
    *(f"M06A-HT-{value:03d}" for value in range(98, 106)),
    "M06A-HT-108",
    "M06A-HT-007",
    "M06A-HT-014",
    "M06A-HT-065",
    "M06A-HT-095",
    "M06A-HT-097",
)

M06A_PHASE3A_INVARIANTS = (
    Invariant("M06A-HT-032", "Runtime parser admission manifest enforcement", "Only an exact owner-admitted same-Vault parser tuple may become canonically selectable; under-test remains blocked.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_032_runtime_admission_manifest_enforced", "tests/test_m06a_parser_framework.py::test_non_admitted_parser_states_fail_before_worker_launch", "tests/test_m06a_parser_framework.py::test_mismatched_and_ambiguous_admission_fail_before_worker_launch", "tests/test_m06a_parser_framework.py::test_wrong_vault_and_retention_ineligible_inputs_fail_before_worker", "tests/test_m06a_parser_packaging.py::test_parser_api_is_read_only_and_exposes_no_mutation_routes")),
    Invariant("M06A-HT-033", "Socket egress denial", "Worker socket creation is denied with no candidate package.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_033_socket_egress_denied",)),
    Invariant("M06A-HT-034", "DNS and HTTP denial", "Worker DNS and HTTP attempts are denied with no outbound connection.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_034_dns_and_http_denied",)),
    Invariant("M06A-HT-035", "Process and filesystem-mutation denial", "Worker subprocess, shell, exec, low-level write, and filesystem-mutation attempts are denied.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_035_subprocess_denied",)),
    Invariant("M06A-HT-039", "Deterministic normalized package", "Identical input and tuple produce byte-identical canonical package bytes in separate workers.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_039_package_is_deterministic",)),
    Invariant("M06A-HT-040", "Execution receipt separation", "Run-specific receipt fields never enter canonical package bytes.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_040_execution_receipt_separate_from_package",)),
    Invariant("M06A-HT-041", "Complete coverage required", "Silent partial output fails before any document version or package authority.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_041_silent_partial_output_fails",)),
    Invariant("M06A-HT-042", "Plain-text limits fail closed", "Every exact byte, character, line, line-byte, and element limit fails without partial output.", ("tests/test_m06a_parser_stdlib.py::test_m06a_ht_042_limits_fail_closed", "tests/test_m06a_parser_stdlib.py::test_hashed_boundary_recipes_generate_the_admitted_corpus_edges")),
    Invariant("M06A-HT-043", "Explicit encoding contract", "UTF-8 and BOM-declared UTF-16 succeed; invalid, replacement, missing-BOM, and NUL input fail explicitly.", ("tests/test_m06a_parser_stdlib.py::test_m06a_ht_043_encoding_is_explicit",)),
    Invariant("M06A-HT-044", "Packaged parser authority parity", "Source and real packaged sidecar use matching parser resources, tuple-versioned identity, self-tested denial controls, exact package lineage, mandatory identity bytes, and package recovery authority.", ("tests/test_m06a_parser_packaging.py::test_m06a_ht_044_packaged_parser_authority_matches", "tests/test_m06a_parser_packaging.py::test_canonical_package_backup_restore_and_tamper_fail_closed", "tests/test_m06a_parser_packaging.py::test_phase3a_c1_parser_definition_ids_are_tuple_versioned", "tests/test_m06a_parser_packaging.py::test_phase3a_c1_exact_package_document_lineage_and_reuse", "tests/test_m06a_parser_packaging.py::test_phase3a_c1_packaged_identity_bytes_are_mandatory")),
    Invariant("M06A-HT-099", "Content-free rejection receipt", "Unknown-retention rejection retains only safe classification metadata.", ("tests/test_m06a_policy_context.py::test_m06a_ht_099_unknown_retention_and_rejection_receipt_fail_closed",)),
    Invariant("M06A-HT-100", "Rejected material has no downstream presence", "Rejected material creates no acquisition, artifact, package, document, backup, or other downstream authority.", ("tests/test_m06a_policy_context.py::test_m06a_ht_100_rejected_material_has_no_downstream_presence",)),
    Invariant("M06A-HT-103", "Rejected content hashes never persist", "Rejected bytes and their hashes remain absent from durable outputs.", ("tests/test_m06a_policy_context.py::test_m06a_ht_103_rejected_content_hashes_never_persist",)),
    Invariant("M06A-HT-105", "Temporary quarantine is noncanonical", "Temporary candidate bytes are destroyed or blocked and never become package authority.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_105_temporary_quarantine_is_noncanonical_and_reconciled",)),
    Invariant("M06A-HT-106", "No second quarantine truth store", "Governed quarantine state never creates or trusts a second canonical byte store.", ("tests/test_m06a_parser_framework.py::test_m06a_ht_106_database_quarantine_creates_no_second_truth_store",)),
    Invariant("M06A-HT-007", "Inherited reparse rejection", "Reparse points remain unable to become Vault, artifact, or package authority.", ("tests/test_m06a_vault_identity.py::test_m06a_ht_007_reparse_points_rejected",)),
    Invariant("M06A-HT-012", "Inherited actor status and scope", "Disabled or wrong-Vault actors remain blocked.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_012_actor_status_and_scope_enforced",)),
    Invariant("M06A-HT-014", "Inherited Vault audit integrity", "Append-only Vault audit enforcement and chain verification detect tamper.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_014_audit_tamper_detected",)),
    Invariant("M06A-HT-015", "Inherited Vault idempotency scope", "Operation keys remain bound to exact actor, Vault, correlation, and request.", ("tests/test_m06a_actor_authority.py::test_m06a_ht_015_idempotency_scope_and_conflict",)),
    Invariant("M06A-HT-025", "Inherited provenance composition", "Caller-selected cross-provenance parent composition remains rejected.", ("tests/test_m06a_ingestion_artifacts.py::test_m06a_ht_025_cross_provenance_composition_rejected",)),
    Invariant("M06A-HT-027", "Inherited unknown-rights refusal", "Unknown rights continue to fail before byte admission.", ("tests/test_m06a_policy_context.py::test_m06a_ht_027_unknown_rights_fail_closed",)),
    Invariant("M06A-HT-030", "Inherited timed-deletion refusal", "Timed-deletion material remains rejected before admission with no purge promise.", ("tests/test_m06a_policy_context.py::test_m06a_ht_030_timed_deletion_material_rejected",)),
    Invariant("M06A-HT-062", "Inherited exact migration environment", "Vault config, manifest, revision coverage, two fresh Vaults, and populated V0002-to-V0004 upgrade remain exact.", ("tests/test_m06a_migrations.py::test_m06a_ht_062_exact_migration_environment_enforced", "tests/test_m06a_parser_framework.py::test_m06a_phase3a_fresh_two_vaults_and_populated_v0002_upgrade")),
    Invariant("M06A-HT-063", "Inherited dirty migration retention", "Interrupted Vault migration remains durably dirty through V0004 until exact recovery.", ("tests/test_m06a_migrations.py::test_m06a_ht_063_partial_migration_remains_dirty", "tests/test_m06a_parser_framework.py::test_m06a_phase3a_dirty_migration_exact_recovery")),
    Invariant("M06A-HT-064", "Inherited exact migration recovery", "Only exact identity, manifest, and V0004 head proof clears dirty state.", ("tests/test_m06a_migrations.py::test_m06a_ht_064_migration_recovery_is_exact", "tests/test_m06a_parser_framework.py::test_m06a_phase3a_dirty_migration_exact_recovery")),
    Invariant("M06A-HT-065", "Inherited destructive downgrade refusal", "Empty V0004 downgrades to exact V0003 parity while governed Phase 3A-C1 rows prevent destructive downgrade.", ("tests/test_m06a_migrations.py::test_m06a_ht_065_destructive_downgrade_refused", "tests/test_m06a_parser_framework.py::test_m06a_phase3a_empty_downgrade_parity_and_populated_refusal")),
    Invariant("M06A-HT-066", "Inherited missing-original recovery failure", "Backup or restore fails when a required original is missing.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_066_missing_original_fails_backup_or_restore",)),
    Invariant("M06A-HT-067", "Inherited backup tamper detection", "Manifest and artifact tamper remain detectable.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_067_manifest_and_artifact_tamper_detected",)),
    Invariant("M06A-HT-068", "Inherited wrong-account restore refusal", "A generation cannot restore as another Vault.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_068_wrong_account_restore_rejected",)),
    Invariant("M06A-HT-069", "Inherited dirty restore target refusal", "Disposable restore never overwrites or mixes an existing target.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_069_dirty_restore_target_rejected",)),
    Invariant("M06A-HT-070", "Inherited partial backup reconciliation", "A generation without exact completion evidence remains unrestorable.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_070_partial_backup_reconciliation",)),
    Invariant("M06A-HT-075", "Inherited Vault-scoped observability", "Health and errors do not leak another Vault path or data.", ("tests/test_m06a_desktop_workflow.py::test_m06a_ht_075_logs_cache_temp_are_vault_scoped",)),
    Invariant("M06A-HT-076", "Inherited secret hygiene", "Source, fixtures, resources, manifests, logs, and evidence contain no credential material.", ("tests/test_m06a_desktop_workflow.py::test_m06a_ht_076_secret_leakage_detected",)),
    Invariant("M06A-HT-095", "Inherited per-Vault migration state", "V0004 migration state remains isolated by physical Vault.", ("tests/test_m06a_migrations.py::test_m06a_ht_095_migration_state_is_per_vault",)),
    Invariant("M06A-HT-096", "Inherited per-Vault backup isolation", "Backup and restore contain exactly one selected Vault and reject missing, extra, or cross-Vault package bytes.", ("tests/test_m06a_backup_restore.py::test_m06a_ht_096_backup_restore_is_per_vault", "tests/test_m06a_parser_packaging.py::test_package_backup_rejects_missing_extra_and_cross_vault_bytes")),
)

M06A_TEXT_V1_INVARIANTS = (
    Invariant("M06A-TEXT-ADMIT-001", "Exact tuple and evidence manifest", "Owner admission binds the exact D039 tuple and evidence hashes.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_001_exact_tuple_and_evidence_manifest",)),
    Invariant("M06A-TEXT-ADMIT-002", "Active human Vault-owner guard", "Disabled, non-human, or unauthorized actors cannot admit the parser.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_002_active_human_vault_owner_guard",)),
    Invariant("M06A-TEXT-ADMIT-003", "Explicit confirmation required", "Admission fails without the exact D039 confirmation text.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_003_explicit_confirmation_required",)),
    Invariant("M06A-TEXT-ADMIT-004", "Immutable admission successor", "The under-test row remains immutable and the owner-admitted row supersedes it.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_004_immutable_successor_preserves_under_test",)),
    Invariant("M06A-TEXT-ADMIT-005", "Stale tuple or evidence refusal", "Any tuple or evidence-manifest mismatch fails before admission.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_005_stale_or_mismatched_material_refused",)),
    Invariant("M06A-TEXT-ADMIT-006", "Current-successor ambiguity refusal", "A second or ambiguous current admission is refused.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_006_current_successor_refuses_second_admission",)),
    Invariant("M06A-TEXT-ADMIT-007", "Per-Vault admission isolation", "Admission in one physical Vault does not admit another Vault.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_007_per_vault_isolation",)),
    Invariant("M06A-TEXT-ADMIT-008", "Admission idempotency", "Exact replay returns the same admission and conflicting reuse fails.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_008_idempotent_replay_and_conflict",)),
    Invariant("M06A-TEXT-ADMIT-009", "Admission creates no parser output", "Admission alone creates no execution, package, document, element, or region.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_009_admission_creates_no_parser_output",)),
    Invariant("M06A-TEXT-ADMIT-010", "No automatic owner admission", "Fresh Vaults remain under-test until explicit human admission.", ("tests/test_m06a_text_admission.py::test_m06a_text_admit_010_no_automatic_owner_admission",)),
    Invariant("M06A-TEXT-CANON-011", "V0004 desktop visibility", "Healthy V0004 Vaults expose parser, artifact, and document controls through Tauri/loopback.", ("tests/test_m06a_desktop_workflow.py::test_m06a_text_canon_011_v0004_desktop_visibility_and_end_to_end",)),
    Invariant("M06A-TEXT-CANON-012", "Same-Vault retention and admission gate", "Wrong-Vault, missing-link, retention-ineligible, or non-admitted input fails before worker launch.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_012_same_vault_and_admission_gate",)),
    Invariant("M06A-TEXT-CANON-013", "Artifact path size hash and reparse verification", "Canonical parsing refuses tampered or noncanonical artifact bytes before execution.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_013_artifact_hash_verification",)),
    Invariant("M06A-TEXT-CANON-014", "Worker launches only after exact admission", "No worker starts before exact owner admission and artifact eligibility checks.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_014_worker_launches_only_after_admission",)),
    Invariant("M06A-TEXT-CANON-015", "Source-worker canonical execution", "Human-triggered source-worker parsing creates exact canonical authority.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_015_source_worker_canonical_execution",)),
    Invariant("M06A-TEXT-CANON-016", "Packaged-sidecar canonical execution", "The real PyInstaller sidecar executes the exact admitted canonical path.", ("tests/test_m06a_parser_packaging.py::test_m06a_text_canon_016_real_packaged_sidecar_canonical_execution",)),
    Invariant("M06A-TEXT-CANON-017", "Deterministic package and exact coverage", "Separate workers produce one byte-identical package with exact source coverage.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_017_deterministic_package_and_coverage",)),
    Invariant("M06A-TEXT-CANON-018", "Failure creates no package or document authority", "Worker or parent-classified failure preserves a failed execution but no canonical package or document.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_018_failure_creates_no_package_or_document", "tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_018_parent_worker_exception_fails_safely")),
    Invariant("M06A-TEXT-CANON-019", "Execution idempotency", "Exact operation replay returns the same execution and conflicting reuse fails.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_019_operation_replay_and_conflict",)),
    Invariant("M06A-TEXT-CANON-020", "Exact package reuse and execution link", "Identical reruns reuse one package and append exact execution-package links.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_020_exact_package_reuse_and_execution_link",)),
    Invariant("M06A-TEXT-CANON-021", "Initial document and locator fidelity", "The initial document, elements, and regions preserve exact artifact lineage and ordinals.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_021_initial_document_elements_and_regions",)),
    Invariant("M06A-TEXT-CANON-022", "No version noise on identical rerun", "Identical reruns retain one current version ordinal without supersession authority.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_022_identical_rerun_creates_no_version_noise",)),
    Invariant("M06A-TEXT-CANON-023", "Package-before-database failure reconciliation", "A post-package database interruption leaves started execution and orphan bytes requiring reconciliation.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_023_package_before_database_requires_reconciliation",)),
    Invariant("M06A-TEXT-CANON-024", "Backup and restore include canonical output", "Canonical package and database authority survive exact V0004 backup and disposable restore.", ("tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_024_backup_restore_includes_output",)),
    Invariant("M06A-TEXT-CANON-025", "Missing extra tampered and cross-Vault output refusal", "Backup/package verification rejects missing, extra, tampered, or cross-Vault output.", ("tests/test_m06a_parser_packaging.py::test_canonical_package_backup_restore_and_tamper_fail_closed", "tests/test_m06a_parser_packaging.py::test_package_backup_rejects_missing_extra_and_cross_vault_bytes")),
    Invariant("M06A-TEXT-CANON-026", "Exact API and UI mutation surface", "Only the D039 admission, per-artifact parse, and document-summary surfaces exist.", ("tests/test_m06a_desktop_workflow.py::test_m06a_text_canon_026_api_ui_mutation_surface_is_exact",)),
    Invariant("M06A-TEXT-CANON-027", "No path secret evidence-location or content leakage", "Desktop responses and types expose safe IDs and summaries only.", ("tests/test_m06a_desktop_workflow.py::test_m06a_text_canon_027_no_path_secret_evidence_or_content_leakage",)),
    Invariant("M06A-TEXT-CANON-028", "No later-parser or capability leakage", "No SRT, VTT, JSON, Phase 3B, provider, agent, or publication capability enters the package.", ("tests/test_m06a_desktop_workflow.py::test_m06a_text_canon_028_no_later_parser_or_capability_leakage",)),
)

M06A_SRT_V1_INVARIANTS = (
    Invariant("M06A-SRT-001", "Exact D039 tuple preservation", "Every exact plain-text tuple input remains byte-identical to application commit 7980b1e7.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_001_d039_tuple_inputs_are_byte_identical",)),
    Invariant("M06A-SRT-002", "Parser-scoped SRT resource manifest", "The SRT config, schema, implementation, and dependency lock are bound by one exact parser-scoped manifest.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_002_scoped_manifest_is_complete_and_exact",)),
    Invariant("M06A-SRT-003", "Fresh V0004 under-test authority only", "A fresh V0004 Vault installs one immutable SRT under-test candidate and zero SRT owner admissions.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_003_fresh_v0004_vault_installs_under_test_only",)),
    Invariant("M06A-SRT-004", "No SRT admission or canonical surface", "No SRT admission, parse, lifecycle, configuration, bulk, or background mutation surface exists.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_004_no_admission_or_canonical_surface",)),
    Invariant("M06A-SRT-005", "Valid indexed cue parsing", "Strict indexed single-line SRT cues produce exact timing and source metadata.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_005_valid_indexed_single_line_cues",)),
    Invariant("M06A-SRT-006", "Optional cue index", "A cue without a numeric index remains valid and records an explicit null index.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_006_optional_index",)),
    Invariant("M06A-SRT-007", "Multiline and separator locator fidelity", "Multiline cue text and blank separators preserve exact byte, character, line, and normalized-text behavior.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_007_multiline_and_blank_locator_fidelity",)),
    Invariant("M06A-SRT-008", "Nonsequential index warning", "Nonsequential numeric cue indexes produce only the admitted deterministic warning.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_008_nonsequential_indexes_warn",)),
    Invariant("M06A-SRT-009", "Overlapping cue warning", "Overlapping cue times produce only the admitted deterministic warning.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_009_overlap_warns",)),
    Invariant("M06A-SRT-010", "Source order preservation", "Cue source order is preserved and never silently reordered by time or index.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_010_source_order_is_preserved",)),
    Invariant("M06A-SRT-011", "Malformed timestamp and arrow refusal", "Malformed timestamp or separator syntax fails the entire candidate with no partial output.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_011_malformed_timestamp_or_arrow_fails",)),
    Invariant("M06A-SRT-012", "Timestamp field and duration limits", "Invalid fields, excessive timestamps, and negative duration fail closed.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_012_invalid_fields_duration_and_maximum_fail",)),
    Invariant("M06A-SRT-013", "Cue text and separation required", "Missing cue text or ambiguous cue boundaries fail the whole candidate.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_013_missing_text_or_separator_fails",)),
    Invariant("M06A-SRT-014", "Exact SRT limits", "Input, cue-count, cue-byte, line, and element limits fail without partial output.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_014_all_limits_fail_closed",)),
    Invariant("M06A-SRT-015", "Explicit SRT encoding contract", "Admitted BOM encodings succeed while invalid encoding and NUL-bearing input fail explicitly.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_015_admitted_encodings", "tests/test_m06a_srt_parser.py::test_m06a_srt_015_invalid_encoding_and_nul_fail")),
    Invariant("M06A-SRT-016", "Independent SRT coverage reconciliation", "Tampered full-cue or cue-text locators are independently detected.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_016_independent_coverage_reconciliation",)),
    Invariant("M06A-SRT-017", "Deterministic source execution", "Identical isolated source workers produce byte-identical candidates and normalized packages.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_017_source_worker_is_deterministic",)),
    Invariant("M06A-SRT-018", "Source denial controls", "Network, process, filesystem, and exec violations are denied with no candidate output; malformed input preserves a failed receipt.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_018_source_worker_denials_and_failure_output",)),
    Invariant("M06A-SRT-019", "Packaged SRT authority parity", "The real packaged sidecar uses exact SRT resources and self-tested denial controls.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_019_real_packaged_sidecar_uses_exact_resources",)),
    Invariant("M06A-SRT-020", "Receipt separation", "Run-specific SRT receipt fields never enter deterministic candidate or package bytes.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_020_receipt_data_is_separate_from_package",)),
    Invariant("M06A-SRT-021", "Under-test non-authority", "Synthetic under-test execution creates no Vault execution, package, document, element, or region authority.", ("tests/test_m06a_srt_parser.py::test_m06a_srt_021_under_test_creates_no_vault_output_authority",)),
    Invariant("M06A-SRT-022", "Read-only desktop status", "Tauri and loopback expose SRT under-test status without admission or canonical mutation controls.", ("tests/test_m06a_desktop_workflow.py::test_m06a_srt_022_desktop_status_is_read_only_under_test",)),
    Invariant("M06A-SRT-023", "Inherited backup and plain-text regression", "V0004 package recovery and exact D039 plain-text admission/canonical behavior remain green.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_023_plain_text_and_backup_regression_surface_is_unchanged", "tests/test_m06a_text_canonical_execution.py::test_m06a_text_canon_024_backup_restore_includes_output", "tests/test_m06a_parser_framework.py::test_m06a_ht_032_runtime_admission_manifest_enforced")),
    Invariant("M06A-SRT-024", "No later capability leakage", "No VTT, JSON, Phase 3B, provider, agent, or publication capability enters D040.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_024_no_later_capability_leakage",)),
)

M06A_SRT_V1_EXPECTED_IDS = tuple(f"M06A-SRT-{value:03d}" for value in range(1, 25))

M06A_SRT_V1_C1_INVARIANTS = (
    Invariant("M06A-SRT-C1-001", "Exact D040 resource constants", "The pinned manifest, config, schema, implementation, and dependency-lock hashes match the live D040 bytes.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_001_exact_resource_constants_match_live_bytes",)),
    Invariant("M06A-SRT-C1-002", "Packaged schema tamper refusal", "A modified packaged SRT schema produces a failed receipt and no candidate.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_002_packaged_schema_tamper_fails",)),
    Invariant("M06A-SRT-C1-003", "Self-authorizing config tamper refusal", "A modified packaged config fails even when the request supplies the modified config hash.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_003_packaged_config_self_hash_tamper_fails",)),
    Invariant("M06A-SRT-C1-004", "Manifest and dependency-lock tamper refusal", "Modified packaged manifest or dependency-lock bytes fail before parsing with no candidate.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_004_packaged_manifest_and_lock_tamper_fail",)),
    Invariant("M06A-SRT-C1-005", "Implementation-byte tamper refusal", "Modified packaged SRT implementation bytes fail before parsing with no candidate.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_005_packaged_implementation_tamper_fails",)),
    Invariant("M06A-SRT-C1-006", "Valid packaged execution retained", "The exact untampered packaged SRT worker remains executable with inherited denial controls.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_006_valid_packaged_execution_remains_green",)),
    Invariant("M06A-SRT-C1-007", "Per-parser status isolation", "SRT-only resource failure returns one safe unavailable row while healthy D039 plain-text status remains visible.", ("tests/test_m06a_desktop_workflow.py::test_m06a_srt_c1_007_srt_resource_failure_preserves_plain_text_status",)),
    Invariant("M06A-SRT-C1-008", "No SRT authority expansion", "The correction adds no SRT admission, canonical, bulk, background, or later-parser mutation surface.", ("tests/test_m06a_srt_packaging.py::test_m06a_srt_c1_008_no_srt_mutation_or_canonical_authority",)),
)

M06A_SRT_V1_C1_EXPECTED_IDS = tuple(
    f"M06A-SRT-C1-{value:03d}" for value in range(1, 9)
)

M06A_VTT_V1_INVARIANTS = (
    Invariant("M06A-VTT-001", "Closed text/SRT tuple preservation", "Every closed D039/D040/D041 tuple input remains byte-identical to application commit 6a808225.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_001_closed_text_and_srt_tuple_inputs_are_byte_identical",)),
    Invariant("M06A-VTT-002", "Parser-scoped VTT resource tuple", "The VTT config, schema, implementation, and dependency lock are bound exactly.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_002_scoped_manifest_is_complete_and_exact",)),
    Invariant("M06A-VTT-003", "Packaged full-tuple tamper refusal", "Manifest, config, schema, implementation, and lock tamper fail before parsing with no candidate.", ("tests/test_m06a_vtt_packaging.py::test_m06a_vtt_003_packaged_worker_rejects_full_tuple_tamper",)),
    Invariant("M06A-VTT-004", "Fresh V0004 under-test authority only", "A fresh V0004 Vault installs one immutable VTT under-test candidate and zero owner admissions.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_004_fresh_v0004_vault_installs_under_test_only",)),
    Invariant("M06A-VTT-005", "No VTT mutation or canonical surface", "No admit, parse, lifecycle, bulk, background, or canonical VTT surface exists.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_005_no_admission_or_canonical_surface",)),
    Invariant("M06A-VTT-006", "Exact signature and header framing", "The WEBVTT signature, optional header text, and required blank separation are exact.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_006_signature_header_and_blank_separation",)),
    Invariant("M06A-VTT-007", "Header-only coverage", "A header-only file is valid and preserves complete source coverage with zero cues.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_007_header_only_is_valid_with_complete_coverage",)),
    Invariant("M06A-VTT-008", "Explicit UTF-8 encoding contract", "UTF-8/BOM succeed while UTF-16, invalid UTF-8, replacement, and NUL fail.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_008_encoding_contract",)),
    Invariant("M06A-VTT-009", "Exact timestamp forms", "Short and hours-bearing timestamp forms produce exact milliseconds through the configured boundary.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_009_short_and_hours_timestamps_parse_exactly",)),
    Invariant("M06A-VTT-010", "Duration and source-order gate", "Positive duration and nondecreasing cue starts are enforced without sorting.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_010_duration_and_nondecreasing_start_order",)),
    Invariant("M06A-VTT-011", "Overlap warning", "Cue overlap produces only the exact deterministic warning.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_011_overlap_warning_is_exact",)),
    Invariant("M06A-VTT-012", "Cue identifier contract", "Cue identifiers remain optional, bounded, case-sensitive, and unique.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_012_identifiers_are_optional_bounded_and_unique",)),
    Invariant("M06A-VTT-013", "Recognized setting grammar", "Recognized cue settings accept only the exact closed grammar.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_013_recognized_settings_use_closed_grammar",)),
    Invariant("M06A-VTT-014", "Setting refusal", "Malformed, duplicate, region, and excessive settings fail closed.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_014_malformed_duplicate_region_and_excessive_settings_fail",)),
    Invariant("M06A-VTT-015", "Unknown setting inert preservation", "Unknown bounded settings remain inert structured metadata with the exact warning.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_015_unknown_setting_is_preserved_inert",)),
    Invariant("M06A-VTT-016", "NOTE inert preservation", "NOTE blocks are preserved as inert regions and never become cues or instructions.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_016_note_blocks_are_inert_regions",)),
    Invariant("M06A-VTT-017", "STYLE/REGION/timeline refusal", "Rendering blocks, region references, and timeline maps fail the whole candidate.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_017_style_region_and_timeline_mapping_fail",)),
    Invariant("M06A-VTT-018", "Payload inertness", "Cue markup and entities remain exact inert text and are never rendered or fetched.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_018_payload_markup_is_preserved_inert",)),
    Invariant("M06A-VTT-019", "Malformed structure refusal", "Malformed signature, timing, separation, payload, or arrow fails with no partial candidate.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_019_malformed_structure_fails",)),
    Invariant("M06A-VTT-020", "Exact limits", "Input, line, cue, element, region, header, note, identifier, and setting limits fail closed.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_020_all_limits_fail_closed",)),
    Invariant("M06A-VTT-021", "Independent locator reconciliation", "Tampered cue and nested payload locators are detected independently.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_021_coverage_reconciliation_detects_tamper",)),
    Invariant("M06A-VTT-022", "Deterministic source execution", "Separate source workers produce byte-identical candidates and packages.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_022_source_worker_and_package_are_deterministic",)),
    Invariant("M06A-VTT-023", "Source worker denial controls", "Source worker denials and malformed failure receipts preserve no candidate.", ("tests/test_m06a_vtt_packaging.py::test_m06a_vtt_023_source_worker_denials_and_failure_receipt",)),
    Invariant("M06A-VTT-024", "Real packaged authority parity", "The real packaged sidecar validates exact VTT resources and denial controls.", ("tests/test_m06a_vtt_packaging.py::test_m06a_vtt_024_real_packaged_sidecar_uses_exact_resources",)),
    Invariant("M06A-VTT-025", "Receipt separation", "Run-specific receipt fields never enter deterministic candidate or package bytes.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_025_receipt_data_is_not_in_package",)),
    Invariant("M06A-VTT-026", "Under-test non-authority", "Synthetic VTT execution creates no Vault execution, package, document, element, or region authority.", ("tests/test_m06a_vtt_parser.py::test_m06a_vtt_026_under_test_creates_no_vault_output_authority",)),
    Invariant("M06A-VTT-027", "Neutral parser-status isolation", "Text, SRT, and VTT resource failures degrade independently while healthy rows remain visible.", ("tests/test_m06a_desktop_workflow.py::test_m06a_vtt_027_neutral_status_isolates_each_parser_failure",)),
    Invariant("M06A-VTT-028", "Inherited and no-later regressions", "Closed parser, backup, desktop, and no-JSON/Phase3B boundaries remain intact.", ("tests/test_m06a_vtt_packaging.py::test_m06a_vtt_028_inherited_and_no_later_capability_surface",)),
)

M06A_VTT_V1_EXPECTED_IDS = tuple(f"M06A-VTT-{value:03d}" for value in range(1, 29))

M06A_TEXT_V1_EXPECTED_IDS = tuple(
    [f"M06A-TEXT-ADMIT-{value:03d}" for value in range(1, 11)]
    + [f"M06A-TEXT-CANON-{value:03d}" for value in range(11, 29)]
)

M06A_PHASE3A_EXPECTED_IDS = (
    "M06A-HT-032", "M06A-HT-033", "M06A-HT-034", "M06A-HT-035",
    "M06A-HT-039", "M06A-HT-040", "M06A-HT-041", "M06A-HT-042",
    "M06A-HT-043", "M06A-HT-044", "M06A-HT-099", "M06A-HT-100",
    "M06A-HT-103", "M06A-HT-105", "M06A-HT-106", "M06A-HT-007",
    "M06A-HT-012", "M06A-HT-014", "M06A-HT-015", "M06A-HT-025",
    "M06A-HT-027", "M06A-HT-030", "M06A-HT-062", "M06A-HT-063",
    "M06A-HT-064", "M06A-HT-065", "M06A-HT-066", "M06A-HT-067",
    "M06A-HT-068", "M06A-HT-069", "M06A-HT-070", "M06A-HT-075",
    "M06A-HT-076", "M06A-HT-095", "M06A-HT-096",
)

SUITES = {
    "legacy": INVARIANTS,
    "m06a-phase1": M06A_PHASE1_INVARIANTS,
    "m06a-phase2": M06A_PHASE2_INVARIANTS,
    "m06a-phase3a": M06A_PHASE3A_INVARIANTS,
    "m06a-text-v1": M06A_TEXT_V1_INVARIANTS,
    "m06a-srt-v1": M06A_SRT_V1_INVARIANTS,
    "m06a-srt-v1-c1": M06A_SRT_V1_C1_INVARIANTS,
    "m06a-vtt-v1": M06A_VTT_V1_INVARIANTS,
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


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def phase3a_contract_metadata(results: list[dict[str, object]]) -> dict[str, object]:
    from discrepancy_desk.migration_spec import central_migration_spec, vault_migration_spec
    from discrepancy_desk.parser_contract import SECURITY_PROFILE_ID, sha256_bytes
    from discrepancy_desk.parser_service import assemble_under_test_package, load_parser_resources

    project_root = Path.cwd().resolve()
    docs_matrix = (
        project_root.parent
        / "discrepancy-desk-docs"
        / "05-implementation-planning"
        / "m06a-adversarial-closure-matrix.md"
    )
    fixture_manifest = project_root / "tests/fixtures/m06a/parsers/manifest.sha256"
    schema_path = project_root / "parser_resources/schemas/m06a.normalized-package.v1.json"
    resources = load_parser_resources(project_root)
    required_paths = (docs_matrix, fixture_manifest, schema_path, Path(__file__).resolve())
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"Phase 3A evidence resources are missing: {missing}")

    probe_bytes = b"phase3a deterministic evidence\r\n\r\nplain text\r\n"
    probe_sha256 = sha256_bytes(probe_bytes)
    probe_args = {
        "vault_account_id": "synthetic-phase3a-evidence-vault",
        "source_artifact_sha256": probe_sha256,
        "parser_admission_id": "synthetic-under-test-evidence-admission",
        "project_root": project_root,
    }
    _, first_bytes, first_worker = assemble_under_test_package(probe_bytes, **probe_args)
    _, second_bytes, second_worker = assemble_under_test_package(probe_bytes, **probe_args)
    first_hash = sha256_bytes(first_bytes)
    second_hash = sha256_bytes(second_bytes)
    deterministic = first_bytes == second_bytes and first_hash == second_hash
    if not deterministic:
        raise RuntimeError("Phase 3A evidence determinism probe failed")
    if first_worker.exit_code != 0 or second_worker.exit_code != 0:
        raise RuntimeError("Phase 3A evidence worker probe failed")

    by_id = {str(result["invariant_id"]): result for result in results}
    required_passes = (
        "M06A-HT-032", "M06A-HT-033", "M06A-HT-034", "M06A-HT-035",
        "M06A-HT-039", "M06A-HT-044", "M06A-HT-096",
    )
    if any(by_id.get(value, {}).get("passed") is not True for value in required_passes):
        raise RuntimeError("Phase 3A contract metadata lacks a required passing proof")

    return {
        "matrix_sha256": sha256_path(docs_matrix),
        "runner_registry_sha256": sha256_path(Path(__file__).resolve()),
        "fixture_manifest_sha256": sha256_path(fixture_manifest),
        "parser_resource_manifest_sha256": resources.manifest_sha256,
        "parser_implementation_sha256": resources.implementation_sha256,
        "parser_config_sha256": resources.config_sha256,
        "normalized_package_schema_sha256": sha256_path(schema_path),
        "dependency_lock_sha256": resources.dependency_lock_sha256,
        "security_profile_id": SECURITY_PROFILE_ID,
        "central_migration_head": central_migration_spec(project_root).expected_head,
        "vault_migration_head": vault_migration_spec(project_root).expected_head,
        "execution_modes": ["source-worker", "packaged-sidecar"],
        "worker_denial_results": {
            "socket": by_id["M06A-HT-033"]["passed"],
            "dns_http": by_id["M06A-HT-034"]["passed"],
            "subprocess_shell_filesystem": by_id["M06A-HT-035"]["passed"],
        },
        "deterministic_package_probe": {
            "input_sha256": probe_sha256,
            "first_package_sha256": first_hash,
            "second_package_sha256": second_hash,
            "byte_identical": deterministic,
        },
        "package_backup_restore_proof": by_id["M06A-HT-044"]["passed"],
        "package_vault_isolation_proof": by_id["M06A-HT-096"]["passed"],
        "product_default_parser_state": "under_test",
        "canonical_parser_available_by_default": False,
        "production_owner_admitted_parser_records": 0,
        "admission_gate_proof": by_id["M06A-HT-032"]["passed"],
    }



def text_v1_contract_metadata(results: list[dict[str, object]]) -> dict[str, object]:
    from discrepancy_desk.migration_spec import central_migration_spec, vault_migration_spec
    from discrepancy_desk.parser_service import load_parser_resources, text_admission_manifest

    project_root = Path.cwd().resolve()
    resources = load_parser_resources(project_root)
    manifest = text_admission_manifest(project_root)
    by_id = {str(result["invariant_id"]): result for result in results}
    if any(by_id.get(value, {}).get("passed") is not True for value in M06A_TEXT_V1_EXPECTED_IDS):
        raise RuntimeError("D039 contract metadata lacks a required passing proof")
    return {
        "runner_registry_sha256": sha256_path(Path(__file__).resolve()),
        "parser_tuple": resources.parser_tuple().material(),
        "admission_manifest": manifest,
        "central_migration_head": central_migration_spec(project_root).expected_head,
        "vault_migration_head": vault_migration_spec(project_root).expected_head,
        "execution_modes": ["source-worker", "packaged-sidecar"],
        "admission_is_per_vault": by_id["M06A-TEXT-ADMIT-007"]["passed"],
        "automatic_owner_admission": False,
        "canonical_execution_requires_human_action": True,
        "package_reuse_proof": by_id["M06A-TEXT-CANON-020"]["passed"],
        "document_version_noise_absent": by_id["M06A-TEXT-CANON-022"]["passed"],
        "backup_restore_proof": by_id["M06A-TEXT-CANON-024"]["passed"],
        "packaged_canonical_execution_proof": by_id["M06A-TEXT-CANON-016"]["passed"],
        "api_ui_surface_proof": by_id["M06A-TEXT-CANON-026"]["passed"],
        "later_capability_leakage_absent": by_id["M06A-TEXT-CANON-028"]["passed"],
    }


def srt_v1_contract_metadata(results: list[dict[str, object]]) -> dict[str, object]:
    from discrepancy_desk.migration_spec import central_migration_spec, vault_migration_spec
    from discrepancy_desk.srt_service import load_srt_resources

    project_root = Path.cwd().resolve()
    resources = load_srt_resources(project_root)
    by_id = {str(result["invariant_id"]): result for result in results}
    if any(by_id.get(value, {}).get("passed") is not True for value in M06A_SRT_V1_EXPECTED_IDS):
        raise RuntimeError("D040 SRT contract metadata lacks a required passing proof")
    fixture_manifest = project_root / "tests/fixtures/m06a/parsers/srt/manifest.sha256"
    package = (
        project_root.parent
        / "discrepancy-desk-docs"
        / "05-implementation-planning"
        / "m06a-srt-v1-under-test-candidate-package.md"
    )
    if not fixture_manifest.is_file() or not package.is_file():
        raise RuntimeError("D040 SRT evidence resources are unavailable")
    return {
        "runner_registry_sha256": sha256_path(Path(__file__).resolve()),
        "implementation_package_sha256": sha256_path(package),
        "fixture_manifest_sha256": sha256_path(fixture_manifest),
        "resource_manifest_sha256": resources.manifest_sha256,
        "config_sha256": resources.config_sha256,
        "schema_sha256": resources.schema_sha256,
        "implementation_sha256": resources.implementation_sha256,
        "dependency_lock_sha256": resources.dependency_lock_sha256,
        "parser_tuple": resources.parser_tuple().material(),
        "central_migration_head": central_migration_spec(project_root).expected_head,
        "vault_migration_head": vault_migration_spec(project_root).expected_head,
        "execution_modes": ["source-worker", "packaged-sidecar"],
        "plain_text_tuple_inputs_preserved": by_id["M06A-SRT-001"]["passed"],
        "automatic_owner_admission": False,
        "canonical_execution_available": False,
        "fresh_vault_state": "under_test",
        "source_denial_proof": by_id["M06A-SRT-018"]["passed"],
        "packaged_execution_proof": by_id["M06A-SRT-019"]["passed"],
        "read_only_status_proof": by_id["M06A-SRT-022"]["passed"],
        "inherited_regression_proof": by_id["M06A-SRT-023"]["passed"],
        "later_capability_leakage_absent": by_id["M06A-SRT-024"]["passed"],
        "d039_independent_review_deferred_not_waived": True,
    }



def srt_v1_c1_contract_metadata(results: list[dict[str, object]]) -> dict[str, object]:
    from discrepancy_desk.srt_contract import (
        SRT_CONFIG_SHA256,
        SRT_DEPENDENCY_LOCK_SHA256,
        SRT_IMPLEMENTATION_SHA256,
        SRT_RESOURCE_MANIFEST_SHA256,
        SRT_SCHEMA_SHA256,
    )

    project_root = Path.cwd().resolve()
    by_id = {str(result["invariant_id"]): result for result in results}
    if any(
        by_id.get(value, {}).get("passed") is not True
        for value in M06A_SRT_V1_C1_EXPECTED_IDS
    ):
        raise RuntimeError("D041 SRT C1 metadata lacks a required passing proof")
    package = (
        project_root.parent
        / "discrepancy-desk-docs"
        / "05-implementation-planning"
        / "m06a-srt-v1-c1-self-review-correction-package.md"
    )
    if not package.is_file():
        raise RuntimeError("D041 SRT C1 correction package is unavailable")
    return {
        "runner_registry_sha256": sha256_path(Path(__file__).resolve()),
        "correction_package_sha256": sha256_path(package),
        "resource_manifest_sha256": SRT_RESOURCE_MANIFEST_SHA256,
        "config_sha256": SRT_CONFIG_SHA256,
        "schema_sha256": SRT_SCHEMA_SHA256,
        "implementation_sha256": SRT_IMPLEMENTATION_SHA256,
        "dependency_lock_sha256": SRT_DEPENDENCY_LOCK_SHA256,
        "packaged_schema_tamper_refused": by_id["M06A-SRT-C1-002"]["passed"],
        "self_authorizing_config_tamper_refused": by_id["M06A-SRT-C1-003"]["passed"],
        "manifest_and_lock_tamper_refused": by_id["M06A-SRT-C1-004"]["passed"],
        "implementation_tamper_refused": by_id["M06A-SRT-C1-005"]["passed"],
        "valid_packaged_execution": by_id["M06A-SRT-C1-006"]["passed"],
        "per_parser_status_isolation": by_id["M06A-SRT-C1-007"]["passed"],
        "srt_admission_authorized": False,
        "srt_canonical_execution_authorized": False,
        "later_capability_leakage_absent": by_id["M06A-SRT-C1-008"]["passed"],
        "review_type": "project-steward-self-review",
        "independent_review_claim": False,
    }



def vtt_v1_contract_metadata(results: list[dict[str, object]]) -> dict[str, object]:
    from discrepancy_desk.migration_spec import central_migration_spec, vault_migration_spec
    from discrepancy_desk.vtt_service import load_vtt_resources

    project_root = Path.cwd().resolve()
    resources = load_vtt_resources(project_root)
    by_id = {str(result["invariant_id"]): result for result in results}
    if any(by_id.get(value, {}).get("passed") is not True for value in M06A_VTT_V1_EXPECTED_IDS):
        raise RuntimeError("D045 VTT contract metadata lacks a required passing proof")
    fixture_manifest = project_root / "tests/fixtures/m06a/parsers/vtt/manifest.sha256"
    package = project_root.parent / "discrepancy-desk-docs" / "05-implementation-planning" / "m06a-vtt-v1-under-test-candidate-package.md"
    if not fixture_manifest.is_file() or not package.is_file():
        raise RuntimeError("D045 VTT evidence resources are unavailable")
    return {
        "runner_registry_sha256": sha256_path(Path(__file__).resolve()),
        "implementation_package_sha256": sha256_path(package),
        "fixture_manifest_sha256": sha256_path(fixture_manifest),
        "resource_manifest_sha256": resources.manifest_sha256,
        "config_sha256": resources.config_sha256,
        "schema_sha256": resources.schema_sha256,
        "implementation_sha256": resources.implementation_sha256,
        "dependency_lock_sha256": resources.dependency_lock_sha256,
        "parser_tuple": resources.parser_tuple().material(),
        "central_migration_head": central_migration_spec(project_root).expected_head,
        "vault_migration_head": vault_migration_spec(project_root).expected_head,
        "execution_modes": ["source-worker", "packaged-sidecar"],
        "closed_text_srt_tuple_inputs_preserved": by_id["M06A-VTT-001"]["passed"],
        "packaged_full_tuple_tamper_refused": by_id["M06A-VTT-003"]["passed"],
        "automatic_owner_admission": False,
        "canonical_execution_available": False,
        "existing_vault_retrofit": False,
        "fresh_vault_state": "under_test",
        "source_denial_proof": by_id["M06A-VTT-023"]["passed"],
        "packaged_execution_proof": by_id["M06A-VTT-024"]["passed"],
        "neutral_status_isolation": by_id["M06A-VTT-027"]["passed"],
        "later_capability_leakage_absent": by_id["M06A-VTT-028"]["passed"],
    }


def validate_suite(name: str, invariants: tuple[Invariant, ...]) -> None:
    ids = [invariant.invariant_id for invariant in invariants]
    if not ids:
        raise RuntimeError(f"{name} invariant suite is empty")
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"{name} invariant suite contains duplicate IDs")
    if name == "m06a-phase1" and tuple(ids) != M06A_PHASE1_EXPECTED_IDS:
        raise RuntimeError("M06-A Phase 1 invariant mapping diverges from the accepted set")
    if name == "m06a-phase2" and tuple(ids) != M06A_PHASE2_EXPECTED_IDS:
        raise RuntimeError("M06-A Phase 2 invariant mapping diverges from the accepted set")
    if name == "m06a-phase3a" and tuple(ids) != M06A_PHASE3A_EXPECTED_IDS:
        raise RuntimeError("M06-A Phase 3A invariant mapping diverges from the accepted set")
    if name == "m06a-text-v1" and tuple(ids) != M06A_TEXT_V1_EXPECTED_IDS:
        raise RuntimeError("M06-A text-v1 invariant mapping diverges from the D039 set")
    if name == "m06a-srt-v1" and tuple(ids) != M06A_SRT_V1_EXPECTED_IDS:
        raise RuntimeError("M06-A SRT-v1 invariant mapping diverges from the D040 set")
    if name == "m06a-srt-v1-c1" and tuple(ids) != M06A_SRT_V1_C1_EXPECTED_IDS:
        raise RuntimeError("M06-A SRT-v1 C1 mapping diverges from the D041 set")
    if name == "m06a-vtt-v1" and tuple(ids) != M06A_VTT_V1_EXPECTED_IDS:
        raise RuntimeError("M06-A VTT-v1 mapping diverges from the D045 set")
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
            "evidence_counts": {
                "collected": 0,
                "executed": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "xfailed": 0,
                "xpassed": 0,
                "errored": 0,
            },
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
    evidence_counts = {
        "collected": 0,
        "executed": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "errored": 0,
    }
    if not evidence_path.is_file():
        evidence_error = "pytest evidence file is missing"
    else:
        try:
            evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            evidence_error = f"pytest evidence is unreadable: {type(exc).__name__}"
        if evidence_payload is not None:
            counts = evidence_payload.get("counts")
            if isinstance(counts, dict):
                passed_count = int(counts.get("passed", 0))
                failed_count = int(counts.get("failed", 0))
                skipped_count = int(counts.get("skipped", 0))
                error_count = int(counts.get("error", 0))
                xfailed_count = int(counts.get("xfailed", 0))
                xpassed_count = int(counts.get("xpassed", 0))
                evidence_counts = {
                    "collected": passed_count
                    + failed_count
                    + skipped_count
                    + error_count
                    + xfailed_count
                    + xpassed_count,
                    "executed": passed_count + failed_count + error_count,
                    "passed": passed_count,
                    "failed": failed_count,
                    "skipped": skipped_count,
                    "xfailed": xfailed_count,
                    "xpassed": xpassed_count,
                    "errored": error_count,
                }
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
        "evidence_counts": evidence_counts,
        "evidence_error": evidence_error,
    }


def commit_bound_payload(payload: dict[str, object]) -> dict[str, object]:
    results = []
    for raw_result in payload["results"]:
        if not isinstance(raw_result, dict):
            raise RuntimeError("hammer result is not an object")
        results.append(
            {
                key: value
                for key, value in raw_result.items()
                if key not in {"stdout", "stderr"}
            }
        )
    return {
        key: value
        for key, value in payload.items()
        if key != "generated_at" and key != "results"
    } | {"results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=sorted(SUITES), default="legacy")
    args = parser.parse_args()
    invariants = SUITES[args.suite]
    validate_suite(args.suite, invariants)
    expected_commit = git_sha()
    evidence_root = (
        Path("runtime/test-evidence/hammer") / args.suite
        if args.suite in {
            "m06a-phase3a", "m06a-text-v1", "m06a-srt-v1", "m06a-srt-v1-c1", "m06a-vtt-v1"
        }
        else Path("runtime/test-evidence") / args.suite
    )
    evidence_root.mkdir(parents=True, exist_ok=True)
    output_root = Path("runtime/ht-evidence") / args.suite
    output_root.mkdir(parents=True, exist_ok=True)
    results = [run_invariant(invariant, evidence_root, expected_commit) for invariant in invariants]
    dirty = working_tree_dirty()
    test_count_names = (
        "collected", "executed", "passed", "failed", "skipped",
        "xfailed", "xpassed", "errored",
    )
    aggregate_test_counts = {
        name: sum(
            int(result.get("evidence_counts", {}).get(name, 0))
            for result in results
            if isinstance(result.get("evidence_counts"), dict)
        )
        for name in test_count_names
    }
    phase_contract = phase3a_contract_metadata(results) if args.suite == "m06a-phase3a" else None
    text_v1_contract = text_v1_contract_metadata(results) if args.suite == "m06a-text-v1" else None
    srt_v1_contract = srt_v1_contract_metadata(results) if args.suite == "m06a-srt-v1" else None
    srt_v1_c1_contract = (
        srt_v1_c1_contract_metadata(results)
        if args.suite == "m06a-srt-v1-c1"
        else None
    )
    vtt_v1_contract = vtt_v1_contract_metadata(results) if args.suite == "m06a-vtt-v1" else None
    payload = {
        "schema_version": 2,
        "suite": args.suite,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "commit_sha": expected_commit,
        "working_tree_dirty": dirty,
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "command": f"uv run python scripts/run_ht_evidence.py --suite {args.suite}",
        "invariant_ids": [invariant.invariant_id for invariant in invariants],
        "results": results,
        "test_counts": aggregate_test_counts,
        "phase3a_contract": phase_contract,
        "text_v1_contract": text_v1_contract,
        "srt_v1_contract": srt_v1_contract,
        "srt_v1_c1_contract": srt_v1_c1_contract,
        "vtt_v1_contract": vtt_v1_contract,
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
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    destination.write_text(rendered, encoding="utf-8", newline="\n")
    if not dirty:
        immutable = (
            Path("runtime/test-evidence") / args.suite / "by-commit" / f"{expected_commit}.json"
            if args.suite in {
                "m06a-phase3a", "m06a-text-v1", "m06a-srt-v1", "m06a-srt-v1-c1", "m06a-vtt-v1"
            }
            else output_root / "by-commit" / f"{expected_commit}.json"
        )
        immutable.parent.mkdir(parents=True, exist_ok=True)
        immutable_rendered = (
            json.dumps(commit_bound_payload(payload), indent=2, sort_keys=True) + "\n"
        )
        if immutable.exists():
            if immutable.read_text(encoding="utf-8") != immutable_rendered:
                raise RuntimeError("commit-bound hammer evidence already exists with different bytes")
        else:
            with immutable.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(immutable_rendered)
    print(json.dumps(payload["summary"], sort_keys=True))
    print(destination)
    return 1 if payload["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
