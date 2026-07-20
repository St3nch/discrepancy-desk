from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EncryptedArchiveResult:
    zip_path: Path
    encrypted_path: Path
    manifest_path: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_deterministic_zip(source_root: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, source.read_bytes())
    return zip_path


def encrypt_with_age(
    zip_path: Path,
    *,
    recipient: str,
    encrypted_path: Path,
    age_executable: str = "age",
) -> Path:
    if not recipient.strip():
        raise ValueError("age recipient is required")
    encrypted_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [age_executable, "-r", recipient, "-o", str(encrypted_path), str(zip_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        encrypted_path.unlink(missing_ok=True)
        raise RuntimeError(
            "age encryption requires the external age CLI on PATH or an explicit executable path"
        ) from exc
    if completed.returncode != 0:
        encrypted_path.unlink(missing_ok=True)
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown age failure"
        raise RuntimeError(f"age encryption failed: {detail}")
    if not encrypted_path.is_file() or encrypted_path.stat().st_size == 0:
        raise RuntimeError("age encryption produced no output")
    return encrypted_path


def package_and_encrypt_generation(
    generation_root: Path,
    output_root: Path,
    *,
    recipient: str,
    age_executable: str = "age",
) -> EncryptedArchiveResult:
    output_root.mkdir(parents=True, exist_ok=True)
    zip_path = output_root / f"{generation_root.name}.zip"
    encrypted_path = output_root / f"{generation_root.name}.zip.age"
    manifest_path = output_root / f"{generation_root.name}.archive-manifest.json"
    create_deterministic_zip(generation_root, zip_path)
    encrypt_with_age(
        zip_path,
        recipient=recipient,
        encrypted_path=encrypted_path,
        age_executable=age_executable,
    )
    manifest = {
        "generation_id": generation_root.name,
        "zip": {
            "path": zip_path.name,
            "sha256": _sha256(zip_path),
            "byte_size": zip_path.stat().st_size,
        },
        "encrypted": {
            "path": encrypted_path.name,
            "sha256": _sha256(encrypted_path),
            "byte_size": encrypted_path.stat().st_size,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return EncryptedArchiveResult(zip_path, encrypted_path, manifest_path)
