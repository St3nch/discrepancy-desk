from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MigrationSpec:
    config_path: Path
    migrations_root: Path
    manifest_path: Path
    expected_head: str
    schema_name: str
    version_table: str = "alembic_version"

    def resolved(self) -> "MigrationSpec":
        return MigrationSpec(
            config_path=self.config_path.resolve(),
            migrations_root=self.migrations_root.resolve(),
            manifest_path=self.manifest_path.resolve(),
            expected_head=self.expected_head,
            schema_name=self.schema_name,
            version_table=self.version_table,
        )


def central_migration_spec(project_root: Path, migrations_root: Path | None = None) -> MigrationSpec:
    root = (migrations_root or project_root / "migrations").resolve()
    return MigrationSpec(
        config_path=(project_root / "alembic.ini").resolve(),
        migrations_root=root,
        manifest_path=(root / "manifest.sha256").resolve(),
        expected_head="0005",
        schema_name="central-control-room",
    )


def vault_migration_spec(project_root: Path, migrations_root: Path | None = None) -> MigrationSpec:
    root = (migrations_root or project_root / "vault_migrations").resolve()
    return MigrationSpec(
        config_path=(root / "alembic.ini").resolve(),
        migrations_root=root,
        manifest_path=(root / "manifest.sha256").resolve(),
        expected_head="V0001",
        schema_name="m06a-vault",
    )
