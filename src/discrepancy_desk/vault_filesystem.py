from __future__ import annotations

import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024


class ArtifactLimitExceeded(ValueError):
    pass


class ArtifactIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StagedArtifact:
    sha256: str
    byte_size: int
    storage_relative_path: str
    final_path: Path
    operation_root: Path
    temporary_path: Path


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    sha256: str
    byte_size: int
    storage_relative_path: str
    final_path: Path
    reused_existing: bool


def _is_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None and isjunction(path):
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def reject_reparse_chain(path: Path, *, stop: Path | None = None) -> None:
    current = path
    while True:
        if current.exists() and _is_reparse(current):
            raise ArtifactIntegrityError("Vault artifact path contains a reparse point")
        if stop is not None and current == stop:
            return
        if current.parent == current:
            return
        current = current.parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_relative_path(sha256: str) -> str:
    normalized = sha256.lower()
    if len(normalized) != 64 or any(value not in "0123456789abcdef" for value in normalized):
        raise ValueError("artifact SHA-256 is invalid")
    return f"objects/sha256/{normalized[:2]}/{normalized[2:4]}/{normalized}"


def _prepare_operation_temp(vault_root: Path, operation_id: str) -> tuple[Path, Path]:
    if not operation_id or any(value in operation_id for value in ("/", "\\", ":", "..")):
        raise ValueError("artifact operation ID is invalid")
    temp_base = vault_root / "temp"
    reject_reparse_chain(temp_base, stop=vault_root)
    operation_root = temp_base / operation_id
    operation_root.mkdir(parents=False, exist_ok=False)
    reject_reparse_chain(operation_root, stop=vault_root)
    temporary = operation_root / "candidate.bin"
    return operation_root, temporary


def _verify_existing(path: Path, *, expected_sha256: str, expected_size: int) -> None:
    if not path.is_file() or _is_reparse(path):
        raise ArtifactIntegrityError("existing artifact path is not a regular file")
    if path.stat().st_size != expected_size:
        raise ArtifactIntegrityError("existing artifact size does not match its content address")
    if sha256_file(path) != expected_sha256:
        raise ArtifactIntegrityError("existing artifact bytes do not match their content address")


def _remove_operation_root(operation_root: Path, temporary: Path) -> None:
    temporary.unlink(missing_ok=True)
    try:
        operation_root.rmdir()
    except OSError:
        pass


def stage_stream(
    vault_root: Path,
    *,
    operation_id: str,
    stream: BinaryIO,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> StagedArtifact:
    if max_bytes <= 0 or max_bytes > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact byte limit is outside the admitted ceiling")
    reject_reparse_chain(vault_root)
    operation_root, temporary = _prepare_operation_temp(vault_root, operation_id)
    digest = hashlib.sha256()
    byte_size = 0
    try:
        with temporary.open("xb") as destination:
            while True:
                chunk = stream.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, (bytes, bytearray)):
                    raise TypeError("artifact stream returned non-byte content")
                byte_size += len(chunk)
                if byte_size > max_bytes:
                    raise ArtifactLimitExceeded("artifact exceeds the 64 MiB intake ceiling")
                destination.write(chunk)
                digest.update(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        artifact_sha256 = digest.hexdigest()
        relative = object_relative_path(artifact_sha256)
        final_path = vault_root / Path(relative)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(final_path.parent, stop=vault_root)
        if final_path.exists():
            _verify_existing(
                final_path,
                expected_sha256=artifact_sha256,
                expected_size=byte_size,
            )
        return StagedArtifact(
            sha256=artifact_sha256,
            byte_size=byte_size,
            storage_relative_path=relative,
            final_path=final_path,
            operation_root=operation_root,
            temporary_path=temporary,
        )
    except Exception:
        _remove_operation_root(operation_root, temporary)
        raise


def discard_staged(staged: StagedArtifact) -> None:
    _remove_operation_root(staged.operation_root, staged.temporary_path)


def finalize_staged(vault_root: Path, staged: StagedArtifact) -> StoredArtifact:
    reject_reparse_chain(vault_root)
    reject_reparse_chain(staged.final_path.parent, stop=vault_root)
    reused = False
    try:
        if staged.final_path.exists():
            _verify_existing(
                staged.final_path,
                expected_sha256=staged.sha256,
                expected_size=staged.byte_size,
            )
            reused = True
        else:
            try:
                os.link(staged.temporary_path, staged.final_path)
            except FileExistsError:
                _verify_existing(
                    staged.final_path,
                    expected_sha256=staged.sha256,
                    expected_size=staged.byte_size,
                )
                reused = True
            except OSError as exc:
                if staged.final_path.exists():
                    _verify_existing(
                        staged.final_path,
                        expected_sha256=staged.sha256,
                        expected_size=staged.byte_size,
                    )
                    reused = True
                else:
                    raise ArtifactIntegrityError("artifact finalization failed") from exc
        _verify_existing(
            staged.final_path,
            expected_sha256=staged.sha256,
            expected_size=staged.byte_size,
        )
        return StoredArtifact(
            sha256=staged.sha256,
            byte_size=staged.byte_size,
            storage_relative_path=staged.storage_relative_path,
            final_path=staged.final_path,
            reused_existing=reused,
        )
    finally:
        discard_staged(staged)


def store_stream(
    vault_root: Path,
    *,
    operation_id: str,
    stream: BinaryIO,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> StoredArtifact:
    staged = stage_stream(
        vault_root,
        operation_id=operation_id,
        stream=stream,
        max_bytes=max_bytes,
    )
    return finalize_staged(vault_root, staged)


def copy_regular_no_overwrite(source: Path, destination: Path, *, root: Path) -> None:
    if not source.is_file() or _is_reparse(source):
        raise ArtifactIntegrityError("backup source is not a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    reject_reparse_chain(destination.parent, stop=root)
    if destination.exists():
        raise FileExistsError(destination)
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, length=READ_CHUNK_BYTES)
        output_stream.flush()
        os.fsync(output_stream.fileno())
