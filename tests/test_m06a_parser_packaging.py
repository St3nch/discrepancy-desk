from __future__ import annotations

import hashlib
import shutil
import sqlite3
import json
import struct
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.parser_contract import (
    PACKAGE_SCHEMA_VERSION,
    SECURITY_PROFILE_ID,
    WORKER_PROTOCOL_VERSION,
    canonical_json,
    sha256_bytes,
)
from discrepancy_desk import parser_service as parser_service_module
from discrepancy_desk.parser_service import (
    assemble_under_test_package,
    load_parser_resources,
)
from discrepancy_desk.parser_worker import sanitized_worker_environment
from discrepancy_desk.vault_backup import (
    create_vault_generation,
    restore_generation_disposable,
    verify_vault_generation,
)
from discrepancy_desk.vault_filesystem import store_package_bytes
from discrepancy_desk.vault_ingestion import admit_bytes, start_intake
from discrepancy_desk.vault_persistence import utc_now
from discrepancy_desk.vault_router import open_registered_vault
from discrepancy_desk.vault_service import provision_vault


def _actor(vault_id: str, key: str) -> ActorContext:
    return ActorContext(
        actor_id="owner-local",
        actor_class="human",
        vault_account_id=vault_id,
        correlation_id=key,
        authentication_source="pytest",
        allowed_operation_class="vault_admin",
    )


def _artifact(opened, *, key: str, content: bytes) -> tuple[str, str]:
    start = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, f"intake:{key}"),
        source_kind="manual_file",
        descriptor_class="file",
        display_label=f"{key}.txt",
        locator=None,
        platform_label="local",
        retention_classification="preservation_compatible",
        policy_basis_reference="synthetic package fixture",
        human_classification_note="disposable package backup proof",
        client_nonce=f"nonce:{key}",
        operation_key=f"intake:{key}",
        expects_bytes=True,
        supplied_filename=f"{key}.txt",
        supplied_media_type="text/plain",
        advisory_byte_size=len(content),
    )
    assert start.acquisition_id and start.upload_authorization_id
    admitted = admit_bytes(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, f"upload:{key}"),
        acquisition_id=start.acquisition_id,
        upload_authorization_id=start.upload_authorization_id,
        operation_key=f"upload:{key}",
        content=content,
        supplied_filename=f"{key}.txt",
        supplied_media_type="text/plain",
    )
    link = opened.connection.execute(
        "SELECT id FROM acquisition_artifact_links WHERE vault_account_id=? AND acquisition_id=?",
        (opened.identity.vault_account_id, start.acquisition_id),
    ).fetchone()
    assert link is not None
    return str(link[0]), admitted.sha256


def _test_owner_admission(opened) -> tuple[str, str, str]:
    vault_id = opened.identity.vault_account_id
    row = opened.connection.execute(
        """SELECT id, parser_definition_id, parser_configuration_version_id,
                  fixture_manifest_sha256, focused_test_evidence_sha256,
                  no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
                  dependency_lock_sha256
        FROM parser_admission_versions
        WHERE vault_account_id=? AND state='under_test'""",
        (vault_id,),
    ).fetchone()
    assert row is not None
    admission_id = "parser-admission-packaging-test-owner-admitted"
    now = utc_now()
    opened.connection.execute(
        """INSERT INTO parser_admission_versions
        (id, vault_account_id, parser_definition_id, parser_configuration_version_id,
         state, fixture_manifest_sha256, focused_test_evidence_sha256,
         no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
         dependency_lock_sha256, admitted_by_actor_id, admitted_at,
         supersedes_admission_id, reason, created_at, created_by_actor_id)
        VALUES (?, ?, ?, ?, 'owner_admitted', ?, ?, ?, ?, ?, 'owner-local', ?, ?,
                'synthetic disposable package backup proof', ?, 'owner-local')""",
        (
            admission_id,
            vault_id,
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
            str(row[7]),
            now,
            str(row[0]),
            now,
        ),
    )
    opened.connection.commit()
    return str(row[1]), str(row[2]), admission_id


def _seed_canonical_synthetic_package(opened) -> tuple[Path, bytes]:
    content = b"alpha\r\n\r\nbeta\r\n"
    link_id, artifact_sha = _artifact(opened, key="package", content=content)
    definition_id, config_id, admission_id = _test_owner_admission(opened)
    package, package_bytes, worker = assemble_under_test_package(
        content,
        vault_account_id=opened.identity.vault_account_id,
        source_artifact_sha256=artifact_sha,
        parser_admission_id=admission_id,
    )
    stored = store_package_bytes(opened.root, package_bytes)
    execution_id = "parser-execution-packaging-test"
    now = utc_now()
    warnings = list(package["warnings"])
    outcome = "success_with_warnings" if warnings else "success"
    state = "succeeded_with_warnings" if warnings else "succeeded"
    opened.connection.execute("BEGIN IMMEDIATE")
    try:
        opened.connection.execute(
            """INSERT INTO parser_executions
            (id, vault_account_id, vault_instance_id, acquisition_artifact_link_id,
             parser_definition_id, parser_configuration_version_id,
             parser_admission_version_id, security_profile_id, input_sha256,
             input_size_bytes, state, terminal_outcome, warning_codes_json,
             started_at, finished_at, worker_receipt_sha256, package_sha256,
             error_code, operation_id, actor_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'owner-local')""",
            (
                execution_id,
                opened.identity.vault_account_id,
                opened.identity.vault_instance_id,
                link_id,
                definition_id,
                config_id,
                admission_id,
                SECURITY_PROFILE_ID,
                artifact_sha,
                len(content),
                state,
                outcome,
                canonical_json(warnings),
                now,
                now,
                sha256_bytes(worker.receipt_bytes),
                stored.sha256,
                "test:canonical-package",
            ),
        )
        package_id = "normalized-package-packaging-test"
        opened.connection.execute(
            """INSERT INTO normalized_packages
            (id, vault_account_id, parser_execution_id, package_schema_version,
             package_sha256, byte_size, storage_relative_path, coverage_sha256,
             warning_codes_json, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'current', ?)""",
            (
                package_id,
                opened.identity.vault_account_id,
                execution_id,
                PACKAGE_SCHEMA_VERSION,
                stored.sha256,
                stored.byte_size,
                stored.storage_relative_path,
                sha256_bytes(canonical_json(package["coverage"])),
                canonical_json(warnings),
                now,
            ),
        )
        document_id = "document-version-packaging-test"
        opened.connection.execute(
            """INSERT INTO document_versions
            (id, vault_account_id, normalized_package_id, source_artifact_sha256,
             parser_execution_id, version_ordinal, state, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 'current', ?)""",
            (
                document_id,
                opened.identity.vault_account_id,
                package_id,
                artifact_sha,
                execution_id,
                now,
            ),
        )
        for element in package["elements"]:
            opened.connection.execute(
                """INSERT INTO elements
                (id, vault_account_id, document_version_id, ordinal, element_kind,
                 source_locator_json, raw_text, normalized_text, content_sha256,
                 warning_codes_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"element-packaging-{element['ordinal']}",
                    opened.identity.vault_account_id,
                    document_id,
                    int(element["ordinal"]),
                    str(element["kind"]),
                    canonical_json(element["source_locator"]),
                    str(element["raw_text"]),
                    str(element["normalized_text"]),
                    str(element["content_sha256"]),
                    canonical_json(element["warnings"]),
                ),
            )
        for region in package["regions"]:
            opened.connection.execute(
                """INSERT INTO regions
                (id, vault_account_id, document_version_id, element_id, ordinal,
                 region_kind, source_locator_json, content_sha256)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?)""",
                (
                    f"region-packaging-{region['ordinal']}",
                    opened.identity.vault_account_id,
                    document_id,
                    int(region["ordinal"]),
                    str(region["kind"]),
                    canonical_json(region["source_locator"]),
                    str(region["content_sha256"]),
                ),
            )
        opened.connection.commit()
    except Exception:
        opened.connection.rollback()
        raise
    return stored.final_path, package_bytes


def _build_packaged_sidecar(project_root: Path) -> Path:
    completed = subprocess.run(
        [sys.executable, "scripts/build_desktop_sidecar.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    executable = (
        project_root
        / "desktop"
        / "src-tauri"
        / "binaries"
        / "discrepancy-desk-backend"
        / "discrepancy-desk-backend.exe"
    )
    assert executable.is_file()
    return executable


def _run_packaged_worker(executable: Path, operation_root: Path, input_bytes: bytes) -> tuple[int, dict[str, object]]:
    resources = load_parser_resources()
    operation_root.mkdir(parents=True)
    input_path = operation_root / "verified-input.bin"
    input_path.write_bytes(input_bytes)
    request = {
        "config_sha256": resources.config_sha256,
        "implementation_sha256": resources.implementation_sha256,
        "output_filename": "candidate-package.json",
        "parser_id": "m06a.text.v1",
        "protocol_version": WORKER_PROTOCOL_VERSION,
        "security_profile_id": SECURITY_PROFILE_ID,
        "verified_input_relative_name": "verified-input.bin",
        "verified_input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "verified_input_size": len(input_bytes),
    }
    request_bytes = canonical_json(request)
    completed = subprocess.run(
        [str(executable), "--m06a-parser-worker"],
        cwd=operation_root,
        input=struct.pack(">Q", len(request_bytes)) + request_bytes,
        capture_output=True,
        check=False,
        timeout=60,
        env=sanitized_worker_environment(),
    )
    receipt = json.loads((operation_root / "worker-receipt.json").read_text(encoding="utf-8"))
    return completed.returncode, receipt


def test_m06a_ht_044_packaged_parser_authority_matches(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    resources = load_parser_resources(project_root)
    implementation = project_root / "src" / "discrepancy_desk" / "parsers" / "plain_text_v1.py"
    assert hashlib.sha256(implementation.read_bytes()).hexdigest() == resources.implementation_sha256
    build_script = (project_root / "scripts" / "build_desktop_sidecar.py").read_text(encoding="utf-8")
    assert "parser_resources" in build_script
    assert "uv.lock" in build_script
    executable = _build_packaged_sidecar(project_root)
    code, receipt = _run_packaged_worker(executable, tmp_path / "packaged-worker", b"packaged\n\ntext\n")
    assert code == 0
    assert receipt["state"] == "succeeded"
    assert receipt["security_profile_id"] == SECURITY_PROFILE_ID
    assert set(receipt["controls"]) >= {
        "socket_denied",
        "dns_denied",
        "subprocess_denied",
        "bounded_filesystem",
        "filesystem_mutation_denied",
        "exec_denied",
        "audit_hook_installed",
        "self_tested_denials",
    }


def test_canonical_package_backup_restore_and_tamper_fail_closed(
    m06a_phase3a_vault, tmp_path: Path
) -> None:
    _, opened = m06a_phase3a_vault
    package_path, package_bytes = _seed_canonical_synthetic_package(opened)
    generation = create_vault_generation(
        opened.connection,
        vault_root=opened.root,
        actor=_actor(opened.identity.vault_account_id, "backup:phase3a-package"),
        migration_head="V0004",
        application_commit="test-phase3a-package",
    )
    verification = verify_vault_generation(
        generation.generation_root,
        expected_vault_account_id=opened.identity.vault_account_id,
        expected_vault_instance_id=opened.identity.vault_instance_id,
        expected_migration_head="V0004",
        authority_connection=opened.connection,
    )
    assert verification["package_count"] == 1
    proof = restore_generation_disposable(
        generation.generation_root,
        tmp_path / "restore-proof",
        expected_vault_account_id=opened.identity.vault_account_id,
        expected_vault_instance_id=opened.identity.vault_instance_id,
        authority_connection=opened.connection,
    )
    assert proof.package_count == 1
    restored = proof.proof_root / package_path.relative_to(opened.root)
    assert restored.read_bytes() == package_bytes

    copied = generation.generation_root / package_path.relative_to(opened.root)
    copied.write_bytes(b"tampered package")
    with pytest.raises(ValueError, match="size mismatch|hash mismatch"):
        verify_vault_generation(
            generation.generation_root,
            expected_migration_head="V0004",
        )


def test_parser_api_is_read_only_and_exposes_no_mutation_routes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source = (project_root / "src" / "discrepancy_desk" / "web.py").read_text(encoding="utf-8")
    assert '@app.get("/desktop-api/v1/vaults/{vault_id}/parsers")' in source
    forbidden = (
        '@app.post("/desktop-api/v1/vaults/{vault_id}/parsers',
        '@app.put("/desktop-api/v1/vaults/{vault_id}/parsers',
        '@app.patch("/desktop-api/v1/vaults/{vault_id}/parsers',
        '@app.delete("/desktop-api/v1/vaults/{vault_id}/parsers',
        "owner_admitted parser button",
    )
    assert not any(value in source for value in forbidden)
    app = (project_root / "desktop" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "Canonical use —" in app
    assert "No parser execution or admission control is available" in app


def test_package_backup_rejects_missing_extra_and_cross_vault_bytes(
    m06a_central_connection, m06a_phase3a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "package-isolation-vaults"
    first_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_phase3a_vault_spec,
        display_name="Package source Vault",
        relative_root="package-source",
        owner_actor_id="owner-local",
        operation_key="package:isolation:first",
    )
    second_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_phase3a_vault_spec,
        display_name="Package target Vault",
        relative_root="package-target",
        owner_actor_id="owner-local",
        operation_key="package:isolation:second",
    )
    with open_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=first_id,
        migration_spec=m06a_phase3a_vault_spec,
    ) as first, open_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=second_id,
        migration_spec=m06a_phase3a_vault_spec,
    ) as second:
        package_path, package_bytes = _seed_canonical_synthetic_package(first)
        package_path.unlink()
        with pytest.raises(
            (FileNotFoundError, ValueError), match="missing|not found|regular file"
        ):
            create_vault_generation(
                first.connection,
                vault_root=first.root,
                actor=_actor(first_id, "backup:missing-package"),
                migration_head="V0004",
                application_commit="test-missing-package",
            )

        cross_relative = package_path.relative_to(first.root)
        cross_target = second.root / cross_relative
        cross_target.parent.mkdir(parents=True, exist_ok=True)
        cross_target.write_bytes(package_bytes)
        with pytest.raises(ValueError, match="package inventory"):
            create_vault_generation(
                second.connection,
                vault_root=second.root,
                actor=_actor(second_id, "backup:cross-vault-package"),
                migration_head="V0004",
                application_commit="test-cross-vault-package",
            )

def test_phase3a_c1_parser_definition_ids_are_tuple_versioned() -> None:
    resources = load_parser_resources()
    current = parser_service_module._candidate_ids(resources)
    changed = parser_service_module._candidate_ids(
        replace(resources, implementation_sha256="0" * 64)
    )
    assert current[0].startswith("parser-definition-m06a-text-v1-")
    assert current[0] != "parser-definition-m06a-text-v1"
    assert current != changed


def test_phase3a_c1_exact_package_document_lineage_and_reuse(
    m06a_phase3a_vault,
) -> None:
    _, opened = m06a_phase3a_vault
    _seed_canonical_synthetic_package(opened)
    vault_id = opened.identity.vault_account_id
    origin = opened.connection.execute(
        "SELECT id FROM parser_executions ORDER BY started_at, id LIMIT 1"
    ).fetchone()[0]
    package_id = opened.connection.execute(
        "SELECT id FROM normalized_packages WHERE parser_execution_id=?", (origin,)
    ).fetchone()[0]
    source_hash = opened.connection.execute(
        "SELECT input_sha256 FROM parser_executions WHERE id=?", (origin,)
    ).fetchone()[0]

    duplicate = "parser-execution-packaging-reuse"
    opened.connection.execute(
        """INSERT INTO parser_executions
        (id, vault_account_id, vault_instance_id, acquisition_artifact_link_id,
         parser_definition_id, parser_configuration_version_id,
         parser_admission_version_id, security_profile_id, input_sha256,
         input_size_bytes, state, terminal_outcome, warning_codes_json,
         started_at, finished_at, worker_receipt_sha256, package_sha256,
         error_code, operation_id, actor_id)
        SELECT ?, vault_account_id, vault_instance_id, acquisition_artifact_link_id,
               parser_definition_id, parser_configuration_version_id,
               parser_admission_version_id, security_profile_id, input_sha256,
               input_size_bytes, state, terminal_outcome, warning_codes_json,
               started_at, finished_at, worker_receipt_sha256, package_sha256,
               error_code, ?, actor_id
        FROM parser_executions WHERE vault_account_id=? AND id=?""",
        (duplicate, "test:canonical-package-reuse", vault_id, origin),
    )
    with pytest.raises(sqlite3.IntegrityError, match="exact execution/package/artifact lineage"):
        opened.connection.execute(
            """INSERT INTO document_versions
            (id, vault_account_id, normalized_package_id, source_artifact_sha256,
             parser_execution_id, version_ordinal, state, created_at)
            VALUES ('document-before-link', ?, ?, ?, ?, 2, 'current', ?)""",
            (vault_id, package_id, source_hash, duplicate, utc_now()),
        )
    opened.connection.execute(
        """INSERT INTO parser_execution_package_links
        (vault_account_id, parser_execution_id, normalized_package_id, created_at)
        VALUES (?, ?, ?, ?)""",
        (vault_id, duplicate, package_id, utc_now()),
    )
    opened.connection.execute(
        """INSERT INTO document_versions
        (id, vault_account_id, normalized_package_id, source_artifact_sha256,
         parser_execution_id, version_ordinal, state, created_at)
        VALUES ('document-reused-package', ?, ?, ?, ?, 2, 'current', ?)""",
        (vault_id, package_id, source_hash, duplicate, utc_now()),
    )
    third = "parser-execution-packaging-third"
    opened.connection.execute(
        """INSERT INTO parser_executions
        (id, vault_account_id, vault_instance_id, acquisition_artifact_link_id,
         parser_definition_id, parser_configuration_version_id,
         parser_admission_version_id, security_profile_id, input_sha256,
         input_size_bytes, state, terminal_outcome, warning_codes_json,
         started_at, finished_at, worker_receipt_sha256, package_sha256,
         error_code, operation_id, actor_id)
        SELECT ?, vault_account_id, vault_instance_id, acquisition_artifact_link_id,
               parser_definition_id, parser_configuration_version_id,
               parser_admission_version_id, security_profile_id, input_sha256,
               input_size_bytes, state, terminal_outcome, warning_codes_json,
               started_at, finished_at, worker_receipt_sha256, package_sha256,
               error_code, ?, actor_id
        FROM parser_executions WHERE vault_account_id=? AND id=?""",
        (third, "test:canonical-package-third", vault_id, origin),
    )
    opened.connection.execute(
        """INSERT INTO parser_execution_package_links
        (vault_account_id, parser_execution_id, normalized_package_id, created_at)
        VALUES (?, ?, ?, ?)""",
        (vault_id, third, package_id, utc_now()),
    )
    with pytest.raises(sqlite3.IntegrityError, match="ordinal already exists"):
        opened.connection.execute(
            """INSERT INTO document_versions
            (id, vault_account_id, normalized_package_id, source_artifact_sha256,
             parser_execution_id, version_ordinal, state, created_at)
            VALUES ('document-duplicate-ordinal', ?, ?, ?, ?, 2, 'current', ?)""",
            (vault_id, package_id, source_hash, third, utc_now()),
        )
    opened.connection.rollback()


def test_phase3a_c1_packaged_identity_bytes_are_mandatory(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    shutil.copytree(Path("parser_resources"), project / "parser_resources")
    fake_module = project / "src" / "discrepancy_desk" / "parser_service.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# synthetic module anchor\n", encoding="utf-8")
    monkeypatch.setattr(parser_service_module, "__file__", str(fake_module))
    monkeypatch.setattr(parser_service_module.sys, "executable", str(project / "bin" / "python.exe"))
    with pytest.raises(FileNotFoundError, match="implementation source bytes"):
        load_parser_resources(project)

    implementation = fake_module.parent / "parsers" / "plain_text_v1.py"
    implementation.parent.mkdir()
    shutil.copyfile(Path("src/discrepancy_desk/parsers/plain_text_v1.py"), implementation)
    with pytest.raises(FileNotFoundError, match="dependency lock bytes"):
        load_parser_resources(project)
