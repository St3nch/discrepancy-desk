"""In-process governed-operations seam tests for Run dispatch and claim."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    claim_next_run,
    create_case,
    create_run,
    list_runs,
)
from desk.service.models import (
    ApproveRunInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    ListRunsInput,
)
from desk.service.run_status import RUN_STATUSES


def _case(engine: Engine, title: str = "Vela") -> int:
    with connection_scope(engine) as conn:
        return create_case(conn, CreateCaseInput(title=title)).case_id


def test_create_approve_claim_round_trip(engine: Engine) -> None:
    case_id = _case(engine)
    with connection_scope(engine) as conn:
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="What did the Vela satellite record?",
                scope="Official foundation sources only",
                coverage_dimension="official_foundation",
            ),
        )
        assert draft.status == "draft"
        assert draft.rubric_version  # placeholder present
        assert draft.rubric_text

        approved = approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        assert approved.status == "approved"

        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        assert claimed.run.run_id == draft.run_id
        assert claimed.run.status == "claimed"
        assert claimed.run.question == "What did the Vela satellite record?"
        assert claimed.run.scope == "Official foundation sources only"
        assert claimed.run.rubric_version == draft.rubric_version
        assert claimed.run.rubric_text == draft.rubric_text

        idle = claim_next_run(conn, ClaimNextRunInput())
        assert idle.run is None


def test_claim_next_run_idle_is_empty_not_refusal(engine: Engine) -> None:
    """No approved run is normal idle — not DeskRefusal."""
    with connection_scope(engine) as conn:
        result = claim_next_run(conn, ClaimNextRunInput())
    assert result.run is None


def test_claim_oldest_approved_first(engine: Engine) -> None:
    case_a = _case(engine, "A")
    case_b = _case(engine, "B")
    with connection_scope(engine) as conn:
        first = create_run(
            conn,
            CreateRunInput(
                case_id=case_a,
                question="First?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        second = create_run(
            conn,
            CreateRunInput(
                case_id=case_b,
                question="Second?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=first.run_id))
        approve_run(conn, ApproveRunInput(run_id=second.run_id))

        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        assert claimed.run.run_id == first.run_id
        assert claimed.run.question == "First?"


def test_approve_refuses_non_draft(engine: Engine) -> None:
    case_id = _case(engine)
    with connection_scope(engine) as conn:
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id, question="Q?", scope="s", coverage_dimension="official_foundation"
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        with pytest.raises(DeskRefusal) as exc_info:
            approve_run(conn, ApproveRunInput(run_id=draft.run_id))
    assert exc_info.value.code == "RUN_NOT_DRAFT"


def test_case_busy_refuses_second_approve(engine: Engine) -> None:
    case_id = _case(engine)
    with connection_scope(engine) as conn:
        a = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="One?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        b = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Two?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=a.run_id))
        with pytest.raises(DeskRefusal) as exc_info:
            approve_run(conn, ApproveRunInput(run_id=b.run_id))
    assert exc_info.value.code == "RUN_CASE_BUSY"


def test_create_run_refuses_unknown_case(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            create_run(
                conn,
                CreateRunInput(
                    case_id=99999,
                    question="Q?",
                    scope="s",
                    coverage_dimension="official_foundation",
                ),
            )
    assert exc_info.value.code == "CASE_NOT_FOUND"


def test_create_run_refuses_empty_question(engine: Engine) -> None:
    case_id = _case(engine)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            create_run(
                conn,
                CreateRunInput(
                    case_id=case_id,
                    question="  ",
                    scope="s",
                    coverage_dimension="official_foundation",
                ),
            )
    assert exc_info.value.code == "RUN_QUESTION_EMPTY"


def test_list_runs_for_case(engine: Engine) -> None:
    case_id = _case(engine)
    with connection_scope(engine) as conn:
        create_run(
            conn,
            CreateRunInput(
                case_id=case_id, question="Q?", scope="s", coverage_dimension="official_foundation"
            ),
        )
        listed = list_runs(conn, ListRunsInput(case_id=case_id))
    assert listed.case_id == case_id
    assert len(listed.runs) == 1
    assert listed.runs[0].status == "draft"


def test_run_status_vocabulary_matches_sqlite_check(engine: Engine) -> None:
    """Bidirectional reconciliation: migration CHECK ↔ RUN_STATUSES (F-10).

    Reads the CHECK clause from sqlite_master so a value present only in the
    migration or only in Python fails the test.
    """
    import re

    with engine.connect() as conn:
        sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runs'")
        ).scalar_one()
    assert sql is not None
    match = re.search(
        r"status\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]+)\)\s*\)",
        str(sql),
        flags=re.IGNORECASE,
    )
    assert match is not None, f"runs.status CHECK not found in: {sql}"
    check_values = {m.strip().strip("'\"") for m in match.group(1).split(",") if m.strip()}
    assert check_values == set(RUN_STATUSES), (
        f"CHECK {sorted(check_values)} != RUN_STATUSES {sorted(RUN_STATUSES)}"
    )

    # Also prove every vocabulary value is insertable.
    case_id = _case(engine)
    with connection_scope(engine) as conn:
        for status in sorted(RUN_STATUSES):
            conn.execute(
                text(
                    "INSERT INTO runs "
                    "(case_id, status, question, scope, rubric_version, rubric_text, "
                    "capture_budget, created_at, updated_at) "
                    "VALUES (:case_id, :status, 'q', 's', '0', 'r', 20, "
                    "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
                ),
                {"case_id": case_id, "status": status},
            )
        count = conn.execute(text("SELECT COUNT(*) FROM runs")).scalar_one()
    assert count == len(RUN_STATUSES)


def test_run_status_check_rejects_unknown(engine: Engine) -> None:
    from sqlalchemy.exc import IntegrityError

    case_id = _case(engine)
    with connection_scope(engine) as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO runs "
                    "(case_id, status, question, scope, rubric_version, rubric_text, "
                    "capture_budget, created_at, updated_at) "
                    "VALUES (:case_id, 'queued', 'q', 's', '0', 'r', 20, "
                    "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
                ),
                {"case_id": case_id},
            )
