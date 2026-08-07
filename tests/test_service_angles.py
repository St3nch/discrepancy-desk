"""Seam tests for Angle Room and claim confirmation (ticket 11 / D21)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from desk.db.schema import claim_confirmations
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    add_quotation_to_shelf,
    approve_run,
    assert_official_foundation_complete,
    attest_coverage,
    capture_url,
    choose_angle,
    claim_next_run,
    close_run,
    create_angle,
    create_case,
    create_public_question,
    create_run,
    dismiss_angle,
    get_case,
    get_case_coverage,
    link_claim_to_angle,
    link_claim_to_public_question,
    list_rendition_eligible_claims,
    propose_claim,
)
from desk.service.models import (
    AddQuotationShelfInput,
    ApproveRunInput,
    AssertOfficialFoundationInput,
    AttestCoverageInput,
    CaptureUrlInput,
    ChooseAngleInput,
    ClaimNextRunInput,
    CloseRunInput,
    CreateAngleInput,
    CreateCaseInput,
    CreatePublicQuestionInput,
    CreateRunInput,
    DismissAngleInput,
    EvidenceDimensions,
    GetCaseCoverageInput,
    GetCaseInput,
    LinkClaimDimensions,
    LinkClaimToAngleInput,
    LinkClaimToPublicQuestionInput,
    ProposeClaimInput,
    RenditionEligibleClaimsInput,
)
from desk.vault.store import VaultStore

_HTML = b"""<!DOCTYPE html><html><body>
<p>The official finding stated X.</p>
<p>A participant said Y.</p>
</body></html>"""


def _html(_url: str) -> tuple[bytes, str]:
    return _HTML, "text/html"


def _dims(**overrides: str) -> EvidenceDimensions:
    base = dict(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )
    base.update(overrides)
    return EvidenceDimensions(**base)  # type: ignore[arg-type]


def _link_dims(**overrides: str) -> LinkClaimDimensions:
    base = dict(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )
    base.update(overrides)
    return LinkClaimDimensions(**base)  # type: ignore[arg-type]


def _foundation_ready(engine: Engine, vault: VaultStore) -> tuple[int, int]:
    """Return (case_id, claim_id) with complete official foundation and one claim."""
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Angle case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="What is the official record?",
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
                url="https://example.com/official",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html,
        )
        el = cap.elements[0]
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Official finding stated X.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=el.locator,
                quoted_text=el.text,
            ),
        )
        close_run(conn, CloseRunInput(run_id=run_id, claim_token=token))
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )
        assert_official_foundation_complete(
            conn, AssertOfficialFoundationInput(case_id=case.case_id)
        )
        return case.case_id, claim.claim_id


def test_create_angle_refuses_without_foundation(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="No foundation"))
        with pytest.raises(DeskRefusal) as exc:
            create_angle(
                conn,
                CreateAngleInput(case_id=case.case_id, title="Too soon"),
            )
        assert exc.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"


def test_confirm_preserves_proposal_history(engine: Engine, tmp_path: Path) -> None:
    """VISION §18: confirmation row keeps proposed vs confirmed dimensions."""
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        create_angle(
            conn,
            CreateAngleInput(
                case_id=case_id,
                title="The discrepancy",
                claim_ids=[claim_id],
                dimensions_by_claim_id={
                    claim_id: _link_dims(certainty="established"),  # correction
                },
            ),
        )
        row = conn.execute(
            select(
                claim_confirmations.c.proposed_certainty,
                claim_confirmations.c.confirmed_certainty,
                claim_confirmations.c.actor,
                claim_confirmations.c.confirmed_at,
            ).where(claim_confirmations.c.claim_id == claim_id)
        ).one()
        assert str(row.proposed_certainty) == "probable"
        assert str(row.confirmed_certainty) == "established"
        assert str(row.actor) == "operator"
        assert row.confirmed_at is not None

        detail = get_case(conn, GetCaseInput(case_id=case_id))
        cl = next(c for c in detail.claims if c.claim_id == claim_id)
        assert cl.confirmation_status == "confirmed"
        assert cl.certainty == "established"
        assert cl.confirmed_at is not None


def test_link_confirm_timestamp_and_angle_scoped_eligible(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        a = create_angle(
            conn,
            CreateAngleInput(
                case_id=case_id,
                title="Angle A",
                claim_ids=[claim_id],
                dimensions_by_claim_id={claim_id: _link_dims(certainty="established")},
            ),
        )
        b = create_angle(conn, CreateAngleInput(case_id=case_id, title="Angle B empty"))

        eligible_a = list_rendition_eligible_claims(
            conn, RenditionEligibleClaimsInput(angle_id=a.angle_id)
        )
        assert eligible_a.angle_id == a.angle_id
        assert eligible_a.case_id == case_id
        assert all(c.confirmation_status == "confirmed" for c in eligible_a.claims)
        assert any(c.claim_id == claim_id for c in eligible_a.claims)

        eligible_b = list_rendition_eligible_claims(
            conn, RenditionEligibleClaimsInput(angle_id=b.angle_id)
        )
        assert eligible_b.claims == []


def test_choose_requires_linked_claims(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        empty = create_angle(conn, CreateAngleInput(case_id=case_id, title="Draft"))
        with pytest.raises(DeskRefusal) as exc:
            choose_angle(conn, ChooseAngleInput(angle_id=empty.angle_id))
        assert exc.value.code == "ANGLE_HAS_NO_CLAIMS"

        with_claim = create_angle(
            conn,
            CreateAngleInput(
                case_id=case_id,
                title="Real",
                claim_ids=[claim_id],
                dimensions_by_claim_id={claim_id: _link_dims()},
            ),
        )
        chosen = choose_angle(conn, ChooseAngleInput(angle_id=with_claim.angle_id))
        assert chosen.status == "chosen"


def test_dismiss_immutable(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, _ = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        b = create_angle(conn, CreateAngleInput(case_id=case_id, title="B"))
        dismissed = dismiss_angle(
            conn,
            DismissAngleInput(angle_id=b.angle_id, reason="Weaker framing."),
        )
        assert dismissed.status == "dismissed"
        assert dismissed.dismissal_reason == "Weaker framing."
        with pytest.raises(DeskRefusal) as exc:
            dismiss_angle(
                conn,
                DismissAngleInput(angle_id=b.angle_id, reason="Overwrite?"),
            )
        assert exc.value.code == "ANGLE_ALREADY_DISMISSED"


def test_public_question_links_claims_and_coverage(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        pq = create_public_question(
            conn,
            CreatePublicQuestionInput(
                case_id=case_id,
                question_text="What really happened that night?",
                circulating_version="The cover-up version",
                where_asked="Forums and late-night radio",
                origin="1997 magazine piece",
            ),
        )
        # Draft PQ without claims: still not a claim; coverage stays unworked.
        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        pq_stage = next(s for s in gauge.stages if s.stage == "public_question")
        assert pq_stage.reading == "unworked"

        linked = link_claim_to_public_question(
            conn,
            LinkClaimToPublicQuestionInput(
                public_question_id=pq.public_question_id,
                claim_id=claim_id,
                dimensions=_link_dims(),
            ),
        )
        assert claim_id in linked.claim_ids
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        assert any(q.public_question_id == pq.public_question_id for q in detail.public_questions)
        assert all("cover-up" not in c.proposition for c in detail.claims)

        gauge2 = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        pq2 = next(s for s in gauge2.stages if s.stage == "public_question")
        assert pq2.reading == "worked"

        ed = next(s for s in gauge2.stages if s.stage == "editorial_development")
        # No angle with claims yet
        assert ed.reading == "unworked"

        create_angle(
            conn,
            CreateAngleInput(
                case_id=case_id,
                title="With claim",
                claim_ids=[claim_id],
                dimensions_by_claim_id={},  # already confirmed via PQ link
            ),
        )
        gauge3 = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        ed3 = next(s for s in gauge3.stages if s.stage == "editorial_development")
        assert ed3.reading == "worked"

        si = next(s for s in gauge3.stages if s.stage == "story_intelligence")
        comp = next(s for s in gauge3.stages if s.stage == "composition")
        assert si.reading == "unmeasurable"
        # Composition is object-backed from ticket 12; no renditions yet → unworked.
        assert comp.reading == "unworked"


def test_f24_categorical_unknown_fails_closed(engine: Engine, tmp_path: Path) -> None:
    """D21: citing unknown cannot be recorded as institution (ladder hole closed)."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="F24 cat"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Q?",
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
                url="https://example.com/p",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html,
        )
        unknown_claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Someone said Y.",
                dimensions=_dims(publication_risk="unknown"),
                capture_id=cap.capture_id,
                locator="e/1",
                quoted_text="A participant said Y.",
            ),
        )
        with pytest.raises(DeskRefusal) as exc:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="Therefore X.",
                    dimensions=_dims(
                        source_basis="desk_inference",
                        publication_risk="institution",
                    ),
                    cited_claim_ids=[unknown_claim.claim_id],
                ),
            )
        assert exc.value.code == "INFERENCE_PUBLICATION_RISK_LAUNDER"

        # living_private same rule
        private = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Living person said Y.",
                dimensions=_dims(
                    posture="participant_account",
                    publication_risk="living_private",
                    certainty="probable",
                ),
                qualification="According to the participant.",
                capture_id=cap.capture_id,
                locator="e/1",
                quoted_text="A participant said Y.",
            ),
        )
        with pytest.raises(DeskRefusal) as exc2:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="Therefore laundered.",
                    dimensions=_dims(
                        source_basis="desk_inference",
                        publication_risk="not_applicable",
                    ),
                    cited_claim_ids=[private.claim_id],
                ),
            )
        assert exc2.value.code == "INFERENCE_PUBLICATION_RISK_LAUNDER"


def test_inference_confirm_requires_cited_confirmed(engine: Engine, tmp_path: Path) -> None:
    """D21 bottom-up: cannot confirm inference while citations are unconfirmed."""
    vault = VaultStore(tmp_path / "vault")
    case_id, base_claim = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        # New run to propose inference over unconfirmed? base is still unconfirmed
        # until linked. Propose inference citing base while both unconfirmed.
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Infer?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        inf = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
                proposition="Therefore the finding matters.",
                dimensions=_dims(source_basis="desk_inference"),
                cited_claim_ids=[base_claim],
            ),
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
            ),
        )
        # base_claim still unconfirmed — linking inference must refuse
        angle = create_angle(conn, CreateAngleInput(case_id=case_id, title="Inf"))
        with pytest.raises(DeskRefusal) as exc:
            link_claim_to_angle(
                conn,
                LinkClaimToAngleInput(
                    angle_id=angle.angle_id,
                    claim_id=inf.claim_id,
                    dimensions=_link_dims(source_basis="desk_inference"),
                ),
            )
        assert exc.value.code == "INFERENCE_CITATIONS_UNCONFIRMED"

        # Confirm base first, then inference
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=angle.angle_id,
                claim_id=base_claim,
                dimensions=_link_dims(),
            ),
        )
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=angle.angle_id,
                claim_id=inf.claim_id,
                dimensions=_link_dims(source_basis="desk_inference"),
            ),
        )
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        assert next(c for c in detail.claims if c.claim_id == inf.claim_id).confirmation_status == (
            "confirmed"
        )


def test_operator_selected_shelf_not_dump(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        create_angle(
            conn,
            CreateAngleInput(
                case_id=case_id,
                title="With claim",
                claim_ids=[claim_id],
                dimensions_by_claim_id={claim_id: _link_dims()},
            ),
        )
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        # Linking does not auto-fill the shelf.
        assert detail.quotation_shelf == []

        cl = next(c for c in detail.claims if c.claim_id == claim_id)
        qb = cl.quote_bindings[0]
        added = add_quotation_to_shelf(
            conn,
            AddQuotationShelfInput(
                case_id=case_id,
                claim_id=claim_id,
                capture_id=qb.capture_id,
                locator=qb.locator,
                quoted_text=qb.quoted_text,
                speaker="The official report",
                attribution_frame="as stated in the finding",
            ),
        )
        assert added.speaker == "The official report"
        assert added.locator == qb.locator

        detail2 = get_case(conn, GetCaseInput(case_id=case_id))
        assert len(detail2.quotation_shelf) == 1
        assert detail2.quotation_shelf[0].speaker == "The official report"


def test_region_locator_on_shelf_when_selected(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, _base = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Quote?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        token = claimed.run.claim_token
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=claimed.run.run_id,
                url="https://example.com/q",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html,
        )
        text = "The official finding stated X."
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=token,
                proposition="Partial quote.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator="e/0/r/0-11",
                quoted_text=text[0:11],
            ),
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=claimed.run.run_id,
                claim_token=token,
            ),
        )
        add_quotation_to_shelf(
            conn,
            AddQuotationShelfInput(
                case_id=case_id,
                claim_id=claim.claim_id,
                capture_id=cap.capture_id,
                locator="e/0/r/0-11",
                quoted_text=text[0:11],
                speaker="Official source",
                attribution_frame="partial quote from finding",
                dimensions=_link_dims(),
            ),
        )
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        assert any(
            item.locator == "e/0/r/0-11" and item.quoted_text == text[0:11]
            for item in detail.quotation_shelf
        )


def _stale_foundation_after_angle(engine: Engine, vault: VaultStore, case_id: int) -> None:
    """Add an unexamined capture so official_foundation attestation goes stale."""
    with connection_scope(engine) as conn:
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Later material?",
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
                url="https://example.com/later",
                claim_token=claimed.run.claim_token,
            ),
            vault=vault,
            fetch=_html,
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
            ),
        )


def test_gate_on_every_angle_room_path(engine: Engine, tmp_path: Path) -> None:
    """D20: each angle-start / confirmation path refuses when foundation incomplete."""
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)

    with connection_scope(engine) as conn:
        angle = create_angle(
            conn,
            CreateAngleInput(case_id=case_id, title="Gate target"),
        )
        angle_id = angle.angle_id
        pq = create_public_question(
            conn,
            CreatePublicQuestionInput(
                case_id=case_id,
                question_text="Q?",
                circulating_version="v",
                where_asked="here",
                origin="there",
            ),
        )
        pq_id = pq.public_question_id

    _stale_foundation_after_angle(engine, vault, case_id)

    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_create:
            create_angle(conn, CreateAngleInput(case_id=case_id, title="Blocked"))
        assert exc_create.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"

        with pytest.raises(DeskRefusal) as exc_link:
            link_claim_to_angle(
                conn,
                LinkClaimToAngleInput(
                    angle_id=angle_id,
                    claim_id=claim_id,
                    dimensions=_link_dims(),
                ),
            )
        assert exc_link.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"

        with pytest.raises(DeskRefusal) as exc_dismiss:
            dismiss_angle(
                conn,
                DismissAngleInput(angle_id=angle_id, reason="Would dismiss."),
            )
        assert exc_dismiss.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"

        with pytest.raises(DeskRefusal) as exc_choose:
            choose_angle(conn, ChooseAngleInput(angle_id=angle_id))
        assert exc_choose.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"

        with pytest.raises(DeskRefusal) as exc_pq:
            create_public_question(
                conn,
                CreatePublicQuestionInput(
                    case_id=case_id,
                    question_text="Q2?",
                    circulating_version="v",
                    where_asked="here",
                    origin="there",
                ),
            )
        assert exc_pq.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"

        with pytest.raises(DeskRefusal) as exc_pq_link:
            link_claim_to_public_question(
                conn,
                LinkClaimToPublicQuestionInput(
                    public_question_id=pq_id,
                    claim_id=claim_id,
                    dimensions=_link_dims(),
                ),
            )
        assert exc_pq_link.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"

        with pytest.raises(DeskRefusal) as exc_shelf:
            add_quotation_to_shelf(
                conn,
                AddQuotationShelfInput(
                    case_id=case_id,
                    claim_id=claim_id,
                    capture_id=1,
                    locator="e/0",
                    quoted_text="x",
                    speaker="s",
                    attribution_frame="a",
                    dimensions=_link_dims(),
                ),
            )
        assert exc_shelf.value.code == "OFFICIAL_FOUNDATION_INCOMPLETE"


def test_link_requires_dimensions_when_unconfirmed(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        angle = create_angle(conn, CreateAngleInput(case_id=case_id, title="Need dims"))
        with pytest.raises(DeskRefusal) as exc:
            link_claim_to_angle(
                conn,
                LinkClaimToAngleInput(angle_id=angle.angle_id, claim_id=claim_id),
            )
        assert exc.value.code == "CONFIRMATION_DIMENSIONS_REQUIRED"


def test_refuse_confirm_crossing_to_inference(engine: Engine, tmp_path: Path) -> None:
    """D21 door: cannot reclassify a capture-bound claim as desk_inference at confirm."""
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        angle = create_angle(conn, CreateAngleInput(case_id=case_id, title="Boundary"))
        with pytest.raises(DeskRefusal) as exc:
            link_claim_to_angle(
                conn,
                LinkClaimToAngleInput(
                    angle_id=angle.angle_id,
                    claim_id=claim_id,
                    dimensions=_link_dims(source_basis="desk_inference"),
                ),
            )
        assert exc.value.code == "SOURCE_BASIS_KIND_MISMATCH"
        # Still unconfirmed — boundary refuse wrote nothing.
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        cl = next(c for c in detail.claims if c.claim_id == claim_id)
        assert cl.confirmation_status == "unconfirmed"
        assert cl.source_basis == "contemporaneous_report"


def test_refuse_confirm_crossing_from_inference(engine: Engine, tmp_path: Path) -> None:
    """Cannot reclassify a desk_inference claim as a non-inference basis at confirm."""
    vault = VaultStore(tmp_path / "vault")
    case_id, base_claim = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Infer?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        inf = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
                proposition="Therefore X.",
                dimensions=_dims(source_basis="desk_inference"),
                cited_claim_ids=[base_claim],
            ),
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
            ),
        )
        angle = create_angle(conn, CreateAngleInput(case_id=case_id, title="From-inf"))
        # Confirm base so only the kind mismatch is under test if we tried inference
        # path — here we try to confirm inference as contemporaneous_report.
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=angle.angle_id,
                claim_id=base_claim,
                dimensions=_link_dims(),
            ),
        )
        with pytest.raises(DeskRefusal) as exc:
            link_claim_to_angle(
                conn,
                LinkClaimToAngleInput(
                    angle_id=angle.angle_id,
                    claim_id=inf.claim_id,
                    dimensions=_link_dims(source_basis="contemporaneous_report"),
                ),
            )
        assert exc.value.code == "SOURCE_BASIS_KIND_MISMATCH"
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        cl = next(c for c in detail.claims if c.claim_id == inf.claim_id)
        assert cl.confirmation_status == "unconfirmed"
        assert cl.source_basis == "desk_inference"


def test_reconfirm_appends_history_and_updates_projection(engine: Engine, tmp_path: Path) -> None:
    """Re-confirmation writes a new claim_confirmations row (§10 correction-rate)."""
    vault = VaultStore(tmp_path / "vault")
    case_id, claim_id = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        a1 = create_angle(conn, CreateAngleInput(case_id=case_id, title="A1"))
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=a1.angle_id,
                claim_id=claim_id,
                dimensions=_link_dims(certainty="probable"),
            ),
        )
        assert (
            len(
                conn.execute(
                    select(claim_confirmations.c.id).where(
                        claim_confirmations.c.claim_id == claim_id
                    )
                ).all()
            )
            == 1
        )

        a2 = create_angle(conn, CreateAngleInput(case_id=case_id, title="A2"))
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=a2.angle_id,
                claim_id=claim_id,
                dimensions=_link_dims(certainty="established"),  # correction
            ),
        )
        rows = conn.execute(
            select(
                claim_confirmations.c.proposed_certainty,
                claim_confirmations.c.confirmed_certainty,
            )
            .where(claim_confirmations.c.claim_id == claim_id)
            .order_by(claim_confirmations.c.id.asc())
        ).all()
        assert len(rows) == 2
        assert str(rows[0].proposed_certainty) == "probable"  # model proposal
        assert str(rows[0].confirmed_certainty) == "probable"
        assert str(rows[1].proposed_certainty) == "probable"  # prior authoritative
        assert str(rows[1].confirmed_certainty) == "established"

        detail = get_case(conn, GetCaseInput(case_id=case_id))
        cl = next(c for c in detail.claims if c.claim_id == claim_id)
        assert cl.certainty == "established"


def test_reconfirm_to_nonpublishable_blocked_by_confirmed_inference(
    engine: Engine, tmp_path: Path
) -> None:
    """D21: cannot re-confirm basis to living_private under a confirmed inference."""
    vault = VaultStore(tmp_path / "vault")
    case_id, base_claim = _foundation_ready(engine, vault)
    with connection_scope(engine) as conn:
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Infer?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        # Base is not_applicable; inference over it as not_applicable is fine.
        inf = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
                proposition="Therefore X.",
                dimensions=_dims(source_basis="desk_inference"),
                cited_claim_ids=[base_claim],
            ),
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
            ),
        )
        angle = create_angle(conn, CreateAngleInput(case_id=case_id, title="Block"))
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=angle.angle_id,
                claim_id=base_claim,
                dimensions=_link_dims(publication_risk="not_applicable"),
            ),
        )
        link_claim_to_angle(
            conn,
            LinkClaimToAngleInput(
                angle_id=angle.angle_id,
                claim_id=inf.claim_id,
                dimensions=_link_dims(source_basis="desk_inference"),
            ),
        )
        # Re-confirm base to living_private via second angle link with dims
        a2 = create_angle(conn, CreateAngleInput(case_id=case_id, title="Reconfirm"))
        with pytest.raises(DeskRefusal) as exc:
            link_claim_to_angle(
                conn,
                LinkClaimToAngleInput(
                    angle_id=a2.angle_id,
                    claim_id=base_claim,
                    dimensions=_link_dims(publication_risk="living_private"),
                ),
            )
        assert exc.value.code == "CONFIRMATION_BLOCKED_BY_INFERENCE"
        assert str(inf.claim_id) in exc.value.what_happened

        detail = get_case(conn, GetCaseInput(case_id=case_id))
        cl = next(c for c in detail.claims if c.claim_id == base_claim)
        assert cl.publication_risk == "not_applicable"
