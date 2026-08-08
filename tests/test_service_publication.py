"""Seam tests for record_publication / reject_rendition (ticket 14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

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
    record_publication,
    reject_rendition,
    update_publication_times,
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
    PublicationUnitInput,
    RecordPublicationInput,
    RejectRenditionInput,
    RenditionUnitInput,
    UpdatePublicationTimesInput,
    UpdateRenditionInput,
)
from desk.transports.wiring import mcp_tool_names
from desk.vault.store import VaultStore

_HTML = b"""<!DOCTYPE html><html><body>
<p>The agency published finding Alpha on 12 March.</p>
<p>A second independent note.</p>
</body></html>"""


def _html(_url: str) -> tuple[bytes, str]:
    return _HTML, "text/html"


def _dims(**kw: str) -> EvidenceDimensions:
    base = dict(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )
    base.update(kw)
    return EvidenceDimensions(**base)  # type: ignore[arg-type]


def _link(**kw: str) -> LinkClaimDimensions:
    base = dict(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
        qualification="",
    )
    base.update(kw)
    return LinkClaimDimensions(**base)  # type: ignore[arg-type]


def _seed_cleared(
    engine: Engine, tmp_path: Path, *, two_claims: bool = False
) -> tuple[int, int, int, int, list[str]]:
    """Return case_id, rendition_id, claim_a, claim_b_or_0, bodies."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Pub case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Q?",
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
                url="https://example.com/a",
                claim_token=token,
            ),
            vault=vault,
            fetch=_html,
        )
        claim_a = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=claimed.run.run_id,
                claim_token=token,
                proposition="Alpha published.",
                dimensions=_dims(),
                capture_id=cap.capture_id,
                locator=cap.elements[0].locator,
                quoted_text=cap.elements[0].text,
            ),
        )
        claim_b_id = 0
        claim_ids_for_angle = [claim_a.claim_id]
        dims_map = {claim_a.claim_id: _link()}
        if two_claims:
            claim_b = propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=claimed.run.run_id,
                    claim_token=token,
                    proposition="Second note exists.",
                    dimensions=_dims(),
                    capture_id=cap.capture_id,
                    locator=cap.elements[1].locator,
                    quoted_text=cap.elements[1].text,
                ),
            )
            claim_b_id = claim_b.claim_id
            claim_ids_for_angle.append(claim_b.claim_id)
            dims_map[claim_b.claim_id] = _link()

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
                title="Pub angle",
                claim_ids=claim_ids_for_angle,
                dimensions_by_claim_id=dims_map,
            ),
        )
        choose_angle(conn, ChooseAngleInput(angle_id=angle.angle_id))
        comp = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Compose",
                scope="c",
                coverage_dimension="composition",
                capture_budget=1,
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=comp.run_id))
        c2 = claim_next_run(conn, ClaimNextRunInput())
        assert c2.run is not None
        bodies = ["Thread unit zero.", "Thread unit one."]
        ren = propose_rendition(
            conn,
            ProposeRenditionInput(
                run_id=c2.run.run_id,
                claim_token=c2.run.claim_token,
                angle_id=angle.angle_id,
                platform="x",
                format="thread",
                units=[
                    RenditionUnitInput(body=bodies[0], claim_ids=[claim_a.claim_id]),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_a.claim_id]),
                ],
            ),
        )
        approve_rendition(conn, ApproveRenditionInput(rendition_id=ren.rendition_id))
        return case.case_id, ren.rendition_id, claim_a.claim_id, claim_b_id, bodies


def _pub_units(bodies: list[str]) -> list[PublicationUnitInput]:
    return [
        PublicationUnitInput(
            ordinal=i,
            platform="x",
            external_post_id=f"id-{i}",
            canonical_url=f"https://x.com/desk/status/{i}",
            published_at=f"2099-01-01T12:0{i}:00+00:00",
            verification_state="unverified",
        )
        for i in range(len(bodies))
    ]


def test_record_publication_binds_approval_id(engine: Engine, tmp_path: Path) -> None:
    case_id, rid, _, _, bodies = _seed_cleared(engine, tmp_path)
    with connection_scope(engine) as conn:
        before = get_case(conn, GetCaseInput(case_id=case_id))
        ren = next(r for r in before.renditions if r.rendition_id == rid)
        assert ren.approval_stands is True
        approval_id = ren.current_approval_id
        assert approval_id is not None

        published = record_publication(
            conn,
            RecordPublicationInput(rendition_id=rid, units=_pub_units(bodies), actor="chaz"),
        )

    assert published.status == "published"
    assert published.publication is not None
    assert published.publication.approval_id == approval_id
    assert published.publication.actor == "chaz"
    assert len(published.publication.units) == 2
    assert published.publication.units[0].external_post_id == "id-0"


def test_publication_refused_when_clearance_invalidated(engine: Engine, tmp_path: Path) -> None:
    _, rid, claim_id, _, bodies = _seed_cleared(engine, tmp_path)
    with connection_scope(engine) as conn:
        update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[
                    RenditionUnitInput(body=bodies[0] + " changed", claim_ids=[claim_id]),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_id]),
                ],
            ),
        )
        from desk.service.renditions import _load_rendition

        mid = _load_rendition(conn, rid)
        assert mid is not None
        assert mid.approval_stands is False
        assert mid.status == "cleared"  # status alone would pass a careless gate

        with pytest.raises(DeskRefusal) as ei:
            record_publication(
                conn,
                RecordPublicationInput(rendition_id=rid, units=_pub_units(bodies)),
            )
    assert ei.value.code == "PUBLICATION_CLEARANCE_NOT_STANDING"


def test_clear_reconfirm_stricter_qual_publication_refuses(engine: Engine, tmp_path: Path) -> None:
    """Cross-ticket S-01 hop: standing still true; qualification no longer holds."""
    case_id, rid, claim_id, _, bodies = _seed_cleared(engine, tmp_path)
    strict = "according to a single contemporaneous report only"
    assert all(strict not in b for b in bodies)

    with connection_scope(engine) as conn:
        confirm_claim_for_use(
            conn,
            claim_id=claim_id,
            case_id=case_id,
            dimensions=_link(
                posture="allegation",
                qualification=strict,
            ),
        )
        from desk.service.renditions import _load_rendition

        ren = _load_rendition(conn, rid)
        assert ren is not None
        assert ren.approval_stands is True  # bodies unchanged

        with pytest.raises(DeskRefusal) as ei:
            record_publication(
                conn,
                RecordPublicationInput(rendition_id=rid, units=_pub_units(bodies)),
            )
    assert ei.value.code == "QUALIFICATION_MISSING_FROM_UNIT"
    assert str(claim_id) in ei.value.what_happened
    assert strict in ei.value.what_happened


def test_f62_citation_drift_allowed_when_still_eligible(engine: Engine, tmp_path: Path) -> None:
    """Change claim_ids only — standing holds; publication proceeds (F-62 lock)."""
    case_id, rid, claim_a, claim_b, bodies = _seed_cleared(engine, tmp_path, two_claims=True)
    assert claim_b != 0

    with connection_scope(engine) as conn:
        # Citation drift without body change — no re-clearance required.
        updated = update_rendition(
            conn,
            UpdateRenditionInput(
                rendition_id=rid,
                units=[
                    RenditionUnitInput(body=bodies[0], claim_ids=[claim_b]),
                    RenditionUnitInput(body=bodies[1], claim_ids=[claim_b]),
                ],
            ),
        )
        assert updated.approval_stands is True
        assert updated.units[0].claim_ids == [claim_b]

        published = record_publication(
            conn,
            RecordPublicationInput(rendition_id=rid, units=_pub_units(bodies)),
        )
    assert published.status == "published"
    assert published.publication is not None
    assert published.units[0].claim_ids == [claim_b]


def test_reject_without_claim_revalidation(engine: Engine, tmp_path: Path) -> None:
    case_id, rid, claim_id, _, bodies = _seed_cleared(engine, tmp_path)
    strict = "must appear for allegation"
    with connection_scope(engine) as conn:
        confirm_claim_for_use(
            conn,
            claim_id=claim_id,
            case_id=case_id,
            dimensions=_link(posture="allegation", qualification=strict),
        )
        # Publication would refuse — rejection must still succeed.
        rejected = reject_rendition(conn, RejectRenditionInput(rendition_id=rid))
    assert rejected.status == "rejected"


def test_update_publication_times_does_not_alter_cleared_text(
    engine: Engine, tmp_path: Path
) -> None:
    _, rid, _, _, bodies = _seed_cleared(engine, tmp_path)
    with connection_scope(engine) as conn:
        record_publication(
            conn,
            RecordPublicationInput(rendition_id=rid, units=_pub_units(bodies)),
        )
        updated = update_publication_times(
            conn,
            UpdatePublicationTimesInput(
                rendition_id=rid,
                published_at_by_ordinal={
                    0: "2099-02-01T00:00:00+00:00",
                    1: "2099-02-01T00:01:00+00:00",
                },
            ),
        )
    assert updated.publication is not None
    assert updated.publication.units[0].published_at == "2099-02-01T00:00:00+00:00"
    assert [u.body for u in updated.units] == bodies
    assert updated.current_approval is not None
    assert [u.body for u in updated.current_approval.units] == bodies


def test_publication_ops_not_on_mcp() -> None:
    names = mcp_tool_names()
    assert "record_publication" not in names
    assert "reject_rendition" not in names
    assert "update_publication_times" not in names


def test_published_at_before_clearance_refused(engine: Engine, tmp_path: Path) -> None:
    """Cannot record a post as earlier than the authorizing clearance."""
    _, rid, _, _, bodies = _seed_cleared(engine, tmp_path)
    with connection_scope(engine) as conn:
        from desk.service.renditions import _load_rendition

        ren = _load_rendition(conn, rid)
        assert ren is not None and ren.current_approval is not None
        approved_at = ren.current_approval.approved_at
        # Far in the past relative to any clearance written in this test.
        early = "2020-01-01T00:00:00+00:00"
        units = _pub_units(bodies)
        units[0] = PublicationUnitInput(
            ordinal=0,
            platform="x",
            external_post_id="id-0",
            canonical_url="https://x.com/desk/status/0",
            published_at=early,
            verification_state="unverified",
        )
        with pytest.raises(DeskRefusal) as ei:
            record_publication(
                conn,
                RecordPublicationInput(rendition_id=rid, units=units),
            )
    assert ei.value.code == "PUBLICATION_BEFORE_CLEARANCE"
    assert "2020-01-01" in ei.value.what_happened
    assert approved_at in ei.value.what_happened


def test_update_publication_times_before_clearance_refused(engine: Engine, tmp_path: Path) -> None:
    _, rid, _, _, bodies = _seed_cleared(engine, tmp_path)
    with connection_scope(engine) as conn:
        record_publication(
            conn,
            RecordPublicationInput(rendition_id=rid, units=_pub_units(bodies)),
        )
        with pytest.raises(DeskRefusal) as ei:
            update_publication_times(
                conn,
                UpdatePublicationTimesInput(
                    rendition_id=rid,
                    published_at_by_ordinal={
                        0: "2019-06-01T00:00:00+00:00",
                        1: "2026-08-08T00:01:00+00:00",
                    },
                ),
            )
    assert ei.value.code == "PUBLICATION_BEFORE_CLEARANCE"
