from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from discrepancy_desk.vault_identity import (
    MARKER_NAME,
    open_existing_vault,
    resolve_vault_root,
)
from discrepancy_desk.vault_registry import (
    VaultRegistryRecord,
    bind_owned_account,
    get_vault,
    require_active_binding,
)
from discrepancy_desk.vault_router import open_registered_vault
from discrepancy_desk.vault_service import provision_vault


def _seed_account(
    connection: sqlite3.Connection,
    account_id: str,
    *,
    platform: str = "x",
) -> None:
    connection.execute(
        "INSERT INTO owned_accounts VALUES (?, ?, ?, ?, 1)",
        (account_id, platform, f"external-{account_id}", account_id),
    )
    connection.commit()


def _provision(
    connection: sqlite3.Connection,
    vault_base: Path,
    vault_spec,
    *,
    root: str,
    accounts: tuple[str, ...] = (),
    key: str,
) -> str:
    return provision_vault(
        connection,
        vault_base=vault_base,
        migration_spec=vault_spec,
        display_name=f"Brand {root}",
        relative_root=root,
        owner_actor_id="owner-local",
        operation_key=key,
        owned_account_ids=accounts,
    )


def test_m06a_ht_001_vault_isolation(m06a_central_connection, m06a_vault_spec, tmp_path: Path) -> None:
    connection, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first = _provision(connection, vault_base, m06a_vault_spec, root="brand-a", key="vault:a")
    second = _provision(connection, vault_base, m06a_vault_spec, root="brand-b", key="vault:b")

    with open_registered_vault(
        connection, vault_base=vault_base, vault_id=first, migration_spec=m06a_vault_spec
    ) as opened_first:
        assert opened_first.identity.vault_account_id == first
        first_db = opened_first.database_path
    with open_registered_vault(
        connection, vault_base=vault_base, vault_id=second, migration_spec=m06a_vault_spec
    ) as opened_second:
        assert opened_second.identity.vault_account_id == second
        second_db = opened_second.database_path
    assert first_db != second_db


def test_m06a_ht_002_wrong_database_rejected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first = _provision(connection, vault_base, m06a_vault_spec, root="brand-a", key="wrong-db:a")
    second = _provision(connection, vault_base, m06a_vault_spec, root="brand-b", key="wrong-db:b")
    first_record = get_vault(connection, first)
    second_record = get_vault(connection, second)
    first_db = vault_base / first_record.relative_root / "database" / "vault.sqlite3"
    second_db = vault_base / second_record.relative_root / "database" / "vault.sqlite3"
    shutil.copy2(second_db, first_db)

    with pytest.raises(ValueError, match="marker and database identity mismatch"):
        open_existing_vault(
            vault_base=vault_base,
            registry=first_record,
            migration_spec=m06a_vault_spec,
        )


def test_m06a_ht_003_marker_tamper_rejected(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    vault_id = _provision(connection, vault_base, m06a_vault_spec, root="marker", key="marker:1")
    record = get_vault(connection, vault_id)
    marker = vault_base / record.relative_root / MARKER_NAME
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["identity_fingerprint"] = "0" * 64
    marker.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        open_existing_vault(
            vault_base=vault_base,
            registry=record,
            migration_spec=m06a_vault_spec,
        )


def test_m06a_ht_004_open_never_creates_database(m06a_vault_spec, tmp_path: Path) -> None:
    vault_base = tmp_path / "vaults"
    registry = VaultRegistryRecord(
        vault_id="vault-missing",
        display_name="Missing",
        relative_root="missing",
        vault_instance_id="instance-missing",
        expected_identity_fingerprint="0" * 64,
        registry_state="registered",
    )
    with pytest.raises(FileNotFoundError):
        open_existing_vault(
            vault_base=vault_base,
            registry=registry,
            migration_spec=m06a_vault_spec,
        )
    assert not vault_base.exists()


@pytest.mark.parametrize(
    "relative_root",
    ("../escape", "/absolute", "C:\\drive", "\\\\server\\share", "nested/../../escape"),
)
def test_m06a_ht_005_path_traversal_rejected(tmp_path: Path, relative_root: str) -> None:
    with pytest.raises(ValueError):
        resolve_vault_root(tmp_path / "vaults", relative_root, must_exist=False)


def test_m06a_ht_006_windows_name_and_case_rules(tmp_path: Path) -> None:
    vault_base = tmp_path / "vaults"
    vault_base.mkdir()
    (vault_base / "Desk").mkdir()
    for invalid in ("CON", "NUL.txt", "trailing.", "trailing ", "bad:name"):
        with pytest.raises(ValueError):
            resolve_vault_root(vault_base, invalid, must_exist=False)
    with pytest.raises(ValueError, match="case-insensitive collision"):
        resolve_vault_root(vault_base, "desk", must_exist=True)


def test_m06a_ht_007_reparse_points_rejected(tmp_path: Path) -> None:
    vault_base = tmp_path / "vaults"
    vault_base.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    link = vault_base / "linked"
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        pytest.fail(f"real symlink fixture could not be created: {exc}")
    with pytest.raises(ValueError, match="reparse point"):
        resolve_vault_root(vault_base, "linked", must_exist=True)


def test_m06a_ht_008_platform_binding_required(m06a_central_connection) -> None:
    connection, _ = m06a_central_connection
    _seed_account(connection, "acct-unbound")
    with pytest.raises(ValueError, match="not actively bound"):
        require_active_binding(
            connection,
            vault_id="vault-fabricated",
            owned_account_id="acct-unbound",
        )


def test_m06a_ht_088_brand_vault_binds_multiple_platform_accounts(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    _seed_account(connection, "acct-x", platform="x")
    _seed_account(connection, "acct-truth", platform="truth_social")
    vault_id = _provision(
        connection,
        tmp_path / "vaults",
        m06a_vault_spec,
        root="discrepancy-desk",
        accounts=("acct-x", "acct-truth"),
        key="multi-platform",
    )
    rows = connection.execute(
        """SELECT owned_account_id FROM vault_account_owned_accounts
        WHERE vault_id=? AND binding_state='active' ORDER BY owned_account_id""",
        (vault_id,),
    ).fetchall()
    assert [str(row[0]) for row in rows] == ["acct-truth", "acct-x"]
    assert connection.execute("SELECT count(*) FROM vault_registry").fetchone()[0] == 1


def test_m06a_ht_089_platform_account_cannot_select_or_create_vault(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    _seed_account(connection, "acct-x")
    with pytest.raises(ValueError, match="unknown Vault"):
        open_registered_vault(
            connection,
            vault_base=tmp_path / "vaults",
            vault_id="acct-x",
            migration_spec=m06a_vault_spec,
        )
    assert not (tmp_path / "vaults").exists()


def test_m06a_ht_090_wrong_brand_binding_fails(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    _seed_account(connection, "acct-x")
    vault_base = tmp_path / "vaults"
    first = _provision(
        connection, vault_base, m06a_vault_spec,
        root="brand-a", accounts=("acct-x",), key="binding:a",
    )
    second = _provision(connection, vault_base, m06a_vault_spec, root="brand-b", key="binding:b")
    assert first != second
    with pytest.raises(sqlite3.IntegrityError):
        bind_owned_account(
            connection,
            vault_id=second,
            owned_account_id="acct-x",
            actor_id="owner-local",
        )


def test_m06a_ht_093_each_physical_vault_has_own_sqlite_file(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first = _provision(connection, vault_base, m06a_vault_spec, root="one", key="sqlite:one")
    second = _provision(connection, vault_base, m06a_vault_spec, root="two", key="sqlite:two")
    paths = {
        (vault_base / get_vault(connection, vault_id).relative_root / "database" / "vault.sqlite3").resolve()
        for vault_id in (first, second)
    }
    assert len(paths) == 2
    assert all(path.is_file() for path in paths)


def test_m06a_ht_094_wrong_registry_database_mapping_fails(
    m06a_central_connection, m06a_vault_spec, tmp_path: Path
) -> None:
    connection, _ = m06a_central_connection
    vault_base = tmp_path / "vaults"
    first = _provision(connection, vault_base, m06a_vault_spec, root="one", key="mapping:one")
    second = _provision(connection, vault_base, m06a_vault_spec, root="two", key="mapping:two")
    first_record = get_vault(connection, first)
    second_record = get_vault(connection, second)
    wrong = VaultRegistryRecord(
        vault_id=first_record.vault_id,
        display_name=first_record.display_name,
        relative_root=second_record.relative_root,
        vault_instance_id=first_record.vault_instance_id,
        expected_identity_fingerprint=first_record.expected_identity_fingerprint,
        registry_state="registered",
    )
    with pytest.raises(ValueError, match="registry and marker identity mismatch"):
        open_existing_vault(
            vault_base=vault_base,
            registry=wrong,
            migration_spec=m06a_vault_spec,
        )
