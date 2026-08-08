"""Seam tests for update_rendition / approve_rendition (ticket 13)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from desk.db.schema import rendition_approvals
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_rendition,
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
    propose_claim,
    propose_rendition,
    update_rendition,
)
from desk.service.confirmation import confirm_claim_for_use
from desk.service.models import (
    ApproveRenditionInput,
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
    GetCaseInput,
    LinkClaimDimensions,
    ProposeClaimInput,
    ProposeRenditionInput,
    RenditionUnitInput,
    UpdateRenditionInput,
)
from desk.service.renditions import describe_content_divergence
from desk.vault.store import VaultStore

_HTML = b"""<!DOCTYPE html><html><body>
<p>The agency published finding Alpha on 12 March.</p>
<p>A witness said the timeline was wrong.</p>
</body></html>"""


def _html(_url: str) -> tuple[bytes, str]:
    return _HTML, "text/html"


def _dims() -> EvidenceDimensions:
    return EvidenceDimensions(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )


def _link_dims() -> LinkClaimDimensions:
    return LinkClaimDimensions(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
        qualification="",
    )


def _seed_draft_thread(engine: Engine, tmp_path: Path) -> tuple[int, int, int, list[str]]:
    """Return case_id, rendition_id, claim_id, unit bodies."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Approval case"))
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
        cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=claimed.run.run_id,
                url="https://example.com/agency",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html,
        )
        el0 = cap.elements[0]
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=token,
                proposition="Agency published finding Alpha.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=el0.locator,
                quoted_text=el0.text,
            ),
        )
        close_run(conn, CloseRunInput(run_id=claimed.run.run_id, claim_token=token))
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )
        assert_official_foundation_complete(
            conn, AssertOfficialFoundationInput(case_id=case.case_id)
        )
        angle = create_angle(
            conn,
            CreateAngleInput(
                case_id=case.case_id,
                title="Alpha published",
                summary="Official record.",
                claim_ids=[claim.claim_id],
                dimensions_by_claim_id={claim.claim_id: _link_dims()},
            ),
        )
        choose_angle(conn, ChooseAngleInput(angle_id=angle.angle_id))

        comp = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Compose thread",
                scope="composition",
                coverage_dimension="composition",
                capture_budget=1,
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=comp.run_id))
        c2 = claim_next_run(conn, ClaimNextRunInput())
        assert c2.run is not None
        bodies = [
            "Finding Alpha was published on 12 March.",
            "That is the spine of the official record.",
        ]
        ren = propose_rendition(
            conn,
            ProposeRenditionInput(
                run_id=c2.run.run_id,
                claim_token=c2.run.claim_token,
                angle_id=angle.angle_id,
                platform="x",
                format="thread",
                units=[
                    RenditionUnitInput(body=bodies[0], claim_ids=[claim.claim_id]),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim.claim_id]),
                ],
            ),
        )
        return case.case_id, ren.rendition_id, claim.claim_id, bodies


def test_describe_content_divergence_order_vs_text() -> None:
    assert describe_content_divergence(["a", "b"], ["a", "b"]) == []
    notes = describe_content_divergence(["b", "a"], ["a", "b"])
    assert any("order" in n for n in notes)
    notes2 = describe_content_divergence(["a", "x"], ["a", "b"])
    assert any("text differs" in n for n in notes2)
    notes3 = describe_content_divergence(["a"], ["a", "b"])
    assert any("count" in n for n in notes3)


def test_approve_binds_ordered_content(engine: Engine, tmp_path: Path) -> None:
    case_id, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        cleared = approve_rendition(conn, ApproveRenditionInput(rendition_id=rid, actor="chaz"))
    assert cleared.status == "cleared"
    assert cleared.approval_stands is True
    assert cleared.approval_invalidation is None
    assert cleared.current_approval_id is not None
    assert cleared.current_approval is not None
    assert cleared.current_approval.actor == "chaz"
    assert [u.body for u in cleared.current_approval.units] == bodies
    assert len(cleared.approvals) == 1

    with connection_scope(engine) as conn:
        detail = get_case(conn, GetCaseInput(case_id=case_id))
    ren = detail.renditions[0]
    assert ren.approval_stands is True
    assert ren.units[0].claim_ids == [claim_id]


def test_edit_after_approval_invalidates_by_derivation(engine: Engine, tmp_path: Path) -> None:
    _, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))
        edited = update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[
                    RenditionUnitInput(
                        body=bodies[0] + " (edited)",
                        claim_ids=[claim_id],
                    ),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_id]),
                ],
            ),
        )
    # Status does not silently revert to draft.
    assert edited.status == "cleared"
    assert edited.approval_stands is False
    assert edited.approval_invalidation is not None
    assert "text" in edited.approval_invalidation.changes
    assert "differs" in edited.approval_invalidation.detail
    # Pointer still names the (now stale) clearance.
    assert edited.current_approval_id is not None
    assert len(edited.approvals) == 1


def test_reorder_after_approval_invalidates(engine: Engine, tmp_path: Path) -> None:
    _, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))
        reordered = update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_id]),
                    RenditionUnitInput(body=bodies[0], claim_ids=[claim_id]),
                ],
            ),
        )
    assert reordered.approval_stands is False
    assert reordered.approval_invalidation is not None
    assert "order" in reordered.approval_invalidation.changes


def test_membership_change_invalidates(engine: Engine, tmp_path: Path) -> None:
    _, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))
        trimmed = update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[RenditionUnitInput(body=bodies[0], claim_ids=[claim_id])],
            ),
        )
    assert trimmed.approval_stands is False
    assert trimmed.approval_invalidation is not None
    assert "membership" in trimmed.approval_invalidation.changes


def test_reapproval_appends_second_record(engine: Engine, tmp_path: Path) -> None:
    _, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        first = approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))
        first_id = first.current_approval_id
        update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[
                    RenditionUnitInput(body="Revised first post.", claim_ids=[claim_id]),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_id]),
                ],
            ),
        )
        second = approve_rendition(conn, ApproveRenditionInput(rendition_id=rid, actor="operator"))
        # History rows are immutable
        rows = conn.execute(
            select(rendition_approvals.c.id, rendition_approvals.c.sequence)
            .where(rendition_approvals.c.rendition_id == rid)
            .order_by(rendition_approvals.c.sequence.asc())
        ).all()

    assert first_id is not None
    assert second.current_approval_id != first_id
    assert second.approval_stands is True
    assert len(second.approvals) == 2
    assert second.approvals[0].approval_id == first_id
    assert [r.sequence for r in rows] == [1, 2]
    assert second.current_approval is not None
    assert second.current_approval.units[0].body == "Revised first post."


def test_approve_not_on_mcp(tmp_path: Path) -> None:
    from desk.transports.wiring import mcp_tool_names

    assert "approve_rendition" not in mcp_tool_names()
    assert "update_rendition" not in mcp_tool_names()


def test_composition_coverage_unchanged_by_approval(engine: Engine, tmp_path: Path) -> None:
    """composition stays object-backed on draft-with-cites; approval need not move it."""
    from desk.service import get_case_coverage
    from desk.service.models import GetCaseCoverageInput

    case_id, rid, _, _ = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        before = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))
        approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))
        after = get_case_coverage(conn, GetCaseCoverageInput(case_id=case_id))

    comp_b = next(s for s in before.stages if s.stage == "composition")
    comp_a = next(s for s in after.stages if s.stage == "composition")
    assert comp_b.reading == comp_a.reading
    assert comp_b.reading in {"worked", "complete"}


def test_edit_before_first_clearance(engine: Engine, tmp_path: Path) -> None:
    _, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    with connection_scope(engine) as conn:
        updated = update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[
                    RenditionUnitInput(body="Edited before clear.", claim_ids=[claim_id]),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_id]),
                ],
            ),
        )
        assert updated.status == "draft"
        assert updated.approval_stands is False
        cleared = approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))
    assert cleared.approval_stands is True
    assert cleared.current_approval is not None
    assert cleared.current_approval.units[0].body == "Edited before clear."


def test_not_found_refuses(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            approve_rendition(conn, ApproveRenditionInput(rendition_id=99999))
    assert ei.value.code == "RENDITION_NOT_FOUND"


def test_clearance_revalidates_after_stricter_qualification(engine: Engine, tmp_path: Path) -> None:
    """Re-confirm a cited claim with required qualification after composition.

    update_rendition never runs — the draft bodies are unchanged. approve_rendition
    must still refuse because clearance asserts current publishability (VISION §14),
    not freshness of an earlier write-path validation.
    """
    case_id, rid, claim_id, bodies = _seed_draft_thread(engine, tmp_path)
    strict_qual = "according to a single contemporaneous report only"
    # Unit bodies from seed do not contain this language.
    assert all(strict_qual not in b for b in bodies)

    with connection_scope(engine) as conn:
        # Ticket 11: re-confirmation without re-linking (claim already on the angle).
        confirm_claim_for_use(
            conn,
            claim_id=claim_id,
            case_id=case_id,
            dimensions=LinkClaimDimensions(
                source_basis="contemporaneous_report",
                corroboration="single_source",
                certainty="probable",
                posture="allegation",
                publication_risk="not_applicable",
                qualification=strict_qual,
            ),
        )

        with pytest.raises(DeskRefusal) as ei:
            approve_rendition(conn, ApproveRenditionInput(rendition_id=rid))

    assert ei.value.code == "QUALIFICATION_MISSING_FROM_UNIT"
    assert str(claim_id) in ei.value.what_happened
    assert strict_qual in ei.value.what_happened
    assert "edit" in ei.value.what_you_can_do.lower() or "unit" in ei.value.what_you_can_do.lower()

    # No clearance was written.
    with connection_scope(engine) as conn:
        detail = get_case(conn, GetCaseInput(case_id=case_id))
        ren = next(r for r in detail.renditions if r.rendition_id == rid)
    assert ren.status == "draft"
    assert ren.approvals == []
    assert ren.approval_stands is False
