"""Bidirectional CHECK ↔ evidence.py vocabulary (F-21)."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from desk.db.session import connection_scope
from desk.service import create_case, create_run
from desk.service.evidence import (
    CERTAINTY,
    CORROBORATION,
    POSTURE,
    PUBLICATION_RISK,
    SOURCE_BASIS,
)
from desk.service.models import ApproveRunInput, CreateCaseInput, CreateRunInput
from desk.service.runs import approve_run

_COLUMN_SETS = {
    "source_basis": SOURCE_BASIS,
    "corroboration": CORROBORATION,
    "certainty": CERTAINTY,
    "posture": POSTURE,
    "publication_risk": PUBLICATION_RISK,
}


def _check_values_for_column(sql: str, column: str) -> set[str]:
    pattern = rf"{column}\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*{column}\s+IN\s*\(([^)]+)\)\s*\)"
    match = re.search(pattern, sql, flags=re.IGNORECASE)
    assert match is not None, f"CHECK for {column} not found in: {sql}"
    return {m.strip().strip("'\"") for m in match.group(1).split(",") if m.strip()}


def test_claims_dimension_checks_match_evidence_module(engine: Engine) -> None:
    with engine.connect() as conn:
        sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'claims'")
        ).scalar_one()
    assert sql is not None
    ddl = str(sql)
    for column, expected in _COLUMN_SETS.items():
        check_values = _check_values_for_column(ddl, column)
        assert check_values == set(expected), (
            f"{column}: CHECK {sorted(check_values)} != evidence.py {sorted(expected)}"
        )


def test_claims_dimension_check_rejects_unknown(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="vocab"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Q",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO claims ("
                    "case_id, run_id, proposition, confirmation_status, "
                    "source_basis, corroboration, certainty, posture, "
                    "qualification, publication_risk, rubric_version, created_at"
                    ") VALUES ("
                    ":case_id, :run_id, 'p', 'unconfirmed', "
                    "'contemporaneous_report', 'single_source', 'definitely_true', "
                    "'factual_assertion', '', 'not_applicable', '0', "
                    "'2026-01-01T00:00:00+00:00')"
                ),
                {"case_id": case.case_id, "run_id": run.run_id},
            )
