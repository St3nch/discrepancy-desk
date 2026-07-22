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
from discrepancy_desk.vault_router import open_registered_vault
from discrepancy_desk.vault_service import provision_vault


def _copy_vault_environment(tmp_path: Path, project_root: Path) -> MigrationSpec:
    project = tmp_path / "project"
    root = project / "vault_migrations"
    shutil.copytree(project_root / "vault_migrations", root)
    return MigrationSpec(
        config_path=root / "alembic.ini",
        migrations_root=root,
        manifest_path=root / "manifest.sha256",
        expected_head="V0001",
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
    with pytest.raises(RuntimeError, match="refusing to downgrade V0001"):
        command.downgrade(config, "base")
    connection = connect_existing(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "V0001"
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
        assert opened.connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "V0001"
