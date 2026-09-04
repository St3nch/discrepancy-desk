"""Content-addressed Vault payload authority."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from discrepancy_desk.errors import ConfigurationError, VaultIntegrityError

_BUFFER_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PayloadRef:
    hash_algorithm: str
    digest: str
    byte_size: int
    media_type: str
    vault_key: str


class Vault:
    """Preserve immutable payloads behind a content-addressed interface."""

    def __init__(self, data_root: Path) -> None:
        if not data_root.is_absolute():
            raise ConfigurationError("Vault data root must be absolute")
        if data_root.exists() and not data_root.is_dir():
            raise ConfigurationError("Vault data root must name a directory")
        self._data_root = data_root
        self._vault_root = data_root / "vault"

    def put_file(
        self,
        source: Path,
        media_type: str,
        *,
        expected_sha256: str | None = None,
        expected_byte_size: int | None = None,
    ) -> PayloadRef:
        if not source.is_file():
            raise ConfigurationError(f"Capture source is not a regular file: {source}")
        with source.open("rb") as stream:
            return self._put_stream(
                stream,
                media_type,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
            )

    def put_bytes(self, payload: bytes, media_type: str) -> PayloadRef:
        with tempfile.SpooledTemporaryFile() as stream:
            stream.write(payload)
            stream.seek(0)
            return self._put_stream(stream, media_type)

    def open(self, ref: PayloadRef) -> BinaryIO:
        path = self._path_for_key(ref.vault_key)
        self._assert_payload(path, ref)
        return path.open("rb")

    def read_bytes(self, ref: PayloadRef) -> bytes:
        with self.open(ref) as stream:
            return stream.read()

    def verify(self, ref: PayloadRef) -> None:
        self._assert_payload(self._path_for_key(ref.vault_key), ref)

    def _put_stream(
        self,
        stream: BinaryIO,
        media_type: str,
        *,
        expected_sha256: str | None = None,
        expected_byte_size: int | None = None,
    ) -> PayloadRef:
        if not media_type or "/" not in media_type:
            raise ConfigurationError("A concrete media type is required")
        staging_root = self._vault_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        descriptor, raw_temp_path = tempfile.mkstemp(prefix="payload-", dir=staging_root)
        temp_path = Path(raw_temp_path)
        digest = hashlib.sha256()
        byte_size = 0
        try:
            with os.fdopen(descriptor, "wb") as target:
                while chunk := stream.read(_BUFFER_SIZE):
                    digest.update(chunk)
                    byte_size += len(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())

            digest_hex = digest.hexdigest()
            digest_mismatch = expected_sha256 is not None and digest_hex != expected_sha256
            size_mismatch = expected_byte_size is not None and byte_size != expected_byte_size
            if digest_mismatch or size_mismatch:
                raise VaultIntegrityError(
                    "Payload does not match its accepted digest and byte size"
                )
            vault_key = f"vault/sha256/{digest_hex[:2]}/{digest_hex}"
            destination = self._data_root / vault_key
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(temp_path, destination)
                destination.chmod(0o444)
            except FileExistsError:
                existing = PayloadRef(
                    hash_algorithm="sha256",
                    digest=digest_hex,
                    byte_size=byte_size,
                    media_type=media_type,
                    vault_key=vault_key,
                )
                self._assert_payload(destination, existing)
            finally:
                temp_path.unlink(missing_ok=True)

            ref = PayloadRef(
                hash_algorithm="sha256",
                digest=digest_hex,
                byte_size=byte_size,
                media_type=media_type,
                vault_key=vault_key,
            )
            self._assert_payload(destination, ref)
            return ref
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _path_for_key(self, vault_key: str) -> Path:
        candidate = self._data_root / vault_key
        try:
            resolved_root = self._vault_root.resolve(strict=False)
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise VaultIntegrityError("Vault reference escapes the configured root") from exc
        return resolved

    @staticmethod
    def _assert_payload(path: Path, ref: PayloadRef) -> None:
        if ref.hash_algorithm != "sha256":
            raise VaultIntegrityError("Unsupported Vault hash algorithm")
        expected_key = f"vault/sha256/{ref.digest[:2]}/{ref.digest}"
        if ref.vault_key != expected_key:
            raise VaultIntegrityError("Vault reference does not match its content address")
        if not path.is_file():
            raise VaultIntegrityError(f"Vault payload is missing: {ref.vault_key}")
        digest = hashlib.sha256()
        byte_size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(_BUFFER_SIZE):
                digest.update(chunk)
                byte_size += len(chunk)
        if byte_size != ref.byte_size or digest.hexdigest() != ref.digest:
            raise VaultIntegrityError(
                f"Vault payload failed integrity verification: {ref.vault_key}"
            )
