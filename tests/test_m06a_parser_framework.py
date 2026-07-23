from __future__ import annotations

import copy
import hashlib
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.actor_context import ActorContext
from discrepancy_desk.parser_contract import (
    DeterminismFailure,
    PartialOutputFailure,
    SECURITY_PROFILE_ID,
    canonical_json,
    require_deterministic_candidates,
    sha256_bytes,
    validate_candidate_core,
)
from discrepancy_desk.parsers.plain_text_v1 import parse_bytes
from discrepancy_desk.parser_service import (
    TEXT_ADMISSION_CONFIRMATION,
    admit_text_parser,
    assemble_under_test_package,
    list_parser_status,
    load_parser_resources,
    resolve_canonical_parser,
    text_admission_manifest,
)
from discrepancy_desk.migration_integrity import (
    begin_migration_guard,
    recover_completed_migration,
    verify_manifest,
)
from discrepancy_desk.migration_runner import run_guarded_upgrade
from discrepancy_desk.vault_filesystem import store_package_bytes
from discrepancy_desk.vault_ingestion import admit_bytes, start_intake
from discrepancy_desk.vault_persistence import utc_now
from discrepancy_desk.vault_router import open_registered_vault, upgrade_registered_vault
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


def _artifact(opened, *, key: str, content: bytes = b"alpha\n\nbeta\n") -> tuple[str, str]:
    start = start_intake(
        opened.connection,
        actor=_actor(opened.identity.vault_account_id, f"intake:{key}"),
        source_kind="manual_file",
        descriptor_class="file",
        display_label=f"{key}.txt",
        locator=None,
        platform_label="local",
        retention_classification="preservation_compatible",
        policy_basis_reference="synthetic parser fixture",
        human_classification_note="disposable test input",
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
        """SELECT id FROM acquisition_artifact_links
        WHERE vault_account_id=? AND acquisition_id=?""",
        (opened.identity.vault_account_id, start.acquisition_id),
    ).fetchone()
    assert link is not None
    return str(link[0]), admitted.sha256


def _owner_admit_for_disposable_test(opened) -> str:
    vault_id = opened.identity.vault_account_id
    operation_key = f"admit:disposable:{vault_id}"
    result = admit_text_parser(
        opened.connection,
        actor=_actor(vault_id, operation_key),
        operation_key=operation_key,
        confirmation_text=TEXT_ADMISSION_CONFIRMATION,
        expected_manifest=text_admission_manifest(),
    )
    return result.parser_admission_version_id


def _append_admission_state(opened, *, state: str, suffix: str, supersedes: str | None = None) -> str:
    vault_id = opened.identity.vault_account_id
    source = opened.connection.execute(
        """SELECT id, parser_definition_id, parser_configuration_version_id,
                  fixture_manifest_sha256, focused_test_evidence_sha256,
                  no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
                  dependency_lock_sha256
        FROM parser_admission_versions
        WHERE vault_account_id=?
        ORDER BY created_at, id LIMIT 1""",
        (vault_id,),
    ).fetchone()
    assert source is not None
    admission_id = f"parser-admission-test-{suffix}"
    now = utc_now()
    admitted_actor = "owner-local" if state == "owner_admitted" else None
    admitted_at = now if state == "owner_admitted" else None
    opened.connection.execute(
        """INSERT INTO parser_admission_versions
        (id, vault_account_id, parser_definition_id, parser_configuration_version_id,
         state, fixture_manifest_sha256, focused_test_evidence_sha256,
         no_egress_evidence_sha256, packaged_sidecar_evidence_sha256,
         dependency_lock_sha256, admitted_by_actor_id, admitted_at,
         supersedes_admission_id, reason, created_at, created_by_actor_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'owner-local')""",
        (
            admission_id, vault_id, str(source[1]), str(source[2]), state,
            str(source[3]), str(source[4]), str(source[5]), str(source[6]), str(source[7]),
            admitted_actor, admitted_at, supersedes or str(source[0]),
            f"synthetic disposable {state} gate proof", now,
        ),
    )
    opened.connection.commit()
    return admission_id


def _alembic_config(spec, database_path: Path) -> Config:
    config = Config(str(spec.config_path))
    config.set_main_option("script_location", str(spec.migrations_root))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    config.attributes["database_path"] = database_path
    config.attributes["version_table"] = spec.version_table
    return config


def _schema_objects(database_path: Path) -> set[tuple[str, str]]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """SELECT type, name FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%' AND name!='alembic_version'"""
            )
        }
    finally:
        connection.close()


def _security_child(expression: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    project_root = Path(__file__).resolve().parents[1]
    operation = tmp_path / "operation"
    operation.mkdir(parents=True)
    script = f"""
import sys
from pathlib import Path
sys.path.insert(0, {str(project_root / 'src')!r})
from discrepancy_desk.parser_worker import install_security_controls
from discrepancy_desk.parser_contract import SecurityBoundaryViolation
operation=Path({str(operation)!r})
resources=Path({str(project_root / 'parser_resources')!r})
outside=operation.parent / "outside-security-probe.txt"
outside.write_text("synthetic", encoding="utf-8")
install_security_controls(operation_root=operation, resource_root=resources)
try:
    {expression}
except SecurityBoundaryViolation:
    print('DENIED')
else:
    raise SystemExit('operation was not denied')
"""
    return subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def test_m06a_ht_032_runtime_admission_manifest_enforced(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    status = list_parser_status(opened.connection, vault_account_id=vault_id)
    assert len(status) == 1
    assert status[0]["state"] == "under_test"
    assert status[0]["canonical_available"] is False
    assert opened.connection.execute(
        "SELECT count(*) FROM parser_admission_versions WHERE state='owner_admitted'"
    ).fetchone()[0] == 0

    link_id, artifact_sha = _artifact(opened, key="032")
    with pytest.raises(PermissionError, match="no owner-admitted parser"):
        resolve_canonical_parser(
            opened.connection,
            vault_account_id=vault_id,
            acquisition_artifact_link_id=link_id,
        )
    assert opened.connection.execute("SELECT count(*) FROM parser_executions").fetchone()[0] == 0
    assert not any(path.is_file() for path in (opened.root / "packages").rglob("*"))

    admitted_id = _owner_admit_for_disposable_test(opened)
    selected = resolve_canonical_parser(
        opened.connection,
        vault_account_id=vault_id,
        acquisition_artifact_link_id=link_id,
    )
    assert selected.parser_admission_version_id == admitted_id
    assert selected.artifact_sha256 == artifact_sha
    with pytest.raises(ValueError, match="same-Vault artifact"):
        resolve_canonical_parser(
            opened.connection,
            vault_account_id=vault_id,
            acquisition_artifact_link_id="fabricated-link",
        )


def test_m06a_ht_033_socket_egress_denied(tmp_path: Path) -> None:
    completed = _security_child("__import__('socket').socket()", tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "DENIED"


def test_m06a_ht_034_dns_and_http_denied(tmp_path: Path) -> None:
    dns = _security_child("__import__('socket').getaddrinfo('example.com', 443)", tmp_path / "dns")
    assert dns.returncode == 0, dns.stderr
    http = _security_child("__import__('urllib.request', fromlist=['urlopen']).urlopen('https://example.com')", tmp_path / "http")
    assert http.returncode == 0, http.stderr


def test_m06a_ht_035_subprocess_denied(tmp_path: Path) -> None:
    process = _security_child(
        "__import__('subprocess').run(['cmd', '/c', 'echo', 'no'])",
        tmp_path / "process",
    )
    assert process.returncode == 0, process.stderr
    shell = _security_child("__import__('os').system('echo no')", tmp_path / "shell")
    assert shell.returncode == 0, shell.stderr
    escape = _security_child(
        "open(str(operation.parent / 'escape.txt'), 'wb')",
        tmp_path / "filesystem",
    )
    assert escape.returncode == 0, escape.stderr
    low_level = _security_child(
        "__import__('os').open(operation.parent / 'low-level.txt', "
        "__import__('os').O_WRONLY | __import__('os').O_CREAT | __import__('os').O_TRUNC)",
        tmp_path / "low-level",
    )
    assert low_level.returncode == 0, low_level.stderr
    remove = _security_child(
        "__import__('os').remove(outside)",
        tmp_path / "remove",
    )
    assert remove.returncode == 0, remove.stderr
    rename = _security_child(
        "__import__('os').rename(outside, operation.parent / 'renamed.txt')",
        tmp_path / "rename",
    )
    assert rename.returncode == 0, rename.stderr
    execute = _security_child(
        "__import__('os').execv(str(operation / 'missing.exe'), ['missing.exe'])",
        tmp_path / "exec",
    )
    assert execute.returncode == 0, execute.stderr


def test_m06a_ht_039_package_is_deterministic(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    admission = opened.connection.execute(
        "SELECT id FROM parser_admission_versions WHERE state='under_test'"
    ).fetchone()[0]
    content = b"alpha\r\n\r\nbeta\r\n"
    source_hash = hashlib.sha256(content).hexdigest()
    first, first_bytes, first_worker = assemble_under_test_package(
        content,
        vault_account_id=opened.identity.vault_account_id,
        source_artifact_sha256=source_hash,
        parser_admission_id=str(admission),
    )
    second, second_bytes, second_worker = assemble_under_test_package(
        content,
        vault_account_id=opened.identity.vault_account_id,
        source_artifact_sha256=source_hash,
        parser_admission_id=str(admission),
    )
    assert first == second
    assert first_bytes == second_bytes
    assert require_deterministic_candidates(first_bytes, second_bytes) == sha256_bytes(
        first_bytes
    )
    with pytest.raises(DeterminismFailure, match="different candidate bytes"):
        require_deterministic_candidates(first_bytes, second_bytes + b" ")
    assert first_worker.receipt["state"] == second_worker.receipt["state"] == "succeeded"


def test_m06a_ht_040_execution_receipt_separate_from_package(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    admission = str(
        opened.connection.execute(
            "SELECT id FROM parser_admission_versions WHERE state='under_test'"
        ).fetchone()[0]
    )
    content = b"receipt separation"
    package, package_bytes, worker = assemble_under_test_package(
        content,
        vault_account_id=opened.identity.vault_account_id,
        source_artifact_sha256=hashlib.sha256(content).hexdigest(),
        parser_admission_id=admission,
    )
    receipt = copy.deepcopy(worker.receipt)
    receipt["started_at"] = "different-run"
    assert canonical_json(receipt) != worker.receipt_bytes
    assert canonical_json(package) == package_bytes
    forbidden = {"started_at", "finished_at", "operation_id", "pid", "hostname"}
    assert forbidden.isdisjoint(package)


def test_m06a_ht_041_silent_partial_output_fails() -> None:
    candidate = {
        "encoding": "utf-8",
        "line_ending_profile": "none",
        "coverage": {
            "input_byte_count": 4,
            "consumed_byte_ranges": [[0, 3]],
            "decoded_character_count": 4,
            "source_line_count": 1,
            "emitted_element_count": 0,
            "emitted_region_count": 0,
            "complete": True,
        },
        "elements": [],
        "regions": [],
        "warnings": [],
    }
    with pytest.raises(PartialOutputFailure, match="cover the input exactly"):
        validate_candidate_core(candidate, input_bytes=b"abcd")
    candidate["coverage"]["consumed_byte_ranges"] = [[0, 4]]
    candidate["coverage"]["complete"] = False
    with pytest.raises(PartialOutputFailure, match="complete input"):
        validate_candidate_core(candidate, input_bytes=b"abcd")

    omitted = parse_bytes(b"abcd")
    omitted["elements"][0]["source_locator"]["source_byte_start"] = 1
    omitted["elements"][0]["source_locator"]["source_character_start"] = 1
    omitted["elements"][0]["raw_text"] = "bcd"
    omitted["elements"][0]["normalized_text"] = "bcd"
    omitted["elements"][0]["content_sha256"] = sha256_bytes(b"bcd")
    with pytest.raises(PartialOutputFailure, match="gap or overlap"):
        validate_candidate_core(omitted, input_bytes=b"abcd")


def test_m06a_ht_106_database_quarantine_creates_no_second_truth_store(
    m06a_phase3a_vault,
) -> None:
    _, opened = m06a_phase3a_vault
    package_bytes = canonical_json({"synthetic": "package"})
    stored = store_package_bytes(opened.root, package_bytes)
    assert stored.storage_relative_path.startswith("packages/sha256/")
    assert stored.final_path.is_file()
    assert not (opened.root / "quarantine").exists()
    assert not (opened.root / "packages" / "quarantine").exists()
    second = store_package_bytes(opened.root, package_bytes)
    assert second.reused_existing is True


def test_under_test_execution_leaves_no_canonical_vault_bytes(m06a_phase3a_vault) -> None:
    _, opened = m06a_phase3a_vault
    before = {path.relative_to(opened.root).as_posix() for path in opened.root.rglob("*") if path.is_file()}
    resources = load_parser_resources()
    admission = str(
        opened.connection.execute(
            "SELECT id FROM parser_admission_versions WHERE state='under_test'"
        ).fetchone()[0]
    )
    content = b"temporary only"
    _, _, worker = assemble_under_test_package(
        content,
        vault_account_id=opened.identity.vault_account_id,
        source_artifact_sha256=hashlib.sha256(content).hexdigest(),
        parser_admission_id=admission,
    )
    after = {path.relative_to(opened.root).as_posix() for path in opened.root.rglob("*") if path.is_file()}
    assert worker.exit_code == 0
    assert before == after
    assert resources.parser_tuple().security_profile_id == SECURITY_PROFILE_ID


@pytest.mark.parametrize(
    "state",
    ["candidate", "suspended", "revoked", "retired", "prohibited"],
)
def test_non_admitted_parser_states_fail_before_worker_launch(
    m06a_phase3a_vault, state: str
) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    link_id, _ = _artifact(opened, key=f"state-{state}")
    _append_admission_state(opened, state=state, suffix=state)
    with pytest.raises(PermissionError, match="no owner-admitted parser"):
        resolve_canonical_parser(
            opened.connection,
            vault_account_id=vault_id,
            acquisition_artifact_link_id=link_id,
        )
    assert opened.connection.execute("SELECT count(*) FROM parser_executions").fetchone()[0] == 0
    assert not any(path.is_file() for path in (opened.root / "packages").rglob("*"))


def test_mismatched_and_ambiguous_admission_fail_before_worker_launch(
    m06a_phase3a_vault, monkeypatch
) -> None:
    _, opened = m06a_phase3a_vault
    vault_id = opened.identity.vault_account_id
    link_id, _ = _artifact(opened, key="mismatch")
    initial_id = str(
        opened.connection.execute(
            "SELECT id FROM parser_admission_versions WHERE state='under_test'"
        ).fetchone()[0]
    )
    _append_admission_state(
        opened, state="owner_admitted", suffix="ambiguous-a", supersedes=initial_id
    )
    _append_admission_state(
        opened, state="owner_admitted", suffix="ambiguous-b", supersedes=initial_id
    )
    with pytest.raises(PermissionError, match="no owner-admitted parser"):
        resolve_canonical_parser(
            opened.connection,
            vault_account_id=vault_id,
            acquisition_artifact_link_id=link_id,
        )

    opened.connection.execute(
        "DROP TRIGGER parser_admission_versions_no_delete"
    )
    opened.connection.execute(
        "DELETE FROM parser_admission_versions WHERE id='parser-admission-test-ambiguous-b'"
    )
    opened.connection.commit()
    resources = load_parser_resources()
    monkeypatch.setattr(
        "discrepancy_desk.parser_service.load_parser_resources",
        lambda project_root=None: replace(resources, implementation_sha256="0" * 64),
    )
    with pytest.raises(PermissionError, match="no owner-admitted parser"):
        resolve_canonical_parser(
            opened.connection,
            vault_account_id=vault_id,
            acquisition_artifact_link_id=link_id,
        )
    assert opened.connection.execute("SELECT count(*) FROM parser_executions").fetchone()[0] == 0


def test_wrong_vault_and_retention_ineligible_inputs_fail_before_worker(
    m06a_central_connection, m06a_phase3a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "state-vaults"
    first_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_phase3a_vault_spec,
        display_name="First parser Vault",
        relative_root="first-parser-vault",
        owner_actor_id="owner-local",
        operation_key="phase3a:state:first",
    )
    second_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_phase3a_vault_spec,
        display_name="Second parser Vault",
        relative_root="second-parser-vault",
        owner_actor_id="owner-local",
        operation_key="phase3a:state:second",
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
        first_link, _ = _artifact(first, key="wrong-vault")
        _owner_admit_for_disposable_test(first)
        _owner_admit_for_disposable_test(second)
        with pytest.raises(ValueError, match="same-Vault artifact"):
            resolve_canonical_parser(
                second.connection,
                vault_account_id=second_id,
                acquisition_artifact_link_id=first_link,
            )

        source = first.connection.execute(
            """SELECT acquisition_id, artifact_object_id, receipt_sha256
            FROM acquisition_artifact_links WHERE id=?""",
            (first_link,),
        ).fetchone()
        assert source is not None
        denied_rights_id = "rights-retention-parser-deny"
        first.connection.execute(
            """INSERT INTO rights_retention_versions
            (id, vault_account_id, retention_eligible, retention_deadline,
             internal_retrieval_eligible, context_run_eligible, export_eligible,
             internal_projection_eligible, public_projection_eligible,
             quotation_redistribution_eligible, policy_basis,
             human_classification_note, reviewed_by_actor_id, reviewed_at)
            VALUES (?, ?, 'deny', NULL, 'deny', 'deny', 'deny', 'deny', 'deny',
                    'deny', 'synthetic denial proof', 'not eligible', 'owner-local', ?)""",
            (denied_rights_id, first_id, utc_now()),
        )
        denied_link = "artifact-link-parser-denied-rights"
        first.connection.execute(
            """INSERT INTO acquisition_artifact_links
            (id, vault_account_id, acquisition_id, artifact_object_id, role,
             supplied_filename, supplied_media_type, rights_retention_version_id,
             receipt_sha256, linked_at)
            VALUES (?, ?, ?, ?, 'supporting', 'denied.txt', 'text/plain', ?, ?, ?)""",
            (
                denied_link,
                first_id,
                str(source[0]),
                str(source[1]),
                denied_rights_id,
                str(source[2]),
                utc_now(),
            ),
        )
        first.connection.commit()
        with pytest.raises(PermissionError, match="preservation-compatible"):
            resolve_canonical_parser(
                first.connection,
                vault_account_id=first_id,
                acquisition_artifact_link_id=denied_link,
            )
        assert first.connection.execute("SELECT count(*) FROM parser_executions").fetchone()[0] == 0
        assert second.connection.execute("SELECT count(*) FROM parser_executions").fetchone()[0] == 0


def test_m06a_phase3a_fresh_two_vaults_and_populated_v0002_upgrade(
    m06a_central_connection,
    m06a_historical_v0002_spec,
    m06a_phase3a_vault_spec,
    tmp_path: Path,
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "migration-vaults"
    fresh_ids = []
    for ordinal in (1, 2):
        fresh_ids.append(
            provision_vault(
                central,
                vault_base=vault_base,
                migration_spec=m06a_phase3a_vault_spec,
                display_name=f"Fresh V0004 {ordinal}",
                relative_root=f"fresh-v0004-{ordinal}",
                owner_actor_id="owner-local",
                operation_key=f"phase3a-c1:fresh:{ordinal}",
            )
        )
    database_paths: list[Path] = []
    for vault_id in fresh_ids:
        with open_registered_vault(
            central,
            vault_base=vault_base,
            vault_id=vault_id,
            migration_spec=m06a_phase3a_vault_spec,
        ) as opened:
            database_paths.append(opened.database_path)
            assert opened.connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0] == "V0004"
            state = opened.connection.execute(
                """SELECT state FROM parser_admission_versions
                ORDER BY created_at DESC, id DESC LIMIT 1"""
            ).fetchone()[0]
            assert state == "under_test"
    assert database_paths[0] != database_paths[1]

    upgrade_id = provision_vault(
        central,
        vault_base=vault_base,
        migration_spec=m06a_historical_v0002_spec,
        display_name="Populated V0002",
        relative_root="populated-v0002",
        owner_actor_id="owner-local",
        operation_key="phase3a-c1:upgrade:create",
    )
    with open_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=upgrade_id,
        migration_spec=m06a_historical_v0002_spec,
    ) as old:
        _artifact(old, key="before-upgrade", content=b"preserved before upgrade")
        artifact_count = old.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0]
    with upgrade_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=upgrade_id,
        migration_spec=m06a_phase3a_vault_spec,
        operation_id="phase3a-c1:upgrade:v0004",
        actor_id="owner-local",
    ) as upgraded:
        assert upgraded.connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "V0004"
        assert upgraded.connection.execute("SELECT count(*) FROM artifact_objects").fetchone()[0] == artifact_count
        assert upgraded.connection.execute(
            "SELECT count(*) FROM parser_execution_package_links"
        ).fetchone()[0] == 0
        assert list_parser_status(
            upgraded.connection,
            vault_account_id=upgraded.identity.vault_account_id,
        )[0]["state"] == "under_test"


def test_m06a_phase3a_empty_downgrade_parity_and_populated_refusal(
    m06a_phase3a_vault_spec,
    m06a_historical_v0003_spec,
    m06a_phase3a_vault,
    tmp_path: Path,
) -> None:
    empty_v0004 = tmp_path / "empty-v0004.sqlite3"
    empty_v0003 = tmp_path / "empty-v0003.sqlite3"
    run_guarded_upgrade(
        empty_v0004,
        m06a_phase3a_vault_spec,
        operation_id="phase3a-c1:empty-v0004",
        allow_create=True,
    )
    run_guarded_upgrade(
        empty_v0003,
        m06a_historical_v0003_spec,
        operation_id="phase3a-c1:empty-v0003",
        allow_create=True,
    )
    command.downgrade(_alembic_config(m06a_phase3a_vault_spec, empty_v0004), "V0003")
    assert _schema_objects(empty_v0004) == _schema_objects(empty_v0003)

    _, opened = m06a_phase3a_vault
    with pytest.raises(RuntimeError, match="refusing to downgrade V0004"):
        command.downgrade(
            _alembic_config(m06a_phase3a_vault_spec, opened.database_path), "V0003"
        )
    opened.connection.rollback()
    assert opened.connection.execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()[0] == "V0004"


def test_m06a_phase3a_dirty_migration_exact_recovery(
    m06a_historical_v0003_spec, m06a_phase3a_vault_spec, tmp_path: Path
) -> None:
    database_path = tmp_path / "dirty-v0004.sqlite3"
    run_guarded_upgrade(
        database_path,
        m06a_historical_v0003_spec,
        operation_id="phase3a-c1:dirty-base",
        allow_create=True,
    )
    operation_id = "phase3a-c1:dirty-recovery"
    begin_migration_guard(
        database_path,
        operation_id=operation_id,
        target_revision="V0004",
        spec=m06a_phase3a_vault_spec,
        from_revision="V0003",
        identity={},
        manifest_sha256=verify_manifest(m06a_phase3a_vault_spec),
    )
    command.upgrade(_alembic_config(m06a_phase3a_vault_spec, database_path), "V0004")
    with pytest.raises(Exception, match="dirty"):
        run_guarded_upgrade(
            database_path,
            m06a_phase3a_vault_spec,
            operation_id="phase3a-c1:blocked-while-dirty",
            allow_create=False,
        )
    recover_completed_migration(
        database_path,
        m06a_phase3a_vault_spec,
        operation_id=operation_id,
        identity={},
    )
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "V0004"
    finally:
        connection.close()
