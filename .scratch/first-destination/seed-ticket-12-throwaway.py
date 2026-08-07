#!/usr/bin/env python3
"""Seed a throwaway case for ticket 12 — not Vela.

Real HTTP captures (example.com + iana.org), real claims, chosen angle, one
draft X-thread rendition the operator can read in the browser.

Run from repo root with the Desk DB at data/desk.db (default settings):

    uv run python .scratch/first-destination/seed-ticket-12-throwaway.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from desk.config import get_settings  # noqa: E402
from desk.db.engine import create_db_engine  # noqa: E402
from desk.db.session import connection_scope  # noqa: E402
from desk.service import (  # noqa: E402
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
    create_run,
    get_case,
    propose_claim,
    propose_rendition,
)
from desk.service.models import (  # noqa: E402
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
    CreateRunInput,
    EvidenceDimensions,
    GetCaseInput,
    LinkClaimDimensions,
    ProposeClaimInput,
    ProposeRenditionInput,
    RenditionUnitInput,
)
from desk.vault.store import VaultStore  # noqa: E402

# Real, stable, non-Vela pages.
URL_A = "https://example.com/"
URL_B = "https://www.iana.org/domains/reserved"


def main() -> None:
    settings = get_settings()
    # Ensure migrations.
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{settings.database_path.resolve()}")
    command.upgrade(cfg, "head")

    engine = create_db_engine(settings.database_path)
    vault = VaultStore(settings.vault_path)

    with connection_scope(engine) as conn:
        case = create_case(
            conn,
            CreateCaseInput(
                title="Throwaway: example.com domain reservation notes (ticket 12 seed)"
            ),
        )
        print(f"case_id={case.case_id}")

        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="What do these reserved-domain pages state on their face?",
                scope="official record of two stable public pages only",
                coverage_dimension="official_foundation",
                capture_budget=5,
                rubric_version="seed-12.0",
                rubric_text="Capture the page; propose only what the text states.",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        token = claimed.run.claim_token
        run_id = claimed.run.run_id

        cap_a = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url=URL_A, claim_token=token),
            vault=vault,
        )
        cap_b = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url=URL_B, claim_token=token),
            vault=vault,
        )
        print(f"capture_a={cap_a.capture_id} elements={len(cap_a.elements)}")
        print(f"capture_b={cap_b.capture_id} elements={len(cap_b.elements)}")
        for i, el in enumerate(cap_a.elements[:5]):
            print(f"  A e/{i}: {el.text[:100]!r}")
        for i, el in enumerate(cap_b.elements[:8]):
            print(f"  B e/{i}: {el.text[:100]!r}")

        # Pick first non-empty elements with usable text.
        el_a = next(e for e in cap_a.elements if e.text.strip())
        el_b = next(e for e in cap_b.elements if len(e.text.strip()) > 20)

        claim1 = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="example.com presents itself as an illustrative example domain.",
                dimensions=EvidenceDimensions(
                    source_basis="contemporaneous_record",
                    corroboration="single_source",
                    certainty="established",
                    posture="factual_assertion",
                    publication_risk="not_applicable",
                ),
                capture_id=cap_a.capture_id,
                locator=el_a.locator,
                quoted_text=el_a.text,
            ),
        )
        claim2 = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition=(
                    "IANA documents domains reserved for documentation and examples."
                ),
                dimensions=EvidenceDimensions(
                    source_basis="contemporaneous_record",
                    corroboration="single_source",
                    certainty="established",
                    posture="factual_assertion",
                    publication_risk="institution",
                ),
                capture_id=cap_b.capture_id,
                locator=el_b.locator,
                quoted_text=el_b.text,
            ),
        )
        close_run(
            conn,
            CloseRunInput(
                run_id=run_id,
                claim_token=token,
                examined_capture_ids=[],
            ),
        )
        attest_coverage(
            conn,
            AttestCoverageInput(case_id=case.case_id, stage="official_foundation"),
        )
        assert_official_foundation_complete(
            conn, AssertOfficialFoundationInput(case_id=case.case_id)
        )

        dims1 = LinkClaimDimensions(
            source_basis="contemporaneous_record",
            corroboration="single_source",
            certainty="established",
            posture="factual_assertion",
            publication_risk="not_applicable",
        )
        dims2 = LinkClaimDimensions(
            source_basis="contemporaneous_record",
            corroboration="single_source",
            certainty="established",
            posture="factual_assertion",
            publication_risk="institution",
        )
        angle = create_angle(
            conn,
            CreateAngleInput(
                case_id=case.case_id,
                title="Reserved names exist so examples do not collide with real sites",
                summary=(
                    "Two official pages together show the reservation is deliberate "
                    "infrastructure, not an accident of naming."
                ),
                claim_ids=[claim1.claim_id, claim2.claim_id],
                dimensions_by_claim_id={
                    claim1.claim_id: dims1,
                    claim2.claim_id: dims2,
                },
            ),
        )
        choose_angle(conn, ChooseAngleInput(angle_id=angle.angle_id))

        # Case-scoped shelf: whole-element entry (composition evidence).
        add_quotation_to_shelf(
            conn,
            AddQuotationShelfInput(
                case_id=case.case_id,
                claim_id=claim1.claim_id,
                capture_id=cap_a.capture_id,
                locator=el_a.locator,
                quoted_text=el_a.text,
                speaker="example.com page",
                attribution_frame="on-page presentation",
            ),
        )

        # Composition run + draft thread (flat, grounded).
        comp = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Compose an X thread for the chosen angle.",
                scope="x/thread from confirmed claims only",
                coverage_dimension="composition",
                capture_budget=1,
                rubric_version="composition-seed-12.0",
                rubric_text=(
                    "Write short units for X. Cite only angle-eligible confirmed "
                    "claims. Include required qualification when present."
                ),
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=comp.run_id))
        cclaimed = claim_next_run(conn, ClaimNextRunInput())
        assert cclaimed.run is not None

        # Flat draft — expected for pre-rubric ticket 16.
        body0 = (
            f"Two quiet pages still do real work.\n\n"
            f"example.com is not a random leftover URL — the page presents itself "
            f"as an example domain: “{el_a.text.strip()[:120]}”"
        )
        body1 = (
            f"IANA says the same thing from the registry side: domains are reserved "
            f"for documentation so examples do not collide with real sites. "
            f"“{el_b.text.strip()[:160]}”"
        )
        body2 = (
            "That is the whole angle: reserved names are infrastructure. "
            "The boring pages are the proof."
        )
        ren = propose_rendition(
            conn,
            ProposeRenditionInput(
                run_id=cclaimed.run.run_id,
                claim_token=cclaimed.run.claim_token,
                angle_id=angle.angle_id,
                platform="x",
                format="thread",
                units=[
                    RenditionUnitInput(body=body0, claim_ids=[claim1.claim_id]),
                    RenditionUnitInput(body=body1, claim_ids=[claim2.claim_id]),
                    RenditionUnitInput(
                        body=body2,
                        claim_ids=[claim1.claim_id, claim2.claim_id],
                    ),
                ],
            ),
        )
        detail = get_case(conn, GetCaseInput(case_id=case.case_id))
        print(f"angle_id={angle.angle_id} status=chosen")
        print(f"rendition_id={ren.rendition_id} units={len(ren.units)} status={ren.status}")
        print(f"composition reading={[s.reading for s in detail.coverage.stages if s.stage=='composition'][0]}")
        print(f"story_intelligence={[s.reading for s in detail.coverage.stages if s.stage=='story_intelligence'][0]}")
        print("--- thread ---")
        for u in ren.units:
            print(f"[{u.ordinal}] cites {u.claim_ids}")
            print(u.body)
            print()
        print(f"Open case #{case.case_id} in the browser to read the draft.")


if __name__ == "__main__":
    main()
