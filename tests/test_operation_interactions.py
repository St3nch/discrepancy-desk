"""Cross-operation interaction tests (ticket 10a).

Why this file exists
--------------------
Every defect that has broken this project is *operation A changes what operation B
reports*, not a failure inside one function. Each layer's tests were green every
time (codingstandards.md; F-07, F-25b, F-34, F-38).

These tests run two (or more) governed operations in sequence and assert what the
**second** (or later) reports. They are not a coverage-percentage sweep. If a
pair has no state interaction, it does not belong here.

Adding a governed operation means adding a pair here when that operation writes
state another operation reads — or documenting why no pair is needed.

Pairs chosen because they sit on load-bearing seams, not because they re-test
single-function happy paths already covered elsewhere.
"""

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
    assert_official_foundation_complete,
    attach_lead,
    attest_coverage,
    cancel_run,
    capture_url,
    claim_next_run,
    close_run,
    create_case,
    create_run,
    get_case,
    get_case_coverage,
    propose_claim,
    read_case_context,
    suspend_run,
)
from desk.service.models import (
    AddLeadInput,
    ApproveRunInput,
    AssertOfficialFoundationInput,
    AttachLeadInput,
    AttestCoverageInput,
    CancelRunInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CloseRunInput,
    CreateCaseInput,
    CreateRunInput,
    EvidenceDimensions,
    GetCaseCoverageInput,
    GetCaseInput,
    ProposeClaimInput,
    ReadCaseContextInput,
    SuspendRunInput,
)
from desk.vault.store import VaultStore

_HTML = b"""<!DOCTYPE html><html><body>
<p>Interaction paragraph one.</p>
<p>Interaction paragraph two.</p>
</body></html>"""


def _html_fetch(_url: str) -> tuple[bytes, str]:
    return _HTML, "text/html; charset=utf-8"


def _dims() -> EvidenceDimensions:
    return EvidenceDimensions(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )


def _claimed(
    engine: Engine,
    *,
    dimension: str = "official_foundation",
    budget: int = 10,
) -> tuple[int, int, str]:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Interaction case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Interaction Q?",
                scope="s",
                coverage_dimension=dimension,
                capture_budget=budget,
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        return case.case_id, claimed.run.run_id, claimed.run.claim_token


# --- Ticket-listed pairs ------------------------------------------------------


def test_attach_lead_then_close_run_can_examine_that_capture(
    engine: Engine, tmp_path: Path
) -> None:
    """F-34: attach_lead then close_run reports the lead capture examined."""
    case_id, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/for-close", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        assert lead.capture_id is not None
        attach_lead(conn, AttachLeadInput(lead_id=lead.lead_id, case_id=case_id))

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


def test_attest_then_attach_lead_then_gauge_stale(engine: Engine, tmp_path: Path) -> None:
    """F-38: attach_lead after attestation must not leave the gate open silently."""
    vault = VaultStore(tmp_path / "vault")
    case_id, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/foundation",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        elem = cap.elements[0]
        propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Foundation claim.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=elem.locator,
                quoted_text=elem.text,
            ),
        )
        close_run(conn, CloseRunInput(run_id=run_id, claim_token=token))
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case_id, stage="official_foundation"),
        )
        assert (
            get_case_coverage(
                conn, GetCaseCoverageInput(case_id=case_id)
            ).official_foundation_complete
            is True
        )

        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/after-attest", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        attach_lead(conn, AttachLeadInput(lead_id=lead.lead_id, case_id=case_id))

        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        assert gauge.official_foundation_complete is False
        of = next(s for s in gauge.stages if s.stage == "official_foundation")
        assert of.reading == "worked"
        with pytest.raises(DeskRefusal) as exc:
            assert_official_foundation_complete(
                conn, AssertOfficialFoundationInput(case_id=case_id)
            )
        assert exc.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"


def test_cancel_run_then_captures_remain_unexamined(engine: Engine, tmp_path: Path) -> None:
    """F-26: cancel_run must not invent examined — status stays unexamined."""
    case_id, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/cancelled-cap",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        cancel_run(conn, CancelRunInput(run_id=run_id))

        status = conn.execute(
            select(captures.c.status).where(captures.c.id == cap.capture_id)
        ).scalar_one()
        assert str(status) == "unexamined"
        # Case still lists the capture; nothing was deleted.
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        assert any(c.capture_id == cap.capture_id for c in detail.captures)
        assert any(
            c.capture_id == cap.capture_id and c.status == "unexamined" for c in detail.captures
        )


def test_propose_claim_on_attached_lead_then_get_case(engine: Engine, tmp_path: Path) -> None:
    """Attached lead capture is citable; get_case shows the claim and capture."""
    case_id, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/cite-me", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        assert lead.capture_id is not None
        attach_lead(conn, AttachLeadInput(lead_id=lead.lead_id, case_id=case_id))

        # Need elements — lead was captured; use first element text from projection.
        assert lead.projection_markdown
        # Re-read via propose: use e/0 with exact text from capture path.
        # Lead add_lead returns elements only in projection; get locator from store path
        # by proposing with text we know is in the HTML.
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Lead material states paragraph one.",
                dimensions=_dims(),
                capture_id=lead.capture_id,
                locator="e/0",
                quoted_text="Interaction paragraph one.",
            ),
        )
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        assert any(c.claim_id == claim.claim_id for c in detail.claims)
        assert any(c.capture_id == lead.capture_id for c in detail.captures)
        cap_row = next(c for c in detail.captures if c.capture_id == lead.capture_id)
        assert cap_row.status == "cited"


def test_suspend_answer_then_read_case_context(engine: Engine) -> None:
    """F-27: after suspend + answer, read_case_context reports the answer and claimed."""
    case_id, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        suspend_run(
            conn,
            SuspendRunInput(
                run_id=run_id,
                claim_token=token,
                question="Which archive?",
                uncertainty="National vs local",
                default_action="National",
            ),
        )
        from desk.service import answer_suspended_run
        from desk.service.models import AnswerSuspendedRunInput

        answer_suspended_run(
            conn,
            AnswerSuspendedRunInput(run_id=run_id, answer="Use national archives."),
        )
        ctx = read_case_context(
            conn,
            ReadCaseContextInput(case_id=case_id, claim_token=token),
        )
        assert ctx.held_run.status == "claimed"
        assert ctx.held_run.run_id == run_id
        assert ctx.held_run.current_suspension is not None
        assert ctx.held_run.current_suspension.human_answer == "Use national archives."
        assert any(s.human_answer == "Use national archives." for s in ctx.held_run.suspensions)


# --- Additional load-bearing pairs (not filler) -------------------------------


def test_second_claim_next_run_does_not_hand_out_held_run(engine: Engine) -> None:
    """F-25b: while a run is claimed, claim_next_run must not give it to a second holder."""
    _case_id, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        second = claim_next_run(conn, ClaimNextRunInput())
        # Idle success — no second concurrent claim of the same run.
        assert second.run is None
        # Original token still holds via context.
        ctx = read_case_context(
            conn,
            ReadCaseContextInput(case_id=_case_id, claim_token=token),
        )
        assert ctx.held_run.run_id == run_id


def test_propose_claim_then_close_refuses_examining_cited(engine: Engine, tmp_path: Path) -> None:
    """F-32: after propose_claim cites a capture, close_run cannot report it examined."""
    _case_id, run_id, token = _claimed(engine)
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/cited",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        elem = cap.elements[0]
        propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Cited.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
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
                    examined_capture_ids=[cap.capture_id],
                ),
            )
        assert exc.value.code == "EXAMINED_CAPTURE_ALREADY_CITED"


def test_cancel_with_unexamined_then_attest_after_report(engine: Engine, tmp_path: Path) -> None:
    """Cancel leaves unexamined captures; attest with examined_capture_ids can clear them."""
    vault = VaultStore(tmp_path / "vault")
    case_id, run_id, token = _claimed(engine)
    with connection_scope(engine) as conn:
        # Foundation claim path
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/main",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        elem = cap.elements[0]
        propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Main claim.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=elem.locator,
                quoted_text=elem.text,
            ),
        )
        close_run(conn, CloseRunInput(run_id=run_id, claim_token=token))

        # Second run cancelled mid-capture
        r2 = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Side?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=r2.run_id))
        c2 = claim_next_run(conn, ClaimNextRunInput())
        assert c2.run is not None
        orphan = capture_url(
            conn,
            CaptureUrlInput(
                run_id=c2.run.run_id,
                url="https://example.com/orphan",
                claim_token=c2.run.claim_token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        cancel_run(conn, CancelRunInput(run_id=c2.run.run_id))

        with pytest.raises(DeskRefusal) as blocked:
            attest_coverage(
                conn,
                AttestCoverageInput(case_id=case_id, stage="official_foundation"),
            )
        assert blocked.value.code == "COVERAGE_UNEXAMINED_REMAIN"

        result = attest_coverage(
            conn,
            AttestCoverageInput(
                case_id=case_id,
                stage="official_foundation",
                examined_capture_ids=[orphan.capture_id],
            ),
        )
        assert result.reading == "complete"
        assert result.captures_marked_examined == 1
