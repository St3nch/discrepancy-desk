"""Bidirectional sqlite_master CHECK ↔ Python vocabulary (F-10, F-21, F-30).

One parameterised suite for every CHECK-constrained enum column rather than
a new file per table — migrations freeze their own copies, which is correct
and is what makes silent drift possible.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import Engine, text

from desk.service.coverage import COVERAGE_STAGE_IDS
from desk.service.evidence import (
    ANGLE_STATUSES,
    CAPTURE_STATUSES,
    CERTAINTY,
    CONFIRMATION_STATUSES,
    CORROBORATION,
    LEAD_INBOX_STATUSES,
    LEAD_MATERIAL_STATUSES,
    POSTURE,
    PUBLICATION_RISK,
    PUBLICATION_VERIFICATION_STATES,
    RENDITION_FORMATS,
    RENDITION_PLATFORMS,
    RENDITION_STATUSES,
    SOURCE_BASIS,
)
from desk.service.models import AGENDA_DECISIONS, OPEN_QUESTION_DISPOSITIONS
from desk.service.run_status import RUN_STATUSES

# (table, column, python frozenset) — every application CHECK enum.
_ENUM_COLUMNS: list[tuple[str, str, frozenset[str]]] = [
    ("runs", "status", RUN_STATUSES),
    ("runs", "coverage_dimension", COVERAGE_STAGE_IDS),
    ("captures", "status", CAPTURE_STATUSES),
    ("claims", "confirmation_status", CONFIRMATION_STATUSES),
    ("claims", "source_basis", SOURCE_BASIS),
    ("claims", "corroboration", CORROBORATION),
    ("claims", "certainty", CERTAINTY),
    ("claims", "posture", POSTURE),
    ("claims", "publication_risk", PUBLICATION_RISK),
    ("open_questions", "agenda_decision", AGENDA_DECISIONS),
    ("open_questions", "disposition", OPEN_QUESTION_DISPOSITIONS),
    ("leads", "material_status", LEAD_MATERIAL_STATUSES),
    ("leads", "inbox_status", LEAD_INBOX_STATUSES),
    ("coverage_attestations", "stage", COVERAGE_STAGE_IDS),
    ("angles", "status", ANGLE_STATUSES),
    ("renditions", "status", RENDITION_STATUSES),
    ("renditions", "platform", RENDITION_PLATFORMS),
    ("renditions", "format", RENDITION_FORMATS),
    ("rendition_publication_units", "platform", RENDITION_PLATFORMS),
    ("rendition_publication_units", "verification_state", PUBLICATION_VERIFICATION_STATES),
]


def _check_in_values(ddl: str, column: str) -> set[str]:
    """Extract values from CHECK (... column IN (...)) or nullable OR form."""
    # Match the IN list for this column whether or not wrapped in NULL OR.
    pattern = (
        rf"(?:{column}\s+IS\s+NULL\s+OR\s+)?"
        rf"{column}\s+IN\s*\(([^)]+)\)"
    )
    match = re.search(pattern, ddl, flags=re.IGNORECASE)
    assert match is not None, f"CHECK IN-list for {column} not found in: {ddl}"
    return {m.strip().strip("'\"") for m in match.group(1).split(",") if m.strip()}


@pytest.mark.parametrize(
    ("table", "column", "expected"),
    _ENUM_COLUMNS,
    ids=[f"{t}.{c}" for t, c, _ in _ENUM_COLUMNS],
)
def test_check_enum_matches_python(
    engine: Engine,
    table: str,
    column: str,
    expected: frozenset[str],
) -> None:
    with engine.connect() as conn:
        sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
            {"name": table},
        ).scalar_one()
    assert sql is not None, f"table {table!r} missing from sqlite_master"
    check_values = _check_in_values(str(sql), column)
    assert check_values == set(expected), (
        f"{table}.{column}: CHECK {sorted(check_values)} != Python {sorted(expected)}"
    )
