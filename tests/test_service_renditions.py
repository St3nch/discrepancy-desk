"""Seam tests for propose_rendition (ticket 12 / D2 / D7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    assert_official_foundation_complete,
    attest_coverage,
    capture_url,
    choose_angle,
    claim_next_run,
    close_run,
    create_angle,
    create_case,
    create_run,
    get_case,
    get_case_coverage,
    propose_claim,
    propose_rendition,
    read_case_context,
)
from desk.service.models import (
    ApproveRunInput,
    AssertOfficialFoundationInput,
    AttestCoverageInput,
    CaptureUrlInput,
    ChooseAngleInput,
    ClaimNextRunInput,
    CloseRunInput,
    CreateAngleInput,
    CreateCaseInput,
    CreateRunInput,
    EvidenceDimensions,
    GetCaseCoverageInput,
    GetCaseInput,
    LinkClaimDimensions,
    ProposeClaimInput,
    ProposeRenditionInput,
    ReadCaseContextInput,
    RenditionUnitInput,
)
from desk.vault.store import VaultStore

_HTML = b"""<!DOCTYPE html><html><body>
<p>The agency published finding Alpha on 12 March.</p>
<p>A witness said the timeline was wrong.</p>
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


def _seed_chosen_angle(
    engine: Engine, vault: VaultStore, *, with_qualification: bool = False
) -> tuple[int, int, int, int]:
    """Return (case_id, angle_id, claim_id, second_claim_id_on_other_angle_or_0)."""
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Rendition case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="What did the agency publish?",
                scope="official",
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
                url="https://example.com/agency",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html,
        )
        el0 = cap.elements[0]
        el1 = cap.elements[1]
        dims_a = _dims()
        qual = ""
        if with_qualification:
            dims_a = _dims(posture="allegation")
            qual = "according to a single contemporaneous report"
        claim_a = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Agency published finding Alpha.",
                dimensions=dims_a,
                qualification=qual,
                capture_id=cap.capture_id,
                locator=el0.locator,
                quoted_text=el0.text,
            ),
        )
        claim_b = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="A witness disputed the timeline.",
                dimensions=_dims(posture="participant_account"),
                qualification="participant recollection, uncorroborated",
                capture_id=cap.capture_id,
                locator=el1.locator,
                quoted_text=el1.text,
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

        link_dims_a = _link_dims()
        if with_qualification:
            link_dims_a = _link_dims(
                posture="allegation",
                qualification="according to a single contemporaneous report",
            )
        angle = create_angle(
            conn,
            CreateAngleInput(
                case_id=case.case_id,
                title="Alpha was published but the timeline is disputed",
                summary="Agency finding vs witness account.",
                claim_ids=[claim_a.claim_id],
                dimensions_by_claim_id={claim_a.claim_id: link_dims_a},
            ),
        )
        # Second angle holds claim_b only — for CLAIM_NOT_ON_ANGLE tests.
        other = create_angle(
            conn,
            CreateAngleInput(
                case_id=case.case_id,
                title="Witness-only angle",
                claim_ids=[claim_b.claim_id],
                dimensions_by_claim_id={
                    claim_b.claim_id: _link_dims(
                        posture="participant_account",
                        qualification="participant recollection, uncorroborated",
                    )
                },
            ),
        )
        del other
        choose_angle(conn, ChooseAngleInput(angle_id=angle.angle_id))
        return case.case_id, angle.angle_id, claim_a.claim_id, claim_b.claim_id


def _composition_token(engine: Engine, case_id: int) -> tuple[int, str]:
    with connection_scope(engine) as conn:
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="Compose an X thread for the chosen angle.",
                scope="composition",
                coverage_dimension="composition",
                capture_budget=1,
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        return claimed.run.run_id, claimed.run.claim_token


def test_propose_rendition_happy_path(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, angle_id, claim_id, _ = _seed_chosen_angle(engine, vault)
    run_id, token = _composition_token(engine, case_id)

    with connection_scope(engine) as conn:
        result = propose_rendition(
            conn,
            ProposeRenditionInput(
                run_id=run_id,
                claim_token=token,
                angle_id=angle_id,
                platform="x",
                format="thread",
                units=[
                    RenditionUnitInput(
                        body="Finding Alpha was published on 12 March.",
                        claim_ids=[claim_id],
                    ),
                    RenditionUnitInput(
                        body="That is the spine of the official record.",
                        claim_ids=[claim_id],
                    ),
                ],
            ),
        )
        assert result.status == "draft"
        assert result.platform == "x"
        assert result.format == "thread"
        assert result.angle_id == angle_id
        assert len(result.units) == 2
        assert result.units[0].ordinal == 0
        assert result.units[0].claim_ids == [claim_id]
        assert result.rubric_version  # from the composition run

        detail = get_case(conn, GetCaseInput(case_id=case_id))
        assert len(detail.renditions) == 1
        assert detail.renditions[0].units[0].body.startswith("Finding Alpha")

        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        composition = next(s for s in gauge.stages if s.stage == "composition")
        assert composition.reading == "worked"
        story = next(s for s in gauge.stages if s.stage == "story_intelligence")
        assert story.reading == "unmeasurable"

        ctx = read_case_context(conn, ReadCaseContextInput(case_id=case_id, claim_token=token))
        assert len(ctx.angles) >= 1
        assert len(ctx.renditions) == 1


def test_refuse_unconfirmed_and_wrong_angle(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Refuse cites"))
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
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        token = claimed.run.claim_token
        run_id = claimed.run.run_id
        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/r", claim_token=token),
            vault=vault,
            fetch=_html,
        )
        el0 = cap.elements[0]
        el1 = cap.elements[1]
        claim_linked = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Linked claim.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=el0.locator,
                quoted_text=el0.text,
            ),
        )
        claim_unconfirmed = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Unconfirmed claim.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=el1.locator,
                quoted_text=el1.text,
            ),
        )
        close_run(conn, CloseRunInput(run_id=run_id, claim_token=token))
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )
        angle_a = create_angle(
            conn,
            CreateAngleInput(
                case_id=case.case_id,
                title="A",
                claim_ids=[claim_linked.claim_id],
                dimensions_by_claim_id={claim_linked.claim_id: _link_dims()},
            ),
        )
        # Confirm claim_unconfirmed onto a different angle only.
        angle_b = create_angle(
            conn,
            CreateAngleInput(
                case_id=case.case_id,
                title="B",
                claim_ids=[claim_unconfirmed.claim_id],
                dimensions_by_claim_id={claim_unconfirmed.claim_id: _link_dims()},
            ),
        )
        # Re-unconfirm path: propose a third never-linked claim.
        # claim_unconfirmed is confirmed on angle_b; use it for wrong-angle.
        # Add a fresh unconfirmed via new run after choosing.
        choose_angle(conn, ChooseAngleInput(angle_id=angle_a.angle_id))
        case_id = case.case_id
        angle_id = angle_a.angle_id
        linked_id = claim_linked.claim_id
        other_angle_claim = claim_unconfirmed.claim_id  # confirmed on B, not A
        del angle_b

    # Fresh unconfirmed claim on a research run that we close without linking.
    with connection_scope(engine) as conn:
        r2 = create_run(
            conn,
            CreateRunInput(
                case_id=case_id,
                question="side",
                scope="s",
                coverage_dimension="deep_context",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=r2.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=claimed.run.run_id,
                url="https://example.com/side",
                claim_token=claimed.run.claim_token,
            ),
            vault=vault,
            fetch=_html,
        )
        el = cap.elements[0]
        unconfirmed = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=claimed.run.claim_token,
                proposition="Never linked.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=el.locator,
                quoted_text=el.text,
            ),
        )
        close_run(
            conn,
            CloseRunInput(run_id=claimed.run.run_id, claim_token=claimed.run.claim_token),
        )
        unconfirmed_id = unconfirmed.claim_id

    run_id, token = _composition_token(engine, case_id)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_u:
            propose_rendition(
                conn,
                ProposeRenditionInput(
                    run_id=run_id,
                    claim_token=token,
                    angle_id=angle_id,
                    platform="x",
                    format="thread",
                    units=[
                        RenditionUnitInput(body="Uses unconfirmed.", claim_ids=[unconfirmed_id])
                    ],
                ),
            )
        assert exc_u.value.code == "CLAIM_UNCONFIRMED"

        with pytest.raises(DeskRefusal) as exc_a:
            propose_rendition(
                conn,
                ProposeRenditionInput(
                    run_id=run_id,
                    claim_token=token,
                    angle_id=angle_id,
                    platform="x",
                    format="thread",
                    units=[
                        RenditionUnitInput(
                            body="Uses other angle claim.",
                            claim_ids=[other_angle_claim],
                        )
                    ],
                ),
            )
        assert exc_a.value.code == "CLAIM_NOT_ON_ANGLE"

        # Sanity: eligible claim still works.
        ok = propose_rendition(
            conn,
            ProposeRenditionInput(
                run_id=run_id,
                claim_token=token,
                angle_id=angle_id,
                platform="x",
                format="thread",
                units=[RenditionUnitInput(body="Linked only.", claim_ids=[linked_id])],
            ),
        )
        assert ok.status == "draft"


def test_refuse_missing_qualification(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, angle_id, claim_id, _ = _seed_chosen_angle(engine, vault, with_qualification=True)
    run_id, token = _composition_token(engine, case_id)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc:
            propose_rendition(
                conn,
                ProposeRenditionInput(
                    run_id=run_id,
                    claim_token=token,
                    angle_id=angle_id,
                    platform="x",
                    format="thread",
                    units=[
                        RenditionUnitInput(
                            body="Alpha was published — no qual text here.",
                            claim_ids=[claim_id],
                        )
                    ],
                ),
            )
        assert exc.value.code == "QUALIFICATION_MISSING_FROM_UNIT"

        ok = propose_rendition(
            conn,
            ProposeRenditionInput(
                run_id=run_id,
                claim_token=token,
                angle_id=angle_id,
                platform="x",
                format="thread",
                units=[
                    RenditionUnitInput(
                        body=("Alpha was published, according to a single contemporaneous report."),
                        claim_ids=[claim_id],
                    )
                ],
            ),
        )
        assert ok.status == "draft"


def test_refuse_angle_not_chosen(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, angle_id, claim_id, _ = _seed_chosen_angle(engine, vault)
    # Create a second active (not chosen) angle with the same claim.
    with connection_scope(engine) as conn:
        active = create_angle(
            conn,
            CreateAngleInput(
                case_id=case_id,
                title="Not chosen",
                claim_ids=[claim_id],
            ),
        )
        active_id = active.angle_id
    run_id, token = _composition_token(engine, case_id)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc:
            propose_rendition(
                conn,
                ProposeRenditionInput(
                    run_id=run_id,
                    claim_token=token,
                    angle_id=active_id,
                    platform="x",
                    format="thread",
                    units=[RenditionUnitInput(body="Nope.", claim_ids=[claim_id])],
                ),
            )
        assert exc.value.code == "ANGLE_NOT_CHOSEN"


def test_composition_unworked_until_rendition(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    case_id, _, _, _ = _seed_chosen_angle(engine, vault)
    with connection_scope(engine) as conn:
        gauge = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        composition = next(s for s in gauge.stages if s.stage == "composition")
        assert composition.reading == "unworked"
        story = next(s for s in gauge.stages if s.stage == "story_intelligence")
        assert story.reading == "unmeasurable"
        assert story.note is not None
        assert "decision" in story.note.lower() or "not" in story.note.lower()
