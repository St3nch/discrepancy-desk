"""Immutable raw-byte storage for captures."""

from __future__ import annotations

import hashlib
from pathlib import Path


class VaultStore:
    """Stores capture originals under vault_root; never mutates after write."""

    def __init__(self, vault_root: Path) -> None:
        self.root = vault_root
        self.root.mkdir(parents=True, exist_ok=True)

    def write_raw(self, *, sha256: str, data: bytes) -> str:
        """Write raw bytes once. Returns path relative to vault root.

        Content-addressed by SHA-256: identical bytes share one object.
        """
        rel = Path("raw") / sha256[:2] / sha256
        abs_path = self.root / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        if not abs_path.exists():
            abs_path.write_bytes(data)
        else:
            # Integrity: existing object must match (never overwrite).
            existing = abs_path.read_bytes()
            if existing != data:
                raise RuntimeError(f"Vault object collision for {sha256}")
        return str(rel).replace("\\", "/")

    def read_raw(self, vault_relpath: str) -> bytes:
        path = self.root / vault_relpath
        return path.read_bytes()

    @staticmethod
    def sha256_hex(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
