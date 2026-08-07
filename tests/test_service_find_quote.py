"""find_quote — exact substring → e/n/r/start-end (ticket 12a / F-55)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from desk.db.schema import runs
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    capture_url,
    claim_next_run,
    create_case,
    create_run,
    find_quote,
    propose_claim,
)
from desk.service.models import (
    ApproveRunInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    EvidenceDimensions,
    FindQuoteInput,
    ProposeClaimInput,
)
from desk.vault.store import VaultStore


def _claimed_with_capture(
    engine: Engine,
    tmp_path: Path,
    *,
    html: bytes,
) -> tuple[int, int, str, str]:
    """Return run_id, capture_id, claim_token, first_element_text."""
    vault = VaultStore(tmp_path / "vault")

    def fetch(_url: str) -> tuple[bytes, str]:
        return html, "text/html"

    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Find quote"))
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
            CaptureUrlInput(
                run_id=run.run_id,
                url="https://example.com/doc",
                claim_token=token,
            ),
            vault=vault,
            fetch=fetch,
        )
        assert cap.elements
        return run.run_id, cap.capture_id, token, cap.elements[0].text


def test_unique_match_returns_region_locator(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>Exact quoteable sentence.</p></body></html>"
    run_id, capture_id, token, full = _claimed_with_capture(engine, tmp_path, html=html)
    needle = "quoteable"
    assert needle in full

    with connection_scope(engine) as conn:
        result = find_quote(
            conn,
            FindQuoteInput(
                capture_id=capture_id,
                claim_token=token,
                quoted_text=needle,
            ),
        )

    assert result.found is True
    assert result.reason == "unique"
    assert result.match_count == 1
    assert result.locator is not None
    assert result.locator.startswith("e/")
    assert "/r/" in result.locator
    start = result.matches[0].start
    end = result.matches[0].end
    assert full[start:end] == needle

    # propose_claim accepts the locator independently (quotation seam unchanged).
    dims = EvidenceDimensions(
        source_basis="contemporaneous_report",
        corroboration="single_source",
        certainty="probable",
        posture="factual_assertion",
        publication_risk="not_applicable",
    )
    with connection_scope(engine) as conn:
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=token,
                proposition="The page contains the word.",
                dimensions=dims,
                capture_id=capture_id,
                locator=result.locator,
                quoted_text=needle,
            ),
        )
    assert claim.quote_bindings[0].locator == result.locator


def test_not_found_is_structured_miss(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>Hello world.</p></body></html>"
    _, capture_id, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        result = find_quote(
            conn,
            FindQuoteInput(
                capture_id=capture_id,
                claim_token=token,
                quoted_text="this text is not on the page at all",
            ),
        )

    assert result.found is False
    assert result.reason == "not_found"
    assert result.match_count == 0
    assert result.locator is None
    assert result.matches == []


def test_multiple_elements_is_distinct_from_not_found(engine: Engine, tmp_path: Path) -> None:
    html = b"""<!DOCTYPE html><html><body>
    <p>Shared phrase alpha.</p>
    <p>Later Shared phrase again.</p>
    </body></html>"""
    _, capture_id, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        result = find_quote(
            conn,
            FindQuoteInput(
                capture_id=capture_id,
                claim_token=token,
                quoted_text="Shared phrase",
            ),
        )

    assert result.found is False
    assert result.reason == "multiple_elements"
    assert result.match_count >= 2
    assert result.locator is None
    element_ids = {m.element_locator for m in result.matches}
    assert len(element_ids) > 1


def test_multiple_in_same_element(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>foo bar foo</p></body></html>"
    _, capture_id, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        result = find_quote(
            conn,
            FindQuoteInput(
                capture_id=capture_id,
                claim_token=token,
                quoted_text="foo",
            ),
        )

    assert result.found is False
    assert result.reason == "multiple_in_element"
    assert result.match_count == 2
    assert len({m.element_locator for m in result.matches}) == 1


def test_exact_only_no_fuzzy_or_casefold(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>Exact Case Matters.</p></body></html>"
    _, capture_id, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        result = find_quote(
            conn,
            FindQuoteInput(
                capture_id=capture_id,
                claim_token=token,
                quoted_text="exact case matters.",
            ),
        )

    assert result.found is False
    assert result.reason == "not_found"


def test_empty_quoted_text_refuses(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>x</p></body></html>"
    _, capture_id, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            find_quote(
                conn,
                FindQuoteInput(
                    capture_id=capture_id,
                    claim_token=token,
                    quoted_text="",
                ),
            )
    assert ei.value.code == "FIND_QUOTE_EMPTY"


def test_does_not_refresh_lease(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>Stable lease text.</p></body></html>"
    run_id, capture_id, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        before = conn.execute(
            select(runs.c.lease_expires_at).where(runs.c.id == run_id)
        ).scalar_one()

    with connection_scope(engine) as conn:
        find_quote(
            conn,
            FindQuoteInput(
                capture_id=capture_id,
                claim_token=token,
                quoted_text="Stable",
            ),
        )

    with connection_scope(engine) as conn:
        after = conn.execute(
            select(runs.c.lease_expires_at).where(runs.c.id == run_id)
        ).scalar_one()

    assert after == before


def test_capture_not_found(engine: Engine, tmp_path: Path) -> None:
    html = b"<html><body><p>x</p></body></html>"
    _, _, token, _ = _claimed_with_capture(engine, tmp_path, html=html)

    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as ei:
            find_quote(
                conn,
                FindQuoteInput(
                    capture_id=99999,
                    claim_token=token,
                    quoted_text="x",
                ),
            )
    assert ei.value.code == "CAPTURE_NOT_FOUND"
