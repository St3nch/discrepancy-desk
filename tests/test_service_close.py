"""Seam tests for close_run, agenda decisions, and examined captures (ticket 08)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from desk.db.schema import captures
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    add_lead,
    approve_run,
    attach_lead,
    capture_url,
    claim_next_run,
    close_run,
    create_case,
    create_operator_open_question,
    create_run,
    decide_open_question,
    get_run_close,
    propose_claim,
)
from desk.service.models import (
    AddLeadInput,
    ApproveRunInput,
    AttachLeadInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CloseRunInput,
    CreateCaseInput,
    CreateOperatorOpenQuestionInput,
    CreateRunInput,
    DecideOpenQuestionInput,
    EvidenceDimensions,
    GetRunCloseInput,
    ProposeClaimInput,
    ProposedOpenQuestionInput,
)
from desk.vault.store import VaultStore


def _dims() -> EvidenceDimensions:
    return EvidenceDimensions(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )


def _claimed(engine: Engine) -> tuple[int, int, str]:
    with connection_scope(engine) as conn:
        case_id = create_case(conn, CreateCaseInput(title="Close case")).case_id
        draft = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="What did the official report establish?",
                scope="Foundation sources",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=draft.run_id))
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        return case_id, packet.run.run_id, packet.run.claim_token


def test_close_run_agenda_and_complete(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)

    with connection_scope(engine) as conn:
        result = close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                proposed_questions=[
                    ProposedOpenQuestionInput(
                        text="Who authored the annex?",
                        rationale="The main report cites an unnamed annex.",
                        proposed_scope="Archive records only",
                    ),
                    ProposedOpenQuestionInput(
                        text="Was the annex published?",
                        rationale="Publication status is unclear.",
                        proposed_scope="Public catalogs",
                    ),
                ],
                low_confidence_areas=[
                    "Certainty on annex authorship felt underserved by the rubric.",
                ],
            ),
        )
        assert result.run.status == "complete"
        assert result.run.lease_expires_at is None
        assert len(result.agenda) == 2
        assert result.agenda[0].agenda_decision == "pending"
        assert result.agenda[0].source_run_question == ("What did the official report establish?")
        assert result.agenda[0].introduced_by_run_id == run_id
        assert result.low_confidence_areas == [
            "Certainty on annex authorship felt underserved by the rubric.",
        ]
        assert result.captures_count == 0
        assert result.claims_count == 0


def test_decide_approve_reject_replace(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        closed = close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                proposed_questions=[
                    ProposedOpenQuestionInput(
                        text="Q1?",
                        rationale="R1",
                        proposed_scope="S1",
                    ),
                    ProposedOpenQuestionInput(
                        text="Q2?",
                        rationale="R2",
                        proposed_scope="S2",
                    ),
                    ProposedOpenQuestionInput(
                        text="Q3?",
                        rationale="R3",
                        proposed_scope="S3",
                    ),
                ],
            ),
        )
        a, b, c = closed.agenda

        approved = decide_open_question(
            conn,
            DecideOpenQuestionInput(
                open_question_id=a.open_question_id,
                decision="approve",
                disposition="not-yet-worked",
                text="Q1 refined?",
                scope="S1 edited",
            ),
        )
        assert approved.agenda_decision == "approved"
        assert approved.disposition == "not-yet-worked"
        assert approved.settled_text == "Q1 refined?"
        assert approved.settled_scope == "S1 edited"

        rejected = decide_open_question(
            conn,
            DecideOpenQuestionInput(
                open_question_id=b.open_question_id,
                decision="reject",
            ),
        )
        assert rejected.agenda_decision == "rejected"
        assert rejected.disposition is None

        replaced = decide_open_question(
            conn,
            DecideOpenQuestionInput(
                open_question_id=c.open_question_id,
                decision="replace",
                disposition="unresolved-likely-permanent",
                text="Operator's own question",
                scope="Operator scope",
            ),
        )
        assert replaced.agenda_decision == "replaced"
        assert replaced.disposition == "unresolved-likely-permanent"
        assert replaced.settled_text == "Operator's own question"

        with pytest.raises(DeskRefusal) as exc:
            decide_open_question(
                conn,
                DecideOpenQuestionInput(
                    open_question_id=a.open_question_id,
                    decision="approve",
                    disposition="not-yet-worked",
                ),
            )
        assert exc.value.code == "OPEN_QUESTION_ALREADY_DECIDED"


def test_examined_only_when_explicitly_reported(engine: Engine, tmp_path: Path) -> None:
    """F-32: only listed uncited captures become examined; omitted stay unexamined."""
    _, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    html_a = b"<html><body><p>Alpha passage for quotes.</p></body></html>"
    html_b = b"<html><body><p>Beta passage looked at, nothing claimed.</p></body></html>"
    html_c = b"<html><body><p>Gamma fetched but not reported examined.</p></body></html>"

    with connection_scope(engine) as conn:
        cap_a = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/a", claim_token=token),
            vault=vault,
            fetch=lambda _u: (html_a, "text/html"),
        )
        cap_b = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/b", claim_token=token),
            vault=vault,
            fetch=lambda _u: (html_b, "text/html"),
        )
        cap_c = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/c", claim_token=token),
            vault=vault,
            fetch=lambda _u: (html_c, "text/html"),
        )

        elem = cap_a.elements[0]
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Alpha was stated.",
                dimensions=_dims(),
                capture_id=cap_a.capture_id,
                locator=elem.locator,
                quoted_text=elem.text,
            ),
        )
        assert claim.source_run_question == "What did the official report establish?"

        closed = close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                proposed_questions=[],
                low_confidence_areas=[],
                # Report only B as examined; C is uncited but not reported.
                examined_capture_ids=[cap_b.capture_id],
            ),
        )
        assert closed.captures_marked_examined == 1
        assert closed.captures_count == 3
        assert closed.claims_count == 1

        statuses = {
            int(r.id): str(r.status)
            for r in conn.execute(
                select(captures.c.id, captures.c.status).where(captures.c.run_id == run_id)
            ).all()
        }
        assert statuses[cap_a.capture_id] == "cited"
        assert statuses[cap_b.capture_id] == "examined"
        assert statuses[cap_c.capture_id] == "unexamined"


def test_close_run_examines_attached_lead_capture(engine: Engine, tmp_path: Path) -> None:
    """Attached lead captures (run_id NULL) are reportable examined (review #1)."""
    case_id, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    html = b"<html><body><p>Lead material looked at, nothing claimed.</p></body></html>"

    def fetch(_url: str) -> tuple[bytes, str]:
        return html, "text/html"

    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/attached-lead", note=""),
            vault=vault,
            fetch=fetch,
        )
        assert lead.capture_id is not None
        attach_lead(
            conn,
            AttachLeadInput(lead_id=lead.lead_id, case_id=case_id),
        )
        closed = close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                examined_capture_ids=[lead.capture_id],
            ),
        )
        assert closed.captures_marked_examined == 1
        status = conn.execute(
            select(captures.c.status).where(captures.c.id == lead.capture_id)
        ).scalar_one()
        assert str(status) == "examined"
        run_id_col = conn.execute(
            select(captures.c.run_id).where(captures.c.id == lead.capture_id)
        ).scalar_one()
        assert run_id_col is None  # still lead-owned on the run column


def test_examined_refuses_cited_capture(engine: Engine, tmp_path: Path) -> None:
    _, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    html_a = b"<html><body><p>Alpha passage for quotes.</p></body></html>"
    with connection_scope(engine) as conn:
        cap_a = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/a", claim_token=token),
            vault=vault,
            fetch=lambda _u: (html_a, "text/html"),
        )
        elem = cap_a.elements[0]
        propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Alpha was stated.",
                dimensions=_dims(),
                capture_id=cap_a.capture_id,
                locator=elem.locator,
                quoted_text=elem.text,
            ),
        )
        with pytest.raises(DeskRefusal) as exc:
            close_run(
                conn,
                CloseRunInput(
                    run_id=run_id,
                    claim_token=token,
                    examined_capture_ids=[cap_a.capture_id],
                ),
            )
        assert exc.value.code == "EXAMINED_CAPTURE_ALREADY_CITED"


def test_operator_authored_open_question_empty_agenda(engine: Engine) -> None:
    """F-31: operator can originate when executor proposed zero questions."""
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        closed = close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                proposed_questions=[],
            ),
        )
        assert closed.agenda == []

        authored = create_operator_open_question(
            conn,
            CreateOperatorOpenQuestionInput(
                run_id=run_id,
                text="What was the chain of custody?",
                scope="Archive only",
                disposition="not-yet-worked",
            ),
        )
        assert authored.agenda_decision == "approved"
        assert authored.disposition == "not-yet-worked"
        assert authored.settled_text == "What was the chain of custody?"
        assert authored.settled_scope == "Archive only"
        assert authored.decided_at is not None
        assert authored.source_run_question == "What did the official report establish?"
        assert authored.introduced_by_run_id == run_id
        assert "Operator-authored" in authored.rationale

        view = get_run_close(conn, GetRunCloseInput(run_id=run_id))
        assert len(view.agenda) == 1
        assert view.agenda[0].open_question_id == authored.open_question_id


def test_get_run_close_d13_shape(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                proposed_questions=[
                    ProposedOpenQuestionInput(
                        text="Next?",
                        rationale="Because",
                        proposed_scope="Scope",
                    )
                ],
                low_confidence_areas=["Unsure about classification"],
            ),
        )
        view = get_run_close(conn, GetRunCloseInput(run_id=run_id))
        assert view.run.status == "complete"
        assert len(view.agenda) == 1
        assert view.captures_count == 0
        assert view.claims_count == 0
        assert view.low_confidence_areas == ["Unsure about classification"]
        # Detail present but not the decision surface
        assert view.claims == []
        assert view.captures == []


def test_close_requires_claim(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc:
            close_run(
                conn,
                CloseRunInput(
                    run_id=run_id,
                    claim_token="wrong",
                    proposed_questions=[],
                ),
            )
        assert exc.value.code == "RUN_CLAIM_STALE"
        # Still claimed with original token
        close_run(
            conn,
            CloseRunInput(run_id=run_id, claim_token=token, proposed_questions=[]),
        )


def test_approve_requires_disposition(engine: Engine) -> None:
    _, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        closed = close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                proposed_questions=[
                    ProposedOpenQuestionInput(
                        text="Q?",
                        rationale="R",
                        proposed_scope="S",
                    )
                ],
            ),
        )
        with pytest.raises(DeskRefusal) as exc:
            decide_open_question(
                conn,
                DecideOpenQuestionInput(
                    open_question_id=closed.agenda[0].open_question_id,
                    decision="approve",
                ),
            )
        assert exc.value.code == "DISPOSITION_INVALID"
