"""Seam tests for suspend / answer / cancel / durable instances (ticket 07)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from desk.db.schema import runs
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    answer_suspended_run,
    approve_run,
    cancel_run,
    claim_next_run,
    create_case,
    create_run,
    list_runs,
    read_case_context,
    suspend_run,
)
from desk.service.lease import validate_and_refresh_claim, validate_claim
from desk.service.models import (
    INSTANCE_VS_CLASS_NOTICE,
    AnswerSuspendedRunInput,
    ApproveRunInput,
    CancelRunInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    ListRunsInput,
    ReadCaseContextInput,
    SuspendRunInput,
)


def _claimed(engine: Engine) -> tuple[int, int, str]:
    """Return (case_id, run_id, claim_token)."""
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="Suspend case")).case_id
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="What is the primary source for Vela?",
                scope="Public foundation only",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        return case_id, packet.run.run_id, packet.run.claim_token


def test_suspend_and_answer_round_trip(engine: Engine) -> None:
    case_id, run_id, token = _claimed(engine)

    with connection_scope(engine) as conn:
        suspended = suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Is source A the same agency as source B?",
                uncertainty="Same agency under a renamed unit vs unrelated agencies",
                default_action="Treat as unrelated and flag for later confirmation",
            ),
        )
        assert suspended.status == "suspended"
        assert suspended.suspension_question == "Is source A the same agency as source B?"
        assert suspended.lease_expires_at is None
        assert suspended.human_answer is None
        assert len(suspended.suspensions) == 1
        assert suspended.suspensions[0].ordinal == 1
        assert suspended.instance_vs_class_notice == INSTANCE_VS_CLASS_NOTICE

        row = conn.execute(
            select(runs.c.status, runs.c.claim_token, runs.c.lease_expires_at).where(
                runs.c.id == run_id
            )
        ).one()
        assert row.status == "suspended"
        assert row.claim_token == token
        assert row.lease_expires_at is None

        with pytest.raises(DeskRefusal) as exc:
            validate_and_refresh_claim(conn, run_id, token)
        assert exc.value.code == "RUN_NOT_CLAIMED"

        # Validate-only (no refresh) still refuses work tools' claimed-only path;
        # allow_suspended accepts token while waiting.
        validate_claim(conn, run_id, token, refresh=False, allow_suspended=True)

        answered = answer_suspended_run(
            conn,
            AnswerSuspendedRunInput(
                run_id=run_id,
                answer="Same agency; treat as one source lineage.",
            ),
        )
        assert answered.status == "claimed"
        assert answered.human_answer == "Same agency; treat as one source lineage."
        assert answered.lease_expires_at is not None
        assert answered.suspensions[0].human_answer == (
            "Same agency; treat as one source lineage."
        )
        assert answered.instance_vs_class_notice is None

        validate_and_refresh_claim(conn, run_id, token)

        listed = list_runs(conn, ListRunsInput(case_id=case_id))
        assert listed.runs[0].status == "claimed"
        assert listed.runs[0].human_answer == "Same agency; treat as one source lineage."


def test_two_suspensions_both_retained(engine: Engine) -> None:
    """F-28: second suspend must not destroy the first answered instance."""
    _, run_id, token = _claimed(engine)

    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="First question?",
                uncertainty="A vs B",
                default_action="Prefer A",
            ),
        )
        answer_suspended_run(
            conn,
            AnswerSuspendedRunInput(run_id=run_id, answer="Prefer B."),
        )
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Second question?",
                uncertainty="C vs D",
                default_action="Prefer C",
            ),
        )
        second = answer_suspended_run(
            conn,
            AnswerSuspendedRunInput(run_id=run_id, answer="Prefer D."),
        )

        assert len(second.suspensions) == 2
        first, last = second.suspensions
        assert first.ordinal == 1
        assert first.question == "First question?"
        assert first.human_answer == "Prefer B."
        assert first.answered_at is not None
        assert last.ordinal == 2
        assert last.question == "Second question?"
        assert last.human_answer == "Prefer D."
        assert last.answered_at is not None
        # Projection shows latest
        assert second.suspension_question == "Second question?"
        assert second.human_answer == "Prefer D."


def test_cancel_unblocks_case(engine: Engine) -> None:
    """F-26: cancel is the escape from a wedged suspended (or any open) run."""
    case_id, run_id, token = _claimed(engine)

    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Unanswerable?",
                uncertainty="Noise",
                default_action="Stop",
            ),
        )
        draft2 = create_run(
            conn,
            CreateRunInput(case_id=case_id, question="Second?", scope="s"),
        )
        with pytest.raises(DeskRefusal) as busy:
            approve_run(conn, ApproveRunInput(run_id=draft2.run_id))
        assert busy.value.code == "RUN_CASE_BUSY"

        cancelled = cancel_run(conn, CancelRunInput(run_id=run_id))
        assert cancelled.status == "cancelled"
        assert cancelled.lease_expires_at is None
        row = conn.execute(
            select(runs.c.claim_token, runs.c.lease_expires_at).where(runs.c.id == run_id)
        ).one()
        assert row.claim_token is None
        assert row.lease_expires_at is None

        approved2 = approve_run(conn, ApproveRunInput(run_id=draft2.run_id))
        assert approved2.status == "approved"


def test_cancel_from_each_cancellable_status(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="Cancel paths")).case_id

        draft = create_run(
            conn, CreateRunInput(case_id=case_id, question="Draft?", scope="s")
        )
        c = cancel_run(conn, CancelRunInput(run_id=draft.run_id))
        assert c.status == "cancelled"

        draft2 = create_run(
            conn, CreateRunInput(case_id=case_id, question="Approved?", scope="s")
        )
        approve_run(conn, ApproveRunInput(run_id=draft2.run_id))
        c2 = cancel_run(conn, CancelRunInput(run_id=draft2.run_id))
        assert c2.status == "cancelled"

        draft3 = create_run(
            conn, CreateRunInput(case_id=case_id, question="Claimed?", scope="s")
        )
        approve_run(conn, ApproveRunInput(run_id=draft3.run_id))
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        c3 = cancel_run(conn, CancelRunInput(run_id=packet.run.run_id))
        assert c3.status == "cancelled"

        with pytest.raises(DeskRefusal) as exc:
            cancel_run(conn, CancelRunInput(run_id=c3.run_id))
        assert exc.value.code == "RUN_NOT_CANCELLABLE"


def test_read_case_context_delivers_answer(engine: Engine) -> None:
    """F-27: same claim reads operator answer after resume."""
    case_id, run_id, token = _claimed(engine)

    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Which entity is canonical?",
                uncertainty="X vs Y",
                default_action="Prefer X",
            ),
        )
        answer_suspended_run(
            conn,
            AnswerSuspendedRunInput(run_id=run_id, answer="Prefer Y."),
        )

        ctx = read_case_context(
            conn,
            ReadCaseContextInput(case_id=case_id, claim_token=token),
        )
        assert ctx.held_run.run_id == run_id
        assert ctx.held_run.status == "claimed"
        assert ctx.held_run.current_suspension is not None
        assert ctx.held_run.current_suspension.human_answer == "Prefer Y."
        assert ctx.held_run.current_suspension.question == "Which entity is canonical?"
        assert ctx.held_run.captures_used == 0
        assert ctx.held_run.claims_made == 0
        assert ctx.held_run.question
        assert ctx.held_run.rubric_text


def test_read_case_context_works_while_suspended(engine: Engine) -> None:
    case_id, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Waiting?",
                uncertainty="A vs B",
                default_action="A",
            ),
        )
        ctx = read_case_context(
            conn,
            ReadCaseContextInput(case_id=case_id, claim_token=token),
        )
        assert ctx.held_run.status == "suspended"
        assert ctx.held_run.current_suspension is not None
        assert ctx.held_run.current_suspension.human_answer is None
        assert ctx.held_run.lease_expires_at is None


def test_suspend_requires_valid_claim_token(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc:
            suspend_run(
                conn,
                SuspendRunInput(
                    run_id=run_id,
                    claim_token="not-the-token",
                    question="Q?",
                    uncertainty="A vs B",
                    default_action="Do A",
                ),
            )
        assert exc.value.code == "RUN_CLAIM_STALE"
        validate_and_refresh_claim(conn, run_id, token)


def test_suspend_refuses_empty_fields(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc:
            suspend_run(
                conn,
                SuspendRunInput(
                    run_id=run_id,
                    claim_token=token,
                    question="   ",
                    uncertainty="A vs B",
                    default_action="Do A",
                ),
            )
        assert exc.value.code == "SUSPEND_QUESTION_EMPTY"


def test_answer_refuses_non_suspended(engine: Engine) -> None:
    _, run_id, _token = _claimed(engine)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc:
            answer_suspended_run(
                conn,
                AnswerSuspendedRunInput(run_id=run_id, answer="Too early"),
            )
        assert exc.value.code == "RUN_NOT_SUSPENDED"


def test_reclaim_after_answer_surfaces_history(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Which entity is canonical?",
                uncertainty="Agency X vs Agency Y",
                default_action="Prefer Agency X",
            ),
        )
        answer_suspended_run(
            conn,
            AnswerSuspendedRunInput(run_id=run_id, answer="Prefer Agency Y."),
        )
        conn.execute(
            text(
                "UPDATE runs SET lease_expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE id = :id"
            ),
            {"id": run_id},
        )

        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        assert packet.run.is_resume is True
        assert packet.run.human_answer == "Prefer Agency Y."
        assert len(packet.run.suspensions) == 1
        assert packet.run.suspensions[0].human_answer == "Prefer Agency Y."


def test_instance_vs_class_copy_in_client_source() -> None:
    """F-29: client must render the same distinction copy the service emits."""
    ui = Path(__file__).resolve().parents[1] / "client" / "src" / "ui.ts"
    text = ui.read_text(encoding="utf-8")
    assert "This answer resolves this run instance only" in text
    assert "amend the relevant rubric separately" in text
    assert "instance-vs-class-notice" in text
