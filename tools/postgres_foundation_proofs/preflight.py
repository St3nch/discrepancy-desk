"""Preflight evidence and the numeric PostgreSQL 18 gate.

Harness section 1.3 requires the four preflight statements and a *numeric*
major-version assertion: ``integer(server_version_num) / 10000 == 18``. The
harness is explicit that the version must not be inferred from Docker metadata
or presentation text. Reconciliation section 5 requires the gate on every
connection context used as proof evidence.
"""

from __future__ import annotations

from typing import Any

from . import sql
from .errors import ErrorCategory, ProofRunError

REQUIRED_MAJOR = 18


def major_from_server_version_num(raw: object) -> int:
    """Convert ``SHOW server_version_num`` output to a numeric major version.

    Strict by construction: anything that is not a plain run of digits is a
    failure rather than a best-effort parse, so a presentation string can never
    be coerced into passing the gate.
    """
    if not isinstance(raw, str):
        raise ProofRunError(
            ErrorCategory.VERSION_GATE_FAILED,
            f"server_version_num was not text (got {type(raw).__name__}); refusing to guess",
        )
    text = raw.strip()
    if not text or not text.isdigit():
        raise ProofRunError(
            ErrorCategory.VERSION_GATE_FAILED,
            f"server_version_num {text!r} is not a plain integer; refusing to guess",
        )
    return int(text) // 10000


def require_major_18(raw: object, *, context: str) -> int:
    """Fail closed unless the connected server's numeric major is exactly 18."""
    major = major_from_server_version_num(raw)
    if major != REQUIRED_MAJOR:
        raise ProofRunError(
            ErrorCategory.VERSION_GATE_FAILED,
            f"connected server at {context} reports numeric major {major}, "
            f"but FND-PG01 requires exactly {REQUIRED_MAJOR}",
        )
    return major


def capture_preflight(conn: Any, *, context: str) -> dict[str, Any]:
    """Capture the four harness preflight statements plus server context.

    Returns credential-free observations only. Reconciliation section 5 permits
    recording ``inet_server_addr``/``inet_server_port`` but forbids claiming
    they prove the Docker image or the host-network path, so the returned record
    carries that caveat with it.
    """
    with conn.cursor() as cur:
        cur.execute(sql.SELECT_VERSION)
        version_text = cur.fetchone()[0]

        cur.execute(sql.SHOW_SERVER_VERSION_NUM)
        server_version_num = cur.fetchone()[0]

        cur.execute(sql.SHOW_SERVER_VERSION)
        server_version = cur.fetchone()[0]

        cur.execute(sql.SHOW_TRACK_COMMIT_TIMESTAMP)
        track_commit_timestamp = cur.fetchone()[0]

        cur.execute(sql.SELECT_SERVER_CONTEXT)
        ctx_row = cur.fetchone()

    major = require_major_18(server_version_num, context=context)

    return {
        "context": context,
        "version": version_text,
        "server_version_num": server_version_num,
        "server_version": server_version,
        "numeric_major": major,
        "numeric_major_check": f"int({server_version_num}) // 10000 == {REQUIRED_MAJOR}",
        "track_commit_timestamp": track_commit_timestamp,
        "track_commit_timestamp_note": (
            "Evidence only. No FND-PG01 proof exercises a commit-timestamp finalizer "
            "or a civil-time-to-admission-boundary receipt."
        ),
        "current_database": ctx_row[0],
        "current_user": ctx_row[1],
        "inet_server_addr": ctx_row[2],
        "inet_server_port": ctx_row[3],
        "server_context_note": (
            "Credential-free SQL-visible server context. These values do not prove the "
            "Docker image, the container identity, or the host-network path."
        ),
    }
