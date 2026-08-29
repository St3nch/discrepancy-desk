"""Stable error categories and runner-authored bounded messages.

Reconciliation section 7 forbids serializing driver exceptions, connection-info
reprs, or environment contents. Every failure that reaches the report is mapped
onto one of these stable categories with a message this package authored.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCategory(StrEnum):
    """Stable, report-safe failure categories."""

    DSN_MISSING = "dsn_missing"
    DSN_UNPARSEABLE = "dsn_unparseable"
    DSN_REJECTED = "dsn_rejected"
    CONNECT_FAILED = "connect_failed"
    VERSION_GATE_FAILED = "version_gate_failed"
    ROLE_CAPABILITY_MISSING = "role_capability_missing"
    DATABASE_CREATE_FAILED = "database_create_failed"
    DATABASE_NOT_EMPTY = "database_not_empty"
    PROOF_STEP_UNEXPECTED = "proof_step_unexpected"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    CLEANUP_FAILED = "cleanup_failed"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    REPORT_CONTAMINATED = "report_contaminated"
    INTERNAL_ERROR = "internal_error"


class ProofRunError(Exception):
    """A runner-authored failure carrying a stable category.

    The message must never embed a DSN, password, driver repr, or environment
    content. Callers construct these from already-redacted values only.
    """

    def __init__(self, category: ErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message

    def __str__(self) -> str:
        return f"[{self.category}] {self.message}"


class DeadlineExceeded(ProofRunError):
    """A hard client-side deadline elapsed.

    Reconciliation section 6: a missed deadline is FAIL followed by cleanup. It
    is never retried into a pass and never silently ignored.
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCategory.DEADLINE_EXCEEDED, message)
