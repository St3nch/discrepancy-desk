"""Seam tests for coverage gauge and official-foundation gate (ticket 10 / D20)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

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
    get_case_coverage,
    propose_claim,
)
from desk.service.coverage import COVERAGE_READINGS, COVERAGE_STAGE_IDS, COVERAGE_STAGE_ORDER
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
    ProposeClaimInput,
)
from desk.vault.store import VaultStore

_HTML = b"""<!DOCTYPE html><html><body>
<p>Official finding alpha.</p>
<p>Dissenting note beta.</p>
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


def _complete_dimension_run(
    conn: object,
    *,
    case_id: int,
    vault: VaultStore,
    dimension: str = "official_foundation",
    url: str = "https://example.com/a",
    extra_unexamined: bool = False,
) -> tuple[int, int, int | None]:
    """Complete a run targeting dimension with one claim. Return (run_id, cited_cap, extra_cap?)."""
    run = create_run(
        conn,  # type: ignore[arg-type]
        CreateRunInput(
            case_id=case_id,
            question="Q?",
            scope="s",
            coverage_dimension=dimension,
        ),
    )
    approve_run(conn, ApproveRunInput(run_id=run.run_id))  # type: ignore[arg-type]
    claimed = claim_next_run(conn, ClaimNextRunInput())  # type: ignore[arg-type]
    assert claimed.run is not None
    token = claimed.run.claim_token
    run_id = claimed.run.run_id
    cap = capture_url(
        conn,  # type: ignore[arg-type]
        CaptureUrlInput(run_id=run_id, url=url, claim_token=token),
        vault=vault,
        fetch=_html_fetch,
    )
    elem = cap.elements[0]
    propose_claim(
        conn,  # type: ignore[arg-type]
        ProposeClaimInput(
            run_id=run_id,
            claim_token=token,
            proposition="Alpha was stated.",
            dimensions=_dims(),
            capture_id=cap.capture_id,
            locator=elem.locator,
            quoted_text=elem.text,
        ),
    )
    extra_id: int | None = None
    examined: list[int] = []
    if extra_unexamined:
        cap2 = capture_url(
            conn,  # type: ignore[arg-type]
            CaptureUrlInput(run_id=run_id, url=url + "/extra", claim_token=token),
            vault=vault,
            fetch=_html_fetch,
        )
        extra_id = cap2.capture_id
        # Leave unexamined — not listed at close.
    close_run(
        conn,  # type: ignore[arg-type]
        CloseRunInput(
            run_id=run_id,
            claim_token=token,
            examined_capture_ids=examined,
        ),
    )
    return run_id, cap.capture_id, extra_id


def test_empty_case_and_unmeasurable_stages(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Empty"))
        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id))
        assert {s.stage for s in gauge.stages} == COVERAGE_STAGE_IDS
        assert [s.stage for s in gauge.stages] == [sid for sid, _ in COVERAGE_STAGE_ORDER]
        for s in gauge.stages:
            assert s.reading in COVERAGE_READINGS
        assert next(s for s in gauge.stages if s.stage == "official_foundation").reading == (
            "unworked"
        )
        # Ticket 11–12 objects make these measurable (empty → unworked, not unmeasurable).
        for stage_id in (
            "public_question",
            "editorial_development",
            "deep_context",
            "composition",
        ):
            assert next(s for s in gauge.stages if s.stage == stage_id).reading == "unworked"
        # Explicit unmeasurable: no measuring object — stated decision, not neglect (D20).
        assert (
            next(s for s in gauge.stages if s.stage == "story_intelligence").reading
            == "unmeasurable"
        )
        with pytest.raises(DeskRefusal) as exc:
            assert_official_foundation_complete(
                conn, AssertOfficialFoundationInput(case_id=case.case_id)
            )
        assert exc.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"


def test_pre_d20_null_dimension_does_not_count(engine: Engine, tmp_path: Path) -> None:
    """Pre-0013 runs have coverage_dimension NULL and never contribute to a stage."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Legacy"))
        # Create via service then strip dimension to simulate pre-D20 row.
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Legacy Q?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        token = claimed.run.claim_token
        run_id = claimed.run.run_id
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/legacy",
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
                proposition="Legacy claim.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=elem.locator,
                quoted_text=elem.text,
            ),
        )
        close_run(
            conn,
            CloseRunInput(run_id=run_id, claim_token=token),
        )
        # Simulate pre-D20: no operator dimension judgement.
        conn.execute(
            text("UPDATE runs SET coverage_dimension = NULL WHERE id = :id"),
            {"id": run_id},
        )

        of = next(
            s
            for s in get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id)).stages
            if s.stage == "official_foundation"
        )
        assert of.reading == "unworked"
        assert "0 completed run" in of.signals[0] or "0 completed run" in " ".join(of.signals)


def test_public_question_run_leaves_foundation_unworked(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Wrong dim"))
        _complete_dimension_run(
            conn,
            case_id=case.case_id,
            vault=vault,
            dimension="public_question",
        )
        of = next(
            s
            for s in get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id)).stages
            if s.stage == "official_foundation"
        )
        assert of.reading == "unworked"


def test_attest_refuses_while_unexamined_remain(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Unexamined refuse"))
        _run_id, _cited, extra = _complete_dimension_run(
            conn,
            case_id=case.case_id,
            vault=vault,
            extra_unexamined=True,
        )
        assert extra is not None
        of = next(
            s
            for s in get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id)).stages
            if s.stage == "official_foundation"
        )
        assert of.reading == "worked"

        with pytest.raises(DeskRefusal) as exc:
            attest_coverage(
                conn,
                AttestCoverageInput(
                    case_id=case.case_id,
                    stage="official_foundation",
                ),
            )
        assert exc.value.code == "COVERAGE_UNEXAMINED_REMAIN"
        assert "1" in exc.value.what_happened


def test_attest_succeeds_when_operator_reports_examined(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Report examined"))
        _run_id, _cited, extra = _complete_dimension_run(
            conn,
            case_id=case.case_id,
            vault=vault,
            extra_unexamined=True,
        )
        assert extra is not None
        result = attest_coverage(
            conn,
            AttestCoverageInput(
                case_id=case.case_id,
                stage="official_foundation",
                examined_capture_ids=[extra],
            ),
        )
        assert result.reading == "complete"
        assert result.captures_marked_examined == 1
        assert result.coverage.official_foundation_complete is True
        allowed = assert_official_foundation_complete(
            conn, AssertOfficialFoundationInput(case_id=case.case_id)
        )
        assert allowed.official_foundation_complete is True


def test_capture_after_attestation_makes_stale(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Stale after capture"))
        _complete_dimension_run(conn, case_id=case.case_id, vault=vault)
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )
        assert (
            get_case_coverage(
                conn, GetCaseCoverageInput(case_id=case.case_id)
            ).official_foundation_complete
            is True
        )

        # New run adds unexamined capture on the case.
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="More?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        capture_url(
            conn,
            CaptureUrlInput(
                run_id=claimed.run.run_id,
                url="https://example.com/after",
                claim_token=claimed.run.claim_token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )

        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id))
        of = next(s for s in gauge.stages if s.stage == "official_foundation")
        assert of.reading == "worked"
        assert "stale" in " ".join(of.signals).lower() or (
            of.note is not None and "stale" in of.note.lower()
        )
        assert gauge.official_foundation_complete is False


def test_lead_attached_after_attestation_makes_stale(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Lead attach stale"))
        _complete_dimension_run(conn, case_id=case.case_id, vault=vault)
        # Lead captured before attestation.
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/pre-lead", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )
        assert (
            get_case_coverage(
                conn, GetCaseCoverageInput(case_id=case.case_id)
            ).official_foundation_complete
            is True
        )

        attach_lead(
            conn,
            AttachLeadInput(lead_id=lead.lead_id, case_id=case.case_id),
        )
        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id))
        of = next(s for s in gauge.stages if s.stage == "official_foundation")
        assert of.reading == "worked"
        assert gauge.official_foundation_complete is False


def test_examined_or_cited_additions_do_not_stale(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="No stale on examined"))
        _complete_dimension_run(conn, case_id=case.case_id, vault=vault)
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )

        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Cite more?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        token = claimed.run.claim_token
        run_id = claimed.run.run_id
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/cited-after",
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
                proposition="Also true.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=elem.locator,
                quoted_text=elem.text,
            ),
        )
        # Second capture examined at close — no unexamined remain.
        cap2 = capture_url(
            conn,
            CaptureUrlInput(
                run_id=run_id,
                url="https://example.com/examined-after",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                examined_capture_ids=[cap2.capture_id],
            ),
        )

        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case.case_id))
        assert gauge.official_foundation_complete is True


def test_cancelled_run_unexamined_can_be_attested_via_report(
    engine: Engine, tmp_path: Path
) -> None:
    """F-26 wedge: cancel leaves unexamined captures; operator can report them examined."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Cancel wedge"))
        # Foundation work first.
        _complete_dimension_run(conn, case_id=case.case_id, vault=vault)

        # Second run: capture then cancel without examining.
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Abandoned thread?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=claimed.run.run_id,
                url="https://example.com/cancelled",
                claim_token=claimed.run.claim_token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        cancel_run(conn, CancelRunInput(run_id=claimed.run.run_id))

        with pytest.raises(DeskRefusal) as exc:
            attest_coverage(
                conn,
                AttestCoverageInput(
                    case_id=case.case_id,
                    stage="official_foundation",
                ),
            )
        assert exc.value.code == "COVERAGE_UNEXAMINED_REMAIN"

        result = attest_coverage(
            conn,
            AttestCoverageInput(
                case_id=case.case_id,
                stage="official_foundation",
                examined_capture_ids=[cap.capture_id],
            ),
        )
        assert result.reading == "complete"
