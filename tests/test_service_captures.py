"""In-process seam tests for capture_url / read_capture (Vault)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from desk.db.schema import captures
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    capture_url,
    claim_next_run,
    create_case,
    create_run,
    read_capture,
)
from desk.service.models import (
    ApproveRunInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    ReadCaptureInput,
)
from desk.vault.store import VaultStore


def _claimed_run(engine: Engine, *, budget: int = 5) -> tuple[int, str]:
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Capture case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Q?",
                scope="s",
                coverage_dimension="official_foundation",
                capture_budget=budget,
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        claimed = claim_next_run(conn, ClaimNextRunInput())
        assert claimed.run is not None
        return claimed.run.run_id, claimed.run.claim_token


def _html_fetch(_url: str) -> tuple[bytes, str]:
    body = b"""<!DOCTYPE html><html><body>
    <h1>Title One</h1>
    <p>Paragraph alpha.</p>
    <p>Paragraph beta.</p>
    </body></html>"""
    return body, "text/html; charset=utf-8"


def test_capture_url_stores_hash_and_locator_map(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claimed_run(engine)
    with connection_scope(engine) as conn:
        result = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/a", claim_token=token),
            vault=vault,
            fetch=_html_fetch,
            locator_map_cap=50,
        )
    assert result.capture_id >= 1
    assert result.sha256
    assert result.byte_size > 0
    assert result.status == "unexamined"
    assert result.element_count >= 2
    assert result.elements_returned == result.element_count
    assert result.truncated is False
    assert any(e.text == "Paragraph alpha." for e in result.elements)
    assert result.projection_is_authoritative is False
    assert "READ-ONLY PROJECTION" in result.projection_markdown
    assert "not authoritative" in result.projection_markdown.lower()
    raw = vault.read_raw(str(Path("raw") / result.sha256[:2] / result.sha256))
    assert VaultStore.sha256_hex(raw) == result.sha256


def test_capture_url_budget_exhausted(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claimed_run(engine, budget=1)
    with connection_scope(engine) as conn:
        capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/1", claim_token=token),
            vault=vault,
            fetch=_html_fetch,
        )
        with pytest.raises(DeskRefusal) as exc_info:
            capture_url(
                conn,
                CaptureUrlInput(run_id=run_id, url="https://example.com/2", claim_token=token),
                vault=vault,
                fetch=_html_fetch,
            )
    assert exc_info.value.code == "BUDGET_EXHAUSTED"


def test_capture_url_refuses_unclaimed_run(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="C"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="Q?",
                scope="s",
                coverage_dimension="official_foundation",
            ),
        )
        with pytest.raises(DeskRefusal) as exc_info:
            capture_url(
                conn,
                CaptureUrlInput(
                    run_id=run.run_id,
                    url="https://example.com/x",
                    claim_token="not-a-real-token",
                ),
                vault=vault,
                fetch=_html_fetch,
            )
    assert exc_info.value.code in {"RUN_NOT_CLAIMED", "RUN_CLAIM_STALE"}


def test_read_capture_paginates(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claimed_run(engine)

    def many_paragraphs(_url: str) -> tuple[bytes, str]:
        parts = [f"<p>Block {i}.</p>" for i in range(10)]
        html = "<html><body>" + "".join(parts) + "</body></html>"
        return html.encode(), "text/html"

    with connection_scope(engine) as conn:
        first = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/long", claim_token=token),
            vault=vault,
            fetch=many_paragraphs,
            locator_map_cap=3,
        )
        assert first.truncated is True
        assert first.elements_returned == 3
        assert first.element_count == 10

        page = read_capture(
            conn,
            ReadCaptureInput(
                capture_id=first.capture_id,
                claim_token=token,
                offset=3,
                limit=4,
            ),
        )
        assert page.elements_returned == 4
        assert page.elements[0].ordinal == 3
        assert page.truncated is True
        assert page.projection_is_authoritative is False


def test_locator_map_cap_truncation(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claimed_run(engine)

    def big(_url: str) -> tuple[bytes, str]:
        parts = [f"<p>P{i}</p>" for i in range(20)]
        return ("<html><body>" + "".join(parts) + "</body></html>").encode(), "text/html"

    with connection_scope(engine) as conn:
        result = capture_url(
            conn,
            CaptureUrlInput(run_id=run_id, url="https://example.com/big", claim_token=token),
            vault=vault,
            fetch=big,
            locator_map_cap=5,
        )
    assert result.element_count == 20
    assert result.elements_returned == 5
    assert result.truncated is True


def test_unsupported_content_type_refused_without_capture(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    run_id, token = _claimed_run(engine, budget=2)

    def pdf_fetch(_url: str) -> tuple[bytes, str]:
        return b"%PDF-1.4 binary junk", "application/pdf"

    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            capture_url(
                conn,
                CaptureUrlInput(
                    run_id=run_id,
                    url="https://example.com/doc.pdf",
                    claim_token=token,
                ),
                vault=vault,
                fetch=pdf_fetch,
            )
        assert exc_info.value.code == "CAPTURE_UNSUPPORTED_TYPE"
        assert "application/pdf" in exc_info.value.what_happened
        used = conn.execute(
            select(func.count()).select_from(captures).where(captures.c.run_id == run_id)
        ).scalar_one()
        assert int(used) == 0
