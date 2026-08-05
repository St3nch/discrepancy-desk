"""Engine factory with required SQLite pragmas on every connection."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text

# Milliseconds. Contended writers (executor claim/capture loop + operator browser)
# must wait rather than fail immediately with "database is locked".
BUSY_TIMEOUT_MS = 5000


class SqlitePragmaError(RuntimeError):
    """Raised when a required SQLite pragma did not take effect."""


def apply_connection_pragmas(dbapi_connection: object, _connection_record: object = None) -> None:
    """Enable foreign keys, WAL, and busy_timeout; verify each took effect.

    SQLite defaults foreign_keys OFF and busy_timeout 0 — both are fail-opens.
    Setting without reading back is the same failure one level up.
    """
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA foreign_keys")
        fk_row = cursor.fetchone()
        fk_value = fk_row[0] if fk_row is not None else None
        if fk_value != 1:
            raise SqlitePragmaError(
                f"PRAGMA foreign_keys=ON did not take effect (read back {fk_value!r})"
            )

        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA journal_mode")
        mode_row = cursor.fetchone()
        mode_value = mode_row[0] if mode_row is not None else None
        if str(mode_value).lower() != "wal":
            raise SqlitePragmaError(
                f"PRAGMA journal_mode=WAL did not take effect (read back {mode_value!r})"
            )

        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA busy_timeout")
        busy_row = cursor.fetchone()
        busy_value = busy_row[0] if busy_row is not None else None
        if busy_value is None or int(busy_value) != BUSY_TIMEOUT_MS:
            raise SqlitePragmaError(
                f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS} did not take effect "
                f"(read back {busy_value!r})"
            )
    finally:
        cursor.close()


def create_db_engine(database_path: Path | str, *, echo: bool = False) -> Engine:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.resolve()}"
    engine = create_engine(url, echo=echo, future=True)
    event.listen(engine, "connect", apply_connection_pragmas)
    # Force a connection so WAL is set on the file early (and verified).
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return engine
