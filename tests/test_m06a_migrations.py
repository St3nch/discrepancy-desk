from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from discrepancy_desk.db import connect_existing
from discrepancy_desk.migration_integrity import (
    MigrationIntegrityError,
    begin_migration_guard,
    dirty_marker_path,
    recover_completed_migration,
    verify_manifest,
)
from discrepancy_desk.migration_runner import run_guarded_upgrade
from discrepancy_desk.migration_spec import MigrationSpec
from discrepancy_desk.vault_registry import get_vault
from discrepancy_desk.vault_router import open_registered_vault, upgrade_registered_vault
from discrepancy_desk.vault_service import provision_vault


def _copy_vault_environment(tmp_path: Path, project_root: Path) -> MigrationSpec:
    project = tmp_path / "project"
    root = project / "vault_migrations"
    shutil.copytree(project_root / "vault_migrations", root)
    return MigrationSpec(
        config_path=root / "alembic.ini",
        migrations_root=root,
        manifest_path=root / "manifest.sha256",
        expected_head="V0002",
        schema_name="m06a-vault",
    )


def _provision(connection, vault_base: Path, vault_spec, root: str, key: str) -> str:
    return provision_vault(
        connection,
        vault_base=vault_base,
        migration_spec=vault_spec,
        display_name=root,
        relative_root=root,
        owner_actor_id="owner-local",
        operation_key=key,
    )


def test_m06a_ht_062_exact_migration_environment_enforced(
    tmp_path: Path, m06a_project_root: Path
) -> None:
    spec = _copy_vault_environment(tmp_path, m06a_project_root)
    assert len(verify_manifest(spec)) == 64

    extra = spec.migrations_root / "versions" / "V9999_unmanifested.py"
    extra.write_text("revision='V9999'\n", encoding="utf-8")
    with pytest.raises(MigrationIntegrityError, match="coverage mismatch"):
        verify_manifest(spec)
    extra.unlink()

    config = spec.config_path
    config.write_text(config.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(MigrationIntegrityError, match="hash mismatch: alembic.ini"):
        verify_manifest(spec)


def test_m06a_ht_063_partial_migration_remains_dirty(tmp_path: Path, m06a_vault_spec) -> None:
    database = tmp_path / "vault.sqlite3"
    with pytest.raises(Exception):
        run_guarded_upgrade(
            database,
            m06a_vault_spec,
            operation_id="partial-V0001",
            target_revision="V9999",
            allow_create=True,
            identity={"vault_account_id": "vault-partial"},
        )
    assert dirty_marker_path(database).is_file()
    with pytest.raises(MigrationIntegrityError, match="dirty"):
        run_guarded_upgrade(
            database,
            m06a_vault_spec,
            operation_id="retry-V0001",
            allow_create=True,
            identity={"vault_account_id": "vault-partial"},
        )


def test_m06a_ht_064_migration_recovery_is_exact(tmp_path: Path, m06a_vault_spec) -> None:
    database = tmp_path / "vault.sqlite3"
    identity = {"vault_account_id": "vault-recovery", "vault_instance_id": "instance-1"}
    run_guarded_upgrade(
        database,
        m06a_vault_spec,
        operation_id="initial-V0001",
        allow_create=True,
        identity=identity,
    )
    begin_migration_guard(
        database,
        operation_id="recover-V0001",
        target_revision=m06a_vault_spec.expected_head,
        spec=m06a_vault_spec,
        from_revision=m06a_vault_spec.expected_head,
        identity=identity,
    )
    with pytest.raises(MigrationIntegrityError, match="identity mismatch"):
        recover_completed_migration(
            database,
            m06a_vault_spec,
            operation_id="recover-V0001",
            identity={"vault_account_id": "wrong"},
        )
    recover_completed_migration(
        database,
        m06a_vault_spec,
        operation_id="recover-V0001",
        identity=identity,
    )
    assert not dirty_marker_path(database).exists()


def test_m06a_ht_065_destructive_downgrade_refused(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    vault_id = _provision(central, vault_base, m06a_vault_spec, "downgrade", "downgrade:65")
    record = get_vault(central, vault_id)
    database = vault_base / record.relative_root / "database" / "vault.sqlite3"
    config = Config(str(m06a_vault_spec.config_path))
    config.set_main_option("script_location", str(m06a_vault_spec.migrations_root))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    with pytest.raises(RuntimeError, match="refusing to downgrade V0004"):
        command.downgrade(config, "base")
    connection = connect_existing(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "V0004"
        assert connection.execute("SELECT count(*) FROM vault_metadata").fetchone()[0] == 1
    finally:
        connection.close()


def test_m06a_ht_095_migration_state_is_per_vault(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    central, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first = _provision(central, vault_base, m06a_vault_spec, "dirty-a", "migration:95a")
    second = _provision(central, vault_base, m06a_vault_spec, "clean-b", "migration:95b")
    first_record = get_vault(central, first)
    first_database = vault_base / first_record.relative_root / "database" / "vault.sqlite3"
    begin_migration_guard(
        first_database,
        operation_id="dirty-only-a",
        target_revision=m06a_vault_spec.expected_head,
        spec=m06a_vault_spec,
        from_revision=m06a_vault_spec.expected_head,
        identity={"vault_account_id": first},
    )
    with pytest.raises(MigrationIntegrityError, match="dirty"):
        open_registered_vault(
            central,
            vault_base=vault_base,
            vault_id=first,
            migration_spec=m06a_vault_spec,
        )
    with open_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=second,
        migration_spec=m06a_vault_spec,
    ) as opened:
        assert opened.connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "V0004"


def test_m06a_ht_102_foundational_backup_schema_exists_by_phase_2(
    m06a_historical_phase2_vault,
) -> None:
    _, opened = m06a_historical_phase2_vault
    head = opened.connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert head == "V0002"
    required = {
        "backup_generations",
        "backup_generation_files",
        "sources",
        "observations",
        "acquisitions",
        "artifact_objects",
        "intake_rejection_receipts",
    }
    actual = {
        str(row[0])
        for row in opened.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert required <= actual


def test_phase2_vault_upgrade_is_human_authorized_audited_and_idempotent(
    m06a_central_connection,
    m06a_historical_v0002_spec,
    tmp_path: Path,
) -> None:
    m06a_vault_spec = m06a_historical_v0002_spec
    central, _ = m06a_central_connection
    previous = MigrationSpec(
        config_path=m06a_vault_spec.config_path,
        migrations_root=m06a_vault_spec.migrations_root,
        manifest_path=m06a_vault_spec.manifest_path,
        expected_head="V0001",
        schema_name=m06a_vault_spec.schema_name,
        version_table=m06a_vault_spec.version_table,
    )
    vault_base = tmp_path / "vaults"
    vault_id = _provision(central, vault_base, previous, "upgrade-vault", "upgrade:create")

    with upgrade_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=vault_id,
        migration_spec=m06a_vault_spec,
        operation_id="upgrade:V0002",
        actor_id="owner-local",
    ) as opened:
        assert opened.connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "V0002"
        assert opened.connection.execute(
            """SELECT count(*) FROM operation_keys
            WHERE operation_type='upgrade_vault_schema' AND operation_key='upgrade:V0002'"""
        ).fetchone()[0] == 1
        assert opened.connection.execute(
            """SELECT count(*) FROM audit_events
            WHERE record_type='vault_migration' AND record_id='upgrade:V0002'"""
        ).fetchone()[0] == 2

    with upgrade_registered_vault(
        central,
        vault_base=vault_base,
        vault_id=vault_id,
        migration_spec=m06a_vault_spec,
        operation_id="upgrade:V0002",
        actor_id="owner-local",
    ) as replay:
        assert replay.connection.execute(
            """SELECT count(*) FROM audit_events
            WHERE record_type='vault_migration' AND record_id='upgrade:V0002'"""
        ).fetchone()[0] == 2

    with pytest.raises(ValueError, match="already at the expected migration head"):
        upgrade_registered_vault(
            central,
            vault_base=vault_base,
            vault_id=vault_id,
            migration_spec=m06a_vault_spec,
            operation_id="upgrade:different",
            actor_id="owner-local",
        )


def test_phase2_vault_upgrade_rejects_disabled_human_actor(
    m06a_central_connection,
    m06a_historical_v0002_spec,
    tmp_path: Path,
) -> None:
    m06a_vault_spec = m06a_historical_v0002_spec
    central, _ = m06a_central_connection
    previous = MigrationSpec(
        config_path=m06a_vault_spec.config_path,
        migrations_root=m06a_vault_spec.migrations_root,
        manifest_path=m06a_vault_spec.manifest_path,
        expected_head="V0001",
        schema_name=m06a_vault_spec.schema_name,
        version_table=m06a_vault_spec.version_table,
    )
    vault_base = tmp_path / "vaults"
    vault_id = _provision(central, vault_base, previous, "disabled-upgrade", "disabled:create")
    record = get_vault(central, vault_id)
    database = vault_base / record.relative_root / "database" / "vault.sqlite3"
    connection = connect_existing(database)
    try:
        connection.execute(
            "UPDATE actors SET status='disabled' WHERE vault_account_id=? AND id='owner-local'",
            (vault_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PermissionError, match="actor is not active"):
        upgrade_registered_vault(
            central,
            vault_base=vault_base,
            vault_id=vault_id,
            migration_spec=m06a_vault_spec,
            operation_id="upgrade:disabled",
            actor_id="owner-local",
        )
    connection = connect_existing(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "V0001"
        assert connection.execute(
            "SELECT count(*) FROM operation_keys WHERE operation_type='upgrade_vault_schema'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_empty_v0002_downgrade_preserves_exact_v0001_schema(
    tmp_path: Path, m06a_historical_v0002_spec
) -> None:
    m06a_vault_spec = m06a_historical_v0002_spec
    v0001_database = tmp_path / "expected-v0001.sqlite3"
    downgraded_database = tmp_path / "downgraded-v0001.sqlite3"

    def config_for(database: Path) -> Config:
        config = Config(str(m06a_vault_spec.config_path))
        config.set_main_option("script_location", str(m06a_vault_spec.migrations_root))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
        return config

    command.upgrade(config_for(v0001_database), "V0001")
    command.upgrade(config_for(downgraded_database), "V0002")
    command.downgrade(config_for(downgraded_database), "V0001")

    def schema(database: Path) -> list[tuple[str, str, str]]:
        connection = connect_existing(database)
        try:
            return [
                (str(row[0]), str(row[1]), str(row[2]))
                for row in connection.execute(
                    """SELECT type, name, sql
                    FROM sqlite_master
                    WHERE name NOT LIKE 'sqlite_%'
                    ORDER BY type, name"""
                )
            ]
        finally:
            connection.close()

    assert schema(downgraded_database) == schema(v0001_database)
