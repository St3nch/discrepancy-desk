"""Proof-database naming.

Names are runner-generated only. Reconciliation section 6 requires that proof
database identifiers be composed with the driver's identifier-quoting facility
and that no DSN-derived value is interpolated into SQL identifiers or SQL text.
This module generates the name; quoting happens at the call site.
"""

from __future__ import annotations

import re
import secrets

#: Every proof database this runner creates carries this prefix so an operator
#: can recognize orphaned proof state as belonging to FND-PG01.
PROOF_DATABASE_PREFIX = "fndpg01"

#: PostgreSQL truncates identifiers at NAMEDATALEN-1 (63) bytes by default.
MAX_IDENTIFIER_LENGTH = 63

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def new_token(entropy_bytes: int = 6) -> str:
    """Return a fresh lowercase hex token."""
    return secrets.token_hex(entropy_bytes)


def proof_database_name(proof: str, token: str) -> str:
    """Compose a unique proof-database name for ``proof``.

    Raises ``ValueError`` rather than silently sanitizing, so a malformed name
    can never reach ``CREATE DATABASE``.
    """
    proof_key = proof.lower()
    if not _SAFE_NAME.match(proof_key):
        raise ValueError(f"unsafe proof key: {proof!r}")
    if not re.match(r"^[0-9a-f]+$", token):
        raise ValueError("token must be lowercase hex")

    name = f"{PROOF_DATABASE_PREFIX}_{proof_key}_{token}"
    if not _SAFE_NAME.match(name):
        raise ValueError(f"generated an unsafe database name: {name!r}")
    if len(name.encode("utf-8")) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"generated database name exceeds {MAX_IDENTIFIER_LENGTH} bytes: {name!r}")
    return name
