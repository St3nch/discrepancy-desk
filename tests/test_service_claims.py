"""Seam tests for propose_claim five-step fail-closed verification."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    capture_url,
    claim_next_run,
    create_case,
    create_run,
    propose_claim,
)
from desk.service.models import (
    ApproveRunInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    EvidenceDimensions,
    ProposeClaimInput,
    QuoteBindingInput,
)
from desk.vault.store import VaultStore

_DIMS = EvidenceDimensions(
    source_basis="contemporaneous_report",
    corroboration="single_source",
    certainty="probable",
    posture="factual_assertion",
    publication_risk="not_applicable",
)


def _setup_claimed_with_capture(engine: Engine, tmp_path: Path) -> tuple[int, int, str, str, str]:
    """Return run_id, capture_id, locator, element_text, claim_token."""
    vault = VaultStore(tmp_path / "vault")

    def fetch(_url: str) -> tuple[bytes, str]:
        html = b"<html><body><p>Exact quoteable sentence.</p></body></html>"
        return html, "text/html"

    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Claims"))
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
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        token = packet.run.claim_token
        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run.run_id, url="https://example.com/a", claim_token=token),
            vault=vault,
            fetch=fetch,
        )
        el = cap.elements[0]
        return run.run_id, cap.capture_id, el.locator, el.text, token


def test_propose_claim_happy_path(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    with connection_scope(engine) as conn:
        result = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="The sentence is on the page.",
                dimensions=_DIMS,
                capture_id=capture_id,
                locator=locator,
                quoted_text=text,
            ),
        )
    assert result.confirmation_status == "unconfirmed"
    assert result.proposition == "The sentence is on the page."
    assert result.rubric_version
    assert len(result.quote_bindings) == 1
    assert result.quote_bindings[0].quoted_text == text


def test_step1_capture_not_found(engine: Engine, tmp_path: Path) -> None:
    run_id, _, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=99999,
                    locator=locator,
                    quoted_text=text,
                ),
            )
    assert ei.value.code == "CAPTURE_NOT_FOUND"


def test_step1_capture_wrong_case(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")

    def fetch(_url: str) -> tuple[bytes, str]:
        return b"<html><body><p>Shared text.</p></body></html>", "text/html"

    with connection_scope(engine) as conn:
        case_a = create_case(conn, CreateCaseInput(title="A"))
        case_b = create_case(conn, CreateCaseInput(title="B"))
        run_a = create_run(
            conn,
            CreateRunInput(
                case_id=case_a.case_id,
                question="Q",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        run_b = create_run(
            conn,
            CreateRunInput(
                case_id=case_b.case_id,
                question="Q",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run_a.run_id))
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        token_a = packet.run.claim_token
        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run_a.run_id, claim_token=token_a, url="https://example.com/a"),
            vault=vault,
            fetch=fetch,
        )
        # Finish run A claim path for B: approve B after A is claimed — case busy for A
        # Approve B on different case works
        approve_run(conn, ApproveRunInput(run_id=run_b.run_id))
        packet_b = claim_next_run(conn, ClaimNextRunInput())
        assert packet_b.run is not None
        token = packet_b.run.claim_token
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_b.run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=cap.capture_id,
                    locator=cap.elements[0].locator,
                    quoted_text=cap.elements[0].text,
                ),
            )
    assert ei.value.code == "CAPTURE_WRONG_CASE"


def test_step2_locator_unresolved(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, _, text, token = _setup_claimed_with_capture(engine, tmp_path)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=capture_id,
                    locator="e/999",
                    quoted_text=text,
                ),
            )
    assert ei.value.code == "LOCATOR_UNRESOLVED"


def test_step3_quote_mismatch(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, locator, _, token = _setup_claimed_with_capture(engine, tmp_path)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=capture_id,
                    locator=locator,
                    quoted_text="Not the element text at all.",
                ),
            )
    assert ei.value.code == "QUOTE_MISMATCH"


def test_step3_no_fuzzy_match(engine: Engine, tmp_path: Path) -> None:
    """Whitespace / case drift must fail — not a normalised match."""
    run_id, capture_id, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=capture_id,
                    locator=locator,
                    quoted_text=text + " ",
                ),
            )
    assert ei.value.code == "QUOTE_MISMATCH"


def test_step4_dimension_invalid(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    bad = EvidenceDimensions(
        source_basis="not_a_real_basis",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=bad,
                    capture_id=capture_id,
                    locator=locator,
                    quoted_text=text,
                ),
            )
    assert ei.value.code == "DIMENSION_INVALID"


def test_step5_qualification_required(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    dims = EvidenceDimensions(
        source_basis="later_retrospective_claim",
        corroboration="single_source",
        certainty="contested",
        posture="allegation",
        publication_risk="living_private",
    )
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="Someone alleged X.",
                    dimensions=dims,
                    qualification="   ",
                    capture_id=capture_id,
                    locator=locator,
                    quoted_text=text,
                ),
            )
    assert ei.value.code == "QUALIFICATION_REQUIRED"


def test_multiple_quote_bindings(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")

    def fetch(_url: str) -> tuple[bytes, str]:
        return (
            b"<html><body><p>First passage.</p><p>Second passage.</p></body></html>",
            "text/html",
        )

    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Multi"))
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
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        token = packet.run.claim_token
        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run.run_id, claim_token=token, url="https://example.com/m"),
            vault=vault,
            fetch=fetch,
        )
        e0, e1 = cap.elements[0], cap.elements[1]
        result = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run.run_id,
                claim_token=token,
                proposition="Both passages support this.",
                dimensions=_DIMS,
                quote_bindings=[
                    QuoteBindingInput(
                        capture_id=cap.capture_id,
                        locator=e0.locator,
                        quoted_text=e0.text,
                    ),
                    QuoteBindingInput(
                        capture_id=cap.capture_id,
                        locator=e1.locator,
                        quoted_text=e1.text,
                    ),
                ],
            ),
        )
    assert len(result.quote_bindings) == 2


def test_region_locator_quotes_substring(engine: Engine, tmp_path: Path) -> None:
    """F-22: e/n/r/start-end quotes a character range, not the whole paragraph."""
    vault = VaultStore(tmp_path / "vault")

    def fetch(_url: str) -> tuple[bytes, str]:
        # One block element; quote only a slice.
        return (
            b"<html><body><p>Alpha sentence. Beta sentence.</p></body></html>",
            "text/html",
        )

    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Region"))
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
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        token = packet.run.claim_token
        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run.run_id, claim_token=token, url="https://example.com/r"),
            vault=vault,
            fetch=fetch,
        )
        full = cap.elements[0].text
        assert "Alpha sentence." in full
        start = full.index("Alpha sentence.")
        end = start + len("Alpha sentence.")
        region_locator = f"e/{cap.elements[0].ordinal}/r/{start}-{end}"
        result = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run.run_id,
                claim_token=token,
                proposition="Only the alpha sentence.",
                dimensions=_DIMS,
                capture_id=cap.capture_id,
                locator=region_locator,
                quoted_text="Alpha sentence.",
            ),
        )
    assert result.quote_bindings[0].locator == region_locator

    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run.run_id,
                    claim_token=token,
                    proposition="Wrong surface.",
                    dimensions=_DIMS,
                    capture_id=cap.capture_id,
                    locator=region_locator,
                    quoted_text=full,  # whole element ≠ region surface
                ),
            )
    assert ei.value.code == "QUOTE_MISMATCH"


def test_region_locator_out_of_range(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    ordinal = int(locator.split("/")[1])
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=capture_id,
                    locator=f"e/{ordinal}/r/0-{len(text) + 50}",
                    quoted_text=text,
                ),
            )
    assert ei.value.code == "LOCATOR_UNRESOLVED"


def test_desk_inference_cites_claims(engine: Engine, tmp_path: Path) -> None:
    run_id, capture_id, locator, text, token = _setup_claimed_with_capture(engine, tmp_path)
    with connection_scope(engine) as conn:
        base = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Base claim.",
                dimensions=_DIMS,
                capture_id=capture_id,
                locator=locator,
                quoted_text=text,
            ),
        )
        inference = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="Therefore we infer Y.",
                dimensions=EvidenceDimensions(
                    source_basis="desk_inference",
                    corroboration="unassessed",
                    certainty="speculative",
                    posture="interpretation",
                    publication_risk="not_applicable",
                ),
                cited_claim_ids=[base.claim_id],
            ),
        )
    assert inference.source_basis == "desk_inference"
    assert inference.cited_claim_ids == [base.claim_id]
    assert inference.quote_bindings == []
