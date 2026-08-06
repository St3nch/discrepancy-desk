"""In-process governed-operations seam tests for Case operations."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, inspect, text

from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import create_case, get_case, list_cases
from desk.service.models import CreateCaseInput, GetCaseInput, ListCasesInput


def test_create_list_get_round_trip(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        created = create_case(conn, CreateCaseInput(title="  Vela Incident  "))
        assert created.title == "Vela Incident"
        assert created.case_id >= 1
        assert created.created_at

        listed = list_cases(conn, ListCasesInput())
        assert len(listed.cases) == 1
        assert listed.cases[0].case_id == created.case_id
        assert listed.cases[0].title == "Vela Incident"

        detail = get_case(conn, GetCaseInput(case_id=created.case_id))
        assert detail.case.title == "Vela Incident"
        assert detail.runs == []
        assert detail.captures == []
        assert detail.claims == []  # list[ClaimRecord], empty until propose_claim
        assert detail.open_questions == []
        assert detail.coverage.case_id == created.case_id
        assert detail.coverage.official_foundation_complete is False
        assert len(detail.coverage.stages) == 6
        assert detail.angles == []
        assert detail.public_questions == []
        assert detail.quotation_shelf == []
        assert detail.renditions == []


def test_create_refuses_empty_title(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            create_case(conn, CreateCaseInput(title="   "))
    assert exc_info.value.code == "CASE_TITLE_EMPTY"


def test_get_refuses_unknown_case(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            get_case(conn, GetCaseInput(case_id=99999))
    assert exc_info.value.code == "CASE_NOT_FOUND"
    assert exc_info.value.what_was_not_changed == "Nothing was written."


def test_case_schema_has_no_complete_or_closed_status(engine: Engine) -> None:
    """A Case never completes — no complete/closed status column is exposed or stored."""
    insp = inspect(engine)
    column_names = {col["name"] for col in insp.get_columns("cases")}
    forbidden = {"status", "state", "completed", "complete", "closed", "lifecycle"}
    assert column_names.isdisjoint(forbidden), (
        f"cases table must not carry complete/closed state; found {column_names & forbidden}"
    )
    assert {"id", "title", "created_at"} <= column_names


def test_case_schema_has_no_account_column(engine: Engine) -> None:
    """One brand per deployment (D17) — no in-instance account boundary."""
    insp = inspect(engine)
    column_names = {col["name"] for col in insp.get_columns("cases")}
    forbidden = {"account_id", "account", "brand_id", "tenant_id"}
    assert column_names.isdisjoint(forbidden), (
        f"cases table must not carry account/brand columns; found {column_names & forbidden}"
    )


def test_create_persists_across_connection(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        created = create_case(conn, CreateCaseInput(title="Persisted case"))
        case_id = created.case_id

    with connection_scope(engine) as conn:
        row = conn.execute(
            text("SELECT title FROM cases WHERE id = :id"),
            {"id": case_id},
        ).one()
    assert row.title == "Persisted case"
