"""Seam tests for run lease expiry, claim tokens, and partial-work preservation."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text

from desk.db.schema import runs
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    capture_url,
    claim_next_run,
    create_case,
    create_run,
    propose_claim,
    read_capture,
)
from desk.service.captures import list_capture_summaries_for_case
from desk.service.claims import list_claims_for_case
from desk.service.lease import format_utc, reclaim_expired_leases, utc_now
from desk.service.models import (
    ApproveRunInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    EvidenceDimensions,
    ProposeClaimInput,
    ReadCaptureInput,
)
from desk.vault.store import VaultStore

_DIMS = EvidenceDimensions(
    source_basis="contemporaneous_report",
    corroboration="single_source",
    certainty="probable",
    posture="factual_assertion",
    publication_risk="not_applicable",
)


def _html_fetch(_url: str) -> tuple[bytes, str]:
    return b"<html><body><p>Kept material.</p></body></html>", "text/html"


def _claim_run(engine: Engine) -> tuple[int, str]:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Lease"))
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
        assert packet.run.is_resume is False
        assert packet.run.lease_expires_at is not None
        assert packet.run.claim_token
        return packet.run.run_id, packet.run.claim_token


def test_claim_starts_lease_and_token(engine: Engine) -> None:
    run_id, token = _claim_run(engine)
    with connection_scope(engine) as conn:
        row = conn.execute(
            select(runs.c.status, runs.c.lease_expires_at, runs.c.claim_token).where(
                runs.c.id == run_id
            )
        ).one()
    assert row.status == "claimed"
    assert row.lease_expires_at is not None
    assert row.claim_token == token


def test_expired_lease_refuses_capture_and_does_not_extend(engine: Engine, tmp_path: Path) -> None:
    """F-25a: expired lease fails closed; refusal does not refresh lease."""
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claim_run(engine)
    past = format_utc(utc_now() - timedelta(hours=1))
    with connection_scope(engine) as conn:
        conn.execute(
            text("UPDATE runs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past, "id": run_id},
        )
        with pytest.raises(DeskRefusal) as ei:
            capture_url(
                conn,
                CaptureUrlInput(
                    run_id=run_id,
                    url="https://example.com/x",
                    claim_token=token,
                ),
                vault=vault,
                fetch=_html_fetch,
            )
        assert ei.value.code == "RUN_LEASE_EXPIRED"
        row = conn.execute(
            select(runs.c.lease_expires_at, runs.c.status).where(runs.c.id == run_id)
        ).one()
        # Lease not extended by the refused call.
        assert str(row.lease_expires_at) == past
        assert row.status == "claimed"


def test_expired_lease_refuses_propose_and_read_capture(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Exp"))
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
        run_id = packet.run.run_id
        token = packet.run.claim_token
        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/a", claim_token=token),
            vault=vault,
            fetch=_html_fetch,
        )
        past = format_utc(utc_now() - timedelta(hours=1))
        conn.execute(
            text("UPDATE runs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past, "id": run_id},
        )
        with pytest.raises(DeskRefusal) as ei_r:
            read_capture(
                conn,
                ReadCaptureInput(capture_id=cap.capture_id, claim_token=token),
            )
        assert ei_r.value.code == "RUN_LEASE_EXPIRED"
        el = cap.elements[0]
        with pytest.raises(DeskRefusal) as ei_p:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=run_id,
                    claim_token=token,
                    proposition="x",
                    dimensions=_DIMS,
                    capture_id=cap.capture_id,
                    locator=el.locator,
                    quoted_text=el.text,
                ),
            )
        assert ei_p.value.code == "RUN_LEASE_EXPIRED"


def test_expired_lease_reclaimable_with_resume(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Preserve"))
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
        first = claim_next_run(conn, ClaimNextRunInput())
        assert first.run is not None
        run_id = first.run.run_id
        old_token = first.run.claim_token

        cap = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/kept", claim_token=old_token),
            vault=vault,
            fetch=_html_fetch,
        )
        el = cap.elements[0]
        claim = propose_claim(
            conn,
            ProposeClaimInput(
                run_id=run_id,
                claim_token=old_token,
                proposition="Material was captured.",
                dimensions=_DIMS,
                capture_id=cap.capture_id,
                locator=el.locator,
                quoted_text=el.text,
            ),
        )

        past = format_utc(utc_now() - timedelta(hours=1))
        conn.execute(
            text("UPDATE runs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past, "id": run_id},
        )

        second = claim_next_run(conn, ClaimNextRunInput())
        assert second.run is not None
        assert second.run.run_id == run_id
        assert second.run.is_resume is True
        assert second.run.captures_used == 1
        assert second.run.claims_made == 1
        assert second.run.claim_token != old_token
        assert second.run.lease_expires_at is not None

        claims = list_claims_for_case(conn, case.case_id)
        assert any(c.claim_id == claim.claim_id for c in claims)
        caps = list_capture_summaries_for_case(conn, case.case_id)
        assert any(s.capture_id == cap.capture_id for s in caps)


def test_valid_lease_still_refreshes(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claim_run(engine)
    with connection_scope(engine) as conn:
        before = conn.execute(
            select(runs.c.lease_expires_at).where(runs.c.id == run_id)
        ).scalar_one()
        capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/r", claim_token=token),
            vault=vault,
            fetch=_html_fetch,
        )
        after = conn.execute(
            select(runs.c.lease_expires_at).where(runs.c.id == run_id)
        ).scalar_one()
    assert after is not None
    assert before is not None
    # Refresh should move deadline forward (or at least keep it valid and re-written).
    assert str(after) >= str(before)


def test_stale_token_refused_while_run_validly_claimed(engine: Engine, tmp_path: Path) -> None:
    """F-25b: executor A cannot use B's lease after reclaim."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Stale"))
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
        first = claim_next_run(conn, ClaimNextRunInput())
        assert first.run is not None
        run_id = first.run.run_id
        token_a = first.run.claim_token

        past = format_utc(utc_now() - timedelta(hours=1))
        conn.execute(
            text("UPDATE runs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past, "id": run_id},
        )
        second = claim_next_run(conn, ClaimNextRunInput())
        assert second.run is not None
        token_b = second.run.claim_token
        assert token_b != token_a

        with pytest.raises(DeskRefusal) as ei:
            capture_url(
                conn,
                CaptureUrlInput(
                    run_id=run_id,
                    url="https://example.com/x",
                    claim_token=token_a,
                ),
                vault=vault,
                fetch=_html_fetch,
            )
        assert ei.value.code == "RUN_CLAIM_STALE"
        # B still works
        capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/b", claim_token=token_b),
            vault=vault,
            fetch=_html_fetch,
        )


def test_reclaim_invalidates_previous_token(engine: Engine) -> None:
    run_id, token_a = _claim_run(engine)
    past = format_utc(utc_now() - timedelta(minutes=1))
    with connection_scope(engine) as conn:
        conn.execute(
            text("UPDATE runs SET lease_expires_at = :past WHERE id = :id"),
            {"past": past, "id": run_id},
        )
        n = reclaim_expired_leases(conn)
        assert n == 1
        row = conn.execute(
            select(runs.c.status, runs.c.claim_token, runs.c.lease_expires_at).where(
                runs.c.id == run_id
            )
        ).one()
        assert row.status == "approved"
        assert row.claim_token is None
        assert row.lease_expires_at is None

        second = claim_next_run(conn, ClaimNextRunInput())
        assert second.run is not None
        assert second.run.claim_token != token_a


def test_fresh_claim_is_not_resume(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Fresh"))
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
    assert packet.run.is_resume is False
    assert packet.run.captures_used == 0
    assert packet.run.claims_made == 0
    assert packet.run.claim_token


def test_case_busy_while_lease_valid(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Busy"))
        a = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="One",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        b = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Two",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=a.run_id))
        claim_next_run(conn, ClaimNextRunInput())
        with pytest.raises(DeskRefusal) as ei:
            approve_run(conn, ApproveRunInput(run_id=b.run_id))
    assert ei.value.code == "RUN_CASE_BUSY"
