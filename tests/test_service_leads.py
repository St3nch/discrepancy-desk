"""In-process seam tests for lead inbox (ticket 09 / ADR 7 / D18)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from desk.db.schema import captures, claims, document_versions, elements
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    add_lead,
    approve_run,
    attach_lead,
    capture_url,
    claim_next_run,
    create_case,
    create_run,
    dispose_lead,
    list_leads,
    promote_lead,
    propose_claim,
    summarise_lead,
)
from desk.service.evidence import LIST_LEADS_ALL
from desk.service.models import (
    AddLeadInput,
    ApproveRunInput,
    AttachLeadInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
    DisposeLeadInput,
    EvidenceDimensions,
    ListLeadsInput,
    PromoteLeadInput,
    ProposeClaimInput,
    SummariseLeadInput,
)
from desk.vault.store import VaultStore

_HTML_BODY = b"""<!DOCTYPE html><html><body>
    <h1>Lead Title</h1>
    <p>Paragraph for both doors.</p>
    </body></html>"""


def _html_fetch(_url: str) -> tuple[bytes, str]:
    return _HTML_BODY, "text/html; charset=utf-8"


def _auth_walled_fetch(_url: str) -> tuple[bytes, str]:
    raise DeskRefusal(
        code="CAPTURE_AUTH_WALLED",
        what_happened="HTTP 403 fetching (test).",
        what_was_preserved="Existing captures unchanged.",
        what_was_not_changed="No capture was written.",
        what_you_can_do="Use a public URL or drop as identity-only lead.",
    )


def _element_rows(conn: object, capture_id: int) -> list[tuple[str, int, str, str]]:
    dv = conn.execute(  # type: ignore[attr-defined]
        select(document_versions.c.id)
        .where(document_versions.c.capture_id == capture_id)
        .order_by(document_versions.c.version_number.desc())
        .limit(1)
    ).one()
    rows = conn.execute(  # type: ignore[attr-defined]
        select(
            elements.c.locator,
            elements.c.ordinal,
            elements.c.element_type,
            elements.c.text,
        )
        .where(elements.c.document_version_id == int(dv.id))
        .order_by(elements.c.ordinal.asc())
    ).all()
    return [(str(r.locator), int(r.ordinal), str(r.element_type), str(r.text)) for r in rows]


def test_add_lead_captures_immediately(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/lead", note="from podcast"),
            vault=vault,
            fetch=_html_fetch,
        )
    assert lead.lead_id >= 1
    assert lead.material_status == "captured"
    assert lead.capture_id is not None
    assert lead.capture_status == "unexamined"
    assert lead.inbox_status == "open"
    assert lead.case_id is None
    assert lead.note == "from podcast"
    assert lead.summary is None
    assert lead.sha256
    assert lead.element_count is not None and lead.element_count >= 1
    assert lead.projection_is_authoritative is False
    raw = vault.read_raw(str(Path("raw") / lead.sha256[:2] / lead.sha256))
    assert VaultStore.sha256_hex(raw) == lead.sha256


def test_lead_and_run_produce_identical_capture_records(engine: Engine, tmp_path: Path) -> None:
    """Same URL through both doors → same store/hash/parse/element structure."""
    vault = VaultStore(tmp_path / "vault")
    url = "https://example.com/same-artifact"

    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url=url, note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        case = create_case(conn, CreateCaseInput(title="Compare doors"))
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
        run_cap = capture_url(
            conn,
            CaptureUrlInput(
                run_id=claimed.run.run_id,
                url=url,
                claim_token=claimed.run.claim_token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )

        assert lead.capture_id is not None
        assert lead.sha256 == run_cap.sha256
        assert lead.content_type == run_cap.content_type
        assert lead.byte_size == run_cap.byte_size
        assert lead.element_count == run_cap.element_count

        lead_row = conn.execute(
            select(
                captures.c.sha256,
                captures.c.content_type,
                captures.c.byte_size,
                captures.c.vault_relpath,
                captures.c.status,
                captures.c.run_id,
                captures.c.case_id,
            ).where(captures.c.id == lead.capture_id)
        ).one()
        run_row = conn.execute(
            select(
                captures.c.sha256,
                captures.c.content_type,
                captures.c.byte_size,
                captures.c.vault_relpath,
                captures.c.status,
                captures.c.run_id,
                captures.c.case_id,
            ).where(captures.c.id == run_cap.capture_id)
        ).one()
        # Content identity — ownership columns differ by design.
        assert lead_row.sha256 == run_row.sha256
        assert lead_row.content_type == run_row.content_type
        assert lead_row.byte_size == run_row.byte_size
        assert lead_row.vault_relpath == run_row.vault_relpath
        assert lead_row.status == run_row.status == "unexamined"
        assert lead_row.run_id is None and run_row.run_id is not None
        assert lead_row.case_id is None and run_row.case_id is not None
        assert _element_rows(conn, int(lead.capture_id)) == _element_rows(conn, run_cap.capture_id)


def test_lead_holds_no_claims(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/no-claims", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        assert conn.execute(select(claims.c.id)).all() == []
        assert lead.capture_id is not None
        case = create_case(conn, CreateCaseInput(title="Other"))
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
        with pytest.raises(DeskRefusal) as exc_info:
            propose_claim(
                conn,
                ProposeClaimInput(
                    run_id=claimed.run.run_id,
                    claim_token=claimed.run.claim_token,
                    proposition="Should fail",
                    dimensions=EvidenceDimensions(
                        source_basis="contemporaneous_report",
                        corroboration="unassessed",
                        certainty="unassessed",
                        posture="factual_assertion",
                        publication_risk="not_applicable",
                    ),
                    capture_id=lead.capture_id,
                    locator="e/0",
                    quoted_text="Lead Title",
                ),
            )
        assert exc_info.value.code == "CAPTURE_WRONG_CASE"


def test_unsupported_type_parks_url_without_vault(engine: Engine, tmp_path: Path) -> None:
    """Ticket 09a: fetched but unparseable → unsupported_type, capture_id NULL."""
    vault = VaultStore(tmp_path / "vault")

    def pdf_fetch(_url: str) -> tuple[bytes, str]:
        return b"%PDF-1.4 not really a parseable document", "application/pdf"

    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/episode.pdf", note="podcast notes pdf"),
            vault=vault,
            fetch=pdf_fetch,
        )
        assert lead.material_status == "unsupported_type"
        assert lead.capture_id is None
        assert lead.capture_status is None
        assert lead.sha256 is None
        assert lead.inbox_status == "open"
        assert conn.execute(select(captures.c.id)).all() == []
        # No content-addressed objects — retain never wrote (VaultStore mkdirs root).
        assert list(vault.root.rglob("raw/**/*")) == [] if vault.root.exists() else True


def test_identity_only_auth_walled(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/paywalled-article", note="paywalled"),
            vault=vault,
            fetch=_auth_walled_fetch,
        )
        assert lead.material_status == "identity_only"
        assert lead.capture_id is None
        assert lead.capture_status is None
        assert lead.sha256 is None
        assert lead.inbox_status == "open"
        assert conn.execute(select(captures.c.id)).all() == []


def test_summary_optional_and_skippable(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        lead = add_lead(
            conn,
            AddLeadInput(url="https://example.com/sum", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        assert lead.summary is None
        listed = list_leads(conn, ListLeadsInput())
        assert any(item.lead_id == lead.lead_id and item.summary is None for item in listed.leads)

        summarised = summarise_lead(
            conn,
            SummariseLeadInput(lead_id=lead.lead_id, summary="Podcast mentioned X."),
        )
        assert summarised.summary == "Podcast mentioned X."
        # list_leads carries the same projection; no separate get_lead.
        after = list_leads(conn, ListLeadsInput())
        match = next(item for item in after.leads if item.lead_id == lead.lead_id)
        assert match.summary == "Podcast mentioned X."


def test_attach_promote_dispose(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="Existing case"))
        to_attach = add_lead(
            conn,
            AddLeadInput(url="https://example.com/a", note="attach me"),
            vault=vault,
            fetch=_html_fetch,
        )
        to_promote = add_lead(
            conn,
            AddLeadInput(url="https://example.com/p", note="promote me"),
            vault=vault,
            fetch=_html_fetch,
        )
        to_dispose = add_lead(
            conn,
            AddLeadInput(url="https://example.com/d", note="dispose me"),
            vault=vault,
            fetch=_html_fetch,
        )

        attached = attach_lead(
            conn,
            AttachLeadInput(lead_id=to_attach.lead_id, case_id=case.case_id),
        )
        assert attached.inbox_status == "attached"
        assert attached.case_id == case.case_id
        cap = conn.execute(
            select(captures.c.case_id).where(captures.c.id == attached.capture_id)
        ).one()
        assert int(cap.case_id) == case.case_id

        promoted = promote_lead(
            conn,
            PromoteLeadInput(lead_id=to_promote.lead_id, title="From lead"),
        )
        assert promoted.inbox_status == "promoted"
        assert promoted.case_id is not None
        assert promoted.case_id != case.case_id

        disposed = dispose_lead(conn, DisposeLeadInput(lead_id=to_dispose.lead_id))
        assert disposed.inbox_status == "disposed"
        assert disposed.case_id is None

        open_inbox = list_leads(conn, ListLeadsInput())
        open_ids = {item.lead_id for item in open_inbox.leads}
        assert to_attach.lead_id not in open_ids
        assert to_promote.lead_id not in open_ids
        assert to_dispose.lead_id not in open_ids

        with pytest.raises(DeskRefusal) as exc_info:
            attach_lead(
                conn,
                AttachLeadInput(lead_id=to_attach.lead_id, case_id=case.case_id),
            )
        assert exc_info.value.code == "LEAD_NOT_OPEN"


def test_ssrf_refuses_without_lead(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            add_lead(
                conn,
                AddLeadInput(url="http://127.0.0.1:8000/api/cases", note=""),
                vault=vault,
                fetch=_html_fetch,
            )
        assert exc_info.value.code == "CAPTURE_URL_BLOCKED"
        listed = list_leads(conn, ListLeadsInput(inbox_status=LIST_LEADS_ALL))
        assert listed.leads == []


def test_executor_add_lead_requires_claim(engine: Engine, tmp_path: Path) -> None:
    """MCP path: claim_token required (review #2). API path: neither field."""
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        # Operator path — no token — succeeds.
        op = add_lead(
            conn,
            AddLeadInput(url="https://example.com/op", note=""),
            vault=vault,
            fetch=_html_fetch,
        )
        assert op.inbox_status == "open"

        case = create_case(conn, CreateCaseInput(title="Claim case"))
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

        # Live claim succeeds and does not consume capture budget slots.
        lead = add_lead(
            conn,
            AddLeadInput(
                url="https://example.com/exec",
                note="parked",
                run_id=run_id,
                claim_token=token,
            ),
            vault=vault,
            fetch=_html_fetch,
        )
        assert lead.capture_id is not None
        used = conn.execute(select(captures.c.id).where(captures.c.run_id == run_id)).all()
        assert used == []  # lead capture has run_id NULL; not charged to budget

        with pytest.raises(DeskRefusal) as stale:
            add_lead(
                conn,
                AddLeadInput(
                    url="https://example.com/stale",
                    note="",
                    run_id=run_id,
                    claim_token="not-the-token",
                ),
                vault=vault,
                fetch=_html_fetch,
            )
        assert stale.value.code == "RUN_CLAIM_STALE"

        with pytest.raises(DeskRefusal) as incomplete:
            add_lead(
                conn,
                AddLeadInput(
                    url="https://example.com/half",
                    note="",
                    run_id=run_id,
                    claim_token=None,
                ),
                vault=vault,
                fetch=_html_fetch,
            )
        assert incomplete.value.code == "LEAD_CLAIM_INCOMPLETE"


def test_list_leads_refuses_unknown_inbox_status(engine: Engine) -> None:
    with connection_scope(engine) as conn:
        with pytest.raises(DeskRefusal) as exc_info:
            list_leads(conn, ListLeadsInput(inbox_status="not-a-status"))
        assert exc_info.value.code == "LEAD_INBOX_STATUS_INVALID"
