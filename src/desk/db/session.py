"""Connection helpers for governed service functions."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine
from sqlalchemy.exc import OperationalError

from desk.refusals import DeskRefusal


def _is_sqlite_busy(exc: OperationalError) -> bool:
    """True when SQLite gave up waiting for a lock (after busy_timeout)."""
    msg = str(exc.orig if exc.orig is not None else exc).lower()
    return "locked" in msg or "busy" in msg


@contextmanager
def connection_scope(engine: Engine) -> Iterator[Connection]:
    """Yield a connection with a transaction; commit on success, roll back on error.

    Exhausted busy_timeout surfaces as DeskRefusal DATABASE_BUSY (retryable), never
    as a raw OperationalError at the transport — driver text must not leak.
    """
    try:
        with engine.begin() as conn:
            yield conn
    except OperationalError as exc:
        if _is_sqlite_busy(exc):
            raise DeskRefusal(
                code="DATABASE_BUSY",
                what_happened=(
                    "The database stayed locked longer than the connection busy_timeout; "
                    "the write could not proceed."
                ),
                what_was_preserved="No partial write from this call was committed.",
                what_was_not_changed="Nothing was written by this call.",
                what_you_can_do=(
                    "Retry the same operation shortly; contending writers release locks."
                ),
            ) from None
        raise
