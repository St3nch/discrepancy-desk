from __future__ import annotations

from pathlib import Path

import pytest

from discrepancy_desk.config import require_data_root, require_human_database_url
from discrepancy_desk.errors import (
    ConfigurationError,
    DecisionAuthorityError,
    VaultIntegrityError,
)
from discrepancy_desk.vault import Vault


def test_data_root_must_be_absolute() -> None:
    with pytest.raises(ConfigurationError, match="absolute"):
        require_data_root({"DESK_DATA_ROOT": "relative/path"})


def test_human_database_url_never_falls_back_to_app_url() -> None:
    with pytest.raises(DecisionAuthorityError, match="never falls back"):
        require_human_database_url({"DESK_POSTGRES_URL": "postgresql://desk_app@example.test/desk"})


def test_vault_deduplicates_identical_payloads(tmp_path: Path) -> None:
    vault = Vault(tmp_path.resolve())
    first = vault.put_bytes(b"same evidence", "application/octet-stream")
    second = vault.put_bytes(b"same evidence", "application/octet-stream")

    assert first == second
    assert vault.read_bytes(first) == b"same evidence"
    payloads = [path for path in (tmp_path / "vault" / "sha256").rglob("*") if path.is_file()]
    assert len(payloads) == 1


def test_vault_refuses_tampered_payload(tmp_path: Path) -> None:
    vault = Vault(tmp_path.resolve())
    ref = vault.put_bytes(b"authoritative bytes", "application/octet-stream")
    payload_path = tmp_path / ref.vault_key
    payload_path.chmod(0o644)
    payload_path.write_bytes(b"tampered bytes")

    with pytest.raises(VaultIntegrityError, match="integrity"):
        vault.verify(ref)


def test_vault_refuses_reference_outside_configured_root(tmp_path: Path) -> None:
    vault = Vault(tmp_path.resolve())
    ref = vault.put_bytes(b"evidence", "application/octet-stream")
    escaped = type(ref)(
        hash_algorithm=ref.hash_algorithm,
        digest=ref.digest,
        byte_size=ref.byte_size,
        media_type=ref.media_type,
        vault_key="../outside",
    )

    with pytest.raises(VaultIntegrityError, match="escapes"):
        vault.verify(escaped)


def test_vault_refuses_noncanonical_content_address(tmp_path: Path) -> None:
    vault = Vault(tmp_path.resolve())
    ref = vault.put_bytes(b"evidence", "application/octet-stream")
    wrong_key = f"vault/sha256/ff/{ref.digest}"
    wrong_path = tmp_path / wrong_key
    wrong_path.parent.mkdir(parents=True)
    wrong_path.write_bytes(b"evidence")
    noncanonical = type(ref)(
        hash_algorithm=ref.hash_algorithm,
        digest=ref.digest,
        byte_size=ref.byte_size,
        media_type=ref.media_type,
        vault_key=wrong_key,
    )

    with pytest.raises(VaultIntegrityError, match="content address"):
        vault.verify(noncanonical)
