"""SQLite pragma and STRICT enforcement tests."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from desk.db.engine import SqlitePragmaError, apply_connection_pragmas


def test_foreign_keys_pragma_enforced(engine) -> None:
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO runs "
                    "(case_id, status, question, scope, rubric_version, rubric_text, "
                    "capture_budget, created_at, updated_at) "
                    "VALUES (99999, 'draft', 'q', 's', '0', 'r', 20, "
                    "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
                )
            )


def test_wal_mode_on(engine) -> None:
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar_one()
    assert str(mode).lower() == "wal"


def test_foreign_keys_pragma_read_back(engine) -> None:
    with engine.connect() as conn:
        value = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
    assert value == 1


def test_busy_timeout_pragma_read_back(engine) -> None:
    with engine.connect() as conn:
        value = conn.execute(text("PRAGMA busy_timeout")).scalar_one()
    assert int(value) == 5000


def test_apply_connection_pragmas_raises_when_wal_unavailable() -> None:
    """Verify-after-set must not silently accept a non-WAL journal mode."""

    class _FakeCursor:
        def __init__(self) -> None:
            self._last: tuple[object, ...] | None = None

        def execute(self, sql: str) -> None:
            normalized = " ".join(sql.split()).upper()
            if normalized == "PRAGMA FOREIGN_KEYS=ON":
                self._last = None
            elif normalized == "PRAGMA FOREIGN_KEYS":
                self._last = (1,)
            elif normalized == "PRAGMA JOURNAL_MODE=WAL":
                # Simulate filesystem that cannot switch to WAL.
                self._last = ("delete",)
            elif normalized == "PRAGMA JOURNAL_MODE":
                self._last = ("delete",)
            else:
                raise AssertionError(f"unexpected SQL: {sql!r}")

        def fetchone(self) -> tuple[object, ...] | None:
            return self._last

        def close(self) -> None:
            return None

    class _FakeConnection:
        def cursor(self) -> _FakeCursor:
            return _FakeCursor()

    with pytest.raises(SqlitePragmaError, match="journal_mode=WAL"):
        apply_connection_pragmas(_FakeConnection())


def test_all_application_tables_are_strict(engine) -> None:
    """Every application table must be STRICT, regardless of how it was created.

    Holds under hand-written migrations, create_all, and future autogenerate —
    the property is read from sqlite_master SQL, not from our migration source.
    alembic_version is infrastructure, not an application table.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' "
                "AND name != 'alembic_version' "
                "ORDER BY name"
            )
        ).all()

    assert rows, "expected at least one application table"
    for name, sql in rows:
        assert sql is not None, f"table {name!r} has no CREATE SQL in sqlite_master"
        # SQLite stores the keyword as STRICT in the CREATE TABLE text.
        assert "STRICT" in sql.upper(), f"table {name!r} is not STRICT: {sql}"


def test_strict_type_rejection(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO cases (title, created_at) VALUES ('t', '2026-01-01T00:00:00+00:00')")
        )
        with pytest.raises(IntegrityError):
            # STRICT: case_id must be INTEGER, not text.
            conn.execute(
                text(
                    "INSERT INTO runs "
                    "(case_id, status, question, scope, rubric_version, rubric_text, "
                    "capture_budget, created_at, updated_at) "
                    "VALUES ('not-an-int', 'draft', 'q', 's', '0', 'r', 20, "
                    "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
                )
            )


def test_probe_tables_dropped(engine) -> None:
    """F-08: temporary probe tables removed when real MCP tools landed."""
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).all()
        }
    assert "probe_parents" not in names
    assert "probe_notes" not in names
    assert "runs" in names
