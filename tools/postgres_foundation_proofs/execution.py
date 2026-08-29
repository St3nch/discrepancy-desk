"""Thin SQL execution layer that records evidence as it goes.

Deliberately thin. The ticket's dead-capability inventory forbids a speculative
fixture framework, and reconciliation section 11 wants assertion evaluation to
run over *recorded observations*. So this layer only executes and records; every
pass/fail decision lives in a pure ``evaluate_*`` function that takes those
recorded observations and needs no database.
"""

from __future__ import annotations

from typing import Any

import psycopg

from .evidence import ProofResult, SqlStep, bounded_rows


class StepRecorder:
    """Executes SQL against a connection and appends a :class:`SqlStep`."""

    def __init__(self, result: ProofResult) -> None:
        self._result = result

    def run(
        self,
        conn: psycopg.Connection,
        label: str,
        statement: str,
        params: dict[str, Any] | None = None,
        *,
        record: bool = True,
    ) -> list[Any]:
        """Execute a statement expected to succeed and return its rows."""
        try:
            with conn.cursor() as cur:
                cur.execute(statement, params)
                rows = cur.fetchall() if cur.description is not None else []
        except psycopg.Error as exc:
            if record:
                self._result.steps.append(
                    SqlStep(
                        label=label,
                        sql=statement.strip(),
                        params=params,
                        succeeded=False,
                        expected_failure=False,
                        sqlstate=getattr(exc, "sqlstate", None),
                        error_category="unexpected_sql_error",
                    )
                )
            raise

        if record:
            self._result.steps.append(
                SqlStep(
                    label=label,
                    sql=statement.strip(),
                    params=params,
                    succeeded=True,
                    expected_failure=False,
                    rows=bounded_rows(rows, label),
                )
            )
        return rows

    def record_rows(
        self,
        label: str,
        statement: str,
        params: dict[str, Any] | None,
        rows: list[Any],
    ) -> None:
        """Record rows that were already fetched.

        Used by the Proof A observer so the evidence in the report is exactly
        the state that satisfied the blocking condition, not a later re-query
        that could show different state.
        """
        self._result.steps.append(
            SqlStep(
                label=label,
                sql=statement.strip(),
                params=params,
                succeeded=True,
                expected_failure=False,
                rows=bounded_rows(rows, label),
            )
        )

    def run_expecting_failure(
        self,
        conn: psycopg.Connection,
        label: str,
        statement: str,
        savepoint: str,
    ) -> SqlStep:
        """Run an integrity adversary inside a recoverable savepoint.

        Harness section 4.3 requires each adversary to be attempted inside its
        own savepoint and to be rejected. A statement that *succeeds* here is
        recorded as unexpected, which forces the proof to FAIL.
        """
        from psycopg import sql as pgsql

        sp = pgsql.Identifier(savepoint)
        with conn.cursor() as cur:
            cur.execute(pgsql.SQL("SAVEPOINT {}").format(sp))
            try:
                cur.execute(statement)
            except psycopg.Error as exc:
                step = SqlStep(
                    label=label,
                    sql=statement.strip(),
                    succeeded=False,
                    expected_failure=True,
                    sqlstate=getattr(exc, "sqlstate", None),
                    error_category="rejected_by_postgresql",
                )
            else:
                step = SqlStep(
                    label=label,
                    sql=statement.strip(),
                    succeeded=True,
                    expected_failure=True,
                    error_category="unexpected_success",
                )
            cur.execute(pgsql.SQL("ROLLBACK TO SAVEPOINT {}").format(sp))
            cur.execute(pgsql.SQL("RELEASE SAVEPOINT {}").format(sp))

        self._result.steps.append(step)
        return step


def run_setup(
    recorder: StepRecorder,
    conn: psycopg.Connection,
    statements: tuple[str, ...],
    prefix: str,
) -> None:
    """Execute a proof's setup DDL, recording each statement."""
    for index, statement in enumerate(statements, start=1):
        recorder.run(conn, f"{prefix}.setup.{index:02d}", statement)
    conn.commit()
