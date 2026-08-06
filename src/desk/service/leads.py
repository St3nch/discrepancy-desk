"""Lead inbox — material only, never claims (ADR 7 / D18).

add_lead is on both transports: the operator drops URLs from the browser; an
executor mid-run may park out-of-scope material without polluting its run budget.
Everything after the drop (attach, promote, dispose, summarise) is API-only.

Capture always runs on drop via the same retain path as capture_url. Auth-walled
responses become identity-only leads (no capture row). SSRF and other hard
failures remain refusals — no lead is written.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select, update

from desk.db.schema import captures, cases, document_versions, elements, leads
from desk.refusals import DeskRefusal
from desk.service.captures import (
    DEFAULT_LOCATOR_MAP_CAP,
    FetchFn,
    default_fetch,
    retain_capture_from_bytes,
)
from desk.service.cases import create_case
from desk.service.evidence import LEAD_INBOX_STATUSES, LIST_LEADS_ALL
from desk.service.lease import validate_and_refresh_claim
from desk.service.models import (
    AddLeadInput,
    AddLeadResult,
    AttachLeadInput,
    AttachLeadResult,
    CreateCaseInput,
    DisposeLeadInput,
    DisposeLeadResult,
    LeadRecord,
    ListLeadsInput,
    ListLeadsResult,
    LocatorElement,
    PromoteLeadInput,
    PromoteLeadResult,
    SummariseLeadInput,
    SummariseLeadResult,
)
from desk.vault.ssrf import assert_url_safe_to_fetch
from desk.vault.store import VaultStore


def _projection_markdown(elems: list[LocatorElement]) -> str:
    """Non-authoritative Markdown view for human browsing — never for quotation."""
    lines = [
        "<!-- READ-ONLY PROJECTION: not authoritative. Quote from locator map / stored "
        "elements only. -->",
        "",
    ]
    for el in elems:
        lines.append(f"<!-- locator={el.locator} type={el.element_type} -->")
        lines.append(el.text)
        lines.append("")
    return "\n".join(lines)


_AUTH_WALLED_CODE = "CAPTURE_AUTH_WALLED"
_UNSUPPORTED_TYPE_CODE = "CAPTURE_UNSUPPORTED_TYPE"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _load_lead_row(conn: Connection, lead_id: int) -> object | None:
    return conn.execute(
        select(
            leads.c.id,
            leads.c.url,
            leads.c.note,
            leads.c.summary,
            leads.c.material_status,
            leads.c.capture_id,
            leads.c.inbox_status,
            leads.c.case_id,
            leads.c.created_at,
            leads.c.updated_at,
        ).where(leads.c.id == lead_id)
    ).one_or_none()


def _capture_browse_fields(
    conn: Connection,
    capture_id: int | None,
    *,
    locator_map_cap: int = DEFAULT_LOCATOR_MAP_CAP,
) -> dict[str, object]:
    """Optional capture fields for LeadRecord projection."""
    empty: dict[str, object] = {
        "capture_status": None,
        "sha256": None,
        "content_type": None,
        "byte_size": None,
        "element_count": None,
        "projection_markdown": None,
    }
    if capture_id is None:
        return empty

    cap = conn.execute(
        select(
            captures.c.id,
            captures.c.status,
            captures.c.sha256,
            captures.c.content_type,
            captures.c.byte_size,
        ).where(captures.c.id == capture_id)
    ).one_or_none()
    if cap is None:
        return empty

    dv = conn.execute(
        select(document_versions.c.id)
        .where(document_versions.c.capture_id == capture_id)
        .order_by(document_versions.c.version_number.desc())
        .limit(1)
    ).one_or_none()
    element_count = 0
    projection: str | None = None
    if dv is not None:
        document_version_id = int(dv.id)
        element_count = int(
            conn.execute(
                select(func.count())
                .select_from(elements)
                .where(elements.c.document_version_id == document_version_id)
            ).scalar_one()
        )
        rows = conn.execute(
            select(
                elements.c.locator,
                elements.c.ordinal,
                elements.c.element_type,
                elements.c.text,
            )
            .where(elements.c.document_version_id == document_version_id)
            .order_by(elements.c.ordinal.asc())
            .limit(locator_map_cap)
        ).all()
        elems = [
            LocatorElement(
                locator=str(r.locator),
                ordinal=int(r.ordinal),
                element_type=str(r.element_type),
                text=str(r.text),
            )
            for r in rows
        ]
        projection = _projection_markdown(elems)

    return {
        "capture_status": str(cap.status),
        "sha256": str(cap.sha256),
        "content_type": str(cap.content_type),
        "byte_size": int(cap.byte_size),
        "element_count": element_count,
        "projection_markdown": projection,
    }


def _row_to_lead(
    conn: Connection,
    row: object,
    *,
    locator_map_cap: int = DEFAULT_LOCATOR_MAP_CAP,
) -> LeadRecord:
    capture_id = row.capture_id  # type: ignore[attr-defined]
    cap_id = int(capture_id) if capture_id is not None else None
    browse = _capture_browse_fields(conn, cap_id, locator_map_cap=locator_map_cap)
    case_raw = row.case_id  # type: ignore[attr-defined]
    return LeadRecord(
        lead_id=int(row.id),  # type: ignore[attr-defined]
        url=str(row.url),  # type: ignore[attr-defined]
        note=str(row.note),  # type: ignore[attr-defined]
        summary=None if row.summary is None else str(row.summary),  # type: ignore[attr-defined]
        material_status=str(row.material_status),  # type: ignore[attr-defined]
        capture_id=cap_id,
        capture_status=browse["capture_status"],  # type: ignore[arg-type]
        inbox_status=str(row.inbox_status),  # type: ignore[attr-defined]
        case_id=None if case_raw is None else int(case_raw),
        created_at=str(row.created_at),  # type: ignore[attr-defined]
        updated_at=str(row.updated_at),  # type: ignore[attr-defined]
        sha256=browse["sha256"],  # type: ignore[arg-type]
        content_type=browse["content_type"],  # type: ignore[arg-type]
        byte_size=browse["byte_size"],  # type: ignore[arg-type]
        element_count=browse["element_count"],  # type: ignore[arg-type]
        projection_markdown=browse["projection_markdown"],  # type: ignore[arg-type]
        projection_is_authoritative=False,
    )


def _require_open_lead(conn: Connection, lead_id: int) -> object:
    row = _load_lead_row(conn, lead_id)
    if row is None:
        raise DeskRefusal(
            code="LEAD_NOT_FOUND",
            what_happened=f"No lead exists with id {lead_id}.",
            what_was_preserved="Existing leads are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List leads and use an existing lead_id, or add a new lead.",
        )
    status = str(row.inbox_status)  # type: ignore[attr-defined]
    if status != "open":
        raise DeskRefusal(
            code="LEAD_NOT_OPEN",
            what_happened=(
                f"Lead {lead_id} has inbox_status {status!r}; "
                "only open leads can be attached, promoted, or disposed."
            ),
            what_was_preserved="The lead is unchanged.",
            what_was_not_changed="No attachment, promotion, or disposal was recorded.",
            what_you_can_do="Choose an open lead from the inbox.",
        )
    return row


def add_lead(
    conn: Connection,
    params: AddLeadInput,
    *,
    vault: VaultStore,
    fetch: FetchFn | None = None,
    locator_map_cap: int = DEFAULT_LOCATOR_MAP_CAP,
) -> AddLeadResult:
    """Drop a URL into the inbox and capture immediately (always).

    Auth-walled (401/402/403) → identity_only lead, no capture bytes stored.
    Unsupported content type after a successful fetch → unsupported_type lead,
    URL parked, no Vault object (ticket 09a). retain_capture_from_bytes is
    unchanged; parking is a catch on CAPTURE_UNSUPPORTED_TYPE plus a lead
    insert — the same pattern as identity_only.

    material_status / capture_id (deliberate CHECK, not a binary extension):
    - captured → capture_id NOT NULL (bytes retained)
    - identity_only | unsupported_type → capture_id NULL (URL only)
    Both non-capture statuses forbid a capture_id so neither can masquerade
    as evidence. Soft 200 OK walls remain ordinary captured material (D19).

    SSRF and other hard fetch failures still refuse with no lead row.

    Executor (MCP) path: run_id + claim_token required; lease validated via
    validate_and_refresh_claim. Lead drops do **not** consume capture_budget —
    the executor case exists so out-of-scope material does not burn the run's
    allowance.
    TODO(ticket-09 review #2): a separate per-run lead-drop cap is the right
    shape so an executor cannot write unbounded Vault objects via add_lead, but
    that number is the operator's to set — do not invent a hard-coded limit here.

    Operator (API) path: omit run_id and claim_token; no claim authority needed.
    """
    # Dual-path authority: both claim fields or neither.
    has_run = params.run_id is not None
    has_token = bool((params.claim_token or "").strip())
    if has_run ^ has_token:
        raise DeskRefusal(
            code="LEAD_CLAIM_INCOMPLETE",
            what_happened=(
                "add_lead executor path requires both run_id and claim_token; "
                "operator path requires neither."
            ),
            what_was_preserved="No lead was written.",
            what_was_not_changed="The inbox is unchanged.",
            what_you_can_do=(
                "From MCP: pass run_id and claim_token from claim_next_run. "
                "From the operator API: omit both."
            ),
        )
    if has_run and has_token:
        # No budget check — lead drops are not charged against capture_budget.
        assert params.run_id is not None and params.claim_token is not None
        validate_and_refresh_claim(conn, params.run_id, params.claim_token)

    do_fetch = fetch if fetch is not None else default_fetch
    url = assert_url_safe_to_fetch(params.url)
    note = (params.note or "").strip()
    now = _utc_now()

    capture_id: int | None = None
    material_status = "captured"
    try:
        raw, content_type = do_fetch(url)
    except DeskRefusal as refusal:
        if refusal.code == _AUTH_WALLED_CODE:
            material_status = "identity_only"
            raw = b""
            content_type = ""
        else:
            # SSRF, DNS, timeout, etc. — fail closed; no lead row.
            raise
    except Exception as exc:  # noqa: BLE001
        raise DeskRefusal(
            code="CAPTURE_FETCH_FAILED",
            what_happened=f"Failed to fetch {url!r}: {type(exc).__name__}.",
            what_was_preserved="No lead was written.",
            what_was_not_changed="The inbox is unchanged.",
            what_you_can_do="Check the URL is reachable and retry add_lead.",
        ) from None

    if material_status == "captured":
        try:
            retained = retain_capture_from_bytes(
                conn,
                vault=vault,
                url=url,
                raw=raw,
                content_type=content_type,
                run_id=None,
                case_id=None,
                locator_map_cap=locator_map_cap,
            )
        except DeskRefusal as refusal:
            if refusal.code == _UNSUPPORTED_TYPE_CODE:
                # Fetched, unparseable — park URL only; no Vault write occurred
                # (assert_content_type_supported raises before store).
                material_status = "unsupported_type"
                capture_id = None
            else:
                raise
        else:
            capture_id = retained.capture_id

    result = conn.execute(
        insert(leads).values(
            url=url,
            note=note,
            summary=None,
            material_status=material_status,
            capture_id=capture_id,
            inbox_status="open",
            case_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    pk = result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into leads did not return a primary key")
    lead_id = int(pk[0])
    row = _load_lead_row(conn, lead_id)
    if row is None:
        raise RuntimeError(f"lead {lead_id} missing immediately after insert")
    return AddLeadResult(**_row_to_lead(conn, row, locator_map_cap=locator_map_cap).model_dump())


def list_leads(conn: Connection, params: ListLeadsInput) -> ListLeadsResult:
    """List leads. Default filter is open inbox only."""
    status_filter = params.inbox_status
    if status_filter is None:
        status_filter = "open"
    allowed = LEAD_INBOX_STATUSES | {LIST_LEADS_ALL}
    if status_filter not in allowed:
        raise DeskRefusal(
            code="LEAD_INBOX_STATUS_INVALID",
            what_happened=(
                f"inbox_status filter {status_filter!r} is not recognised. "
                f"Use one of {sorted(LEAD_INBOX_STATUSES)} or {LIST_LEADS_ALL!r}."
            ),
            what_was_preserved="Existing leads are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do=(
                f"Pass a stored inbox_status, omit the filter for open only, "
                f"or pass {LIST_LEADS_ALL!r} for every status."
            ),
        )
    q = select(
        leads.c.id,
        leads.c.url,
        leads.c.note,
        leads.c.summary,
        leads.c.material_status,
        leads.c.capture_id,
        leads.c.inbox_status,
        leads.c.case_id,
        leads.c.created_at,
        leads.c.updated_at,
    ).order_by(leads.c.id.asc())
    if status_filter != LIST_LEADS_ALL:
        q = q.where(leads.c.inbox_status == status_filter)
    rows = conn.execute(q).all()
    return ListLeadsResult(leads=[_row_to_lead(conn, r) for r in rows])


def attach_lead(conn: Connection, params: AttachLeadInput) -> AttachLeadResult:
    """Attach an open lead to an existing case. Human-only."""
    row = _require_open_lead(conn, params.lead_id)
    case_row = conn.execute(select(cases.c.id).where(cases.c.id == params.case_id)).one_or_none()
    if case_row is None:
        raise DeskRefusal(
            code="CASE_NOT_FOUND",
            what_happened=f"No case exists with id {params.case_id}.",
            what_was_preserved="The lead is unchanged.",
            what_was_not_changed="No attachment was recorded.",
            what_you_can_do="Create a case or attach to an existing case_id.",
        )

    now = _utc_now()
    cap_id = row.capture_id  # type: ignore[attr-defined]
    if cap_id is not None:
        conn.execute(
            update(captures).where(captures.c.id == int(cap_id)).values(case_id=params.case_id)
        )

    conn.execute(
        update(leads)
        .where(leads.c.id == params.lead_id)
        .values(
            inbox_status="attached",
            case_id=params.case_id,
            updated_at=now,
        )
    )
    updated = _load_lead_row(conn, params.lead_id)
    assert updated is not None
    return AttachLeadResult(**_row_to_lead(conn, updated).model_dump())


def promote_lead(conn: Connection, params: PromoteLeadInput) -> PromoteLeadResult:
    """Create a new case from an open lead and attach the lead to it. Human-only.

    Composes create_case and attach_lead on the shared ``conn``, so the whole
    promote is atomic in one transaction. That works only because those service
    functions take a Connection rather than opening their own connection_scope.
    Do not copy this pattern against functions that begin their own transactions
    — the pair would no longer be atomic.
    """
    _require_open_lead(conn, params.lead_id)
    title = params.title.strip()
    if not title:
        raise DeskRefusal(
            code="CASE_TITLE_EMPTY",
            what_happened="Case title was empty after trimming whitespace.",
            what_was_preserved="The lead is unchanged; no case was created.",
            what_was_not_changed="No promotion was recorded.",
            what_you_can_do="Retry with a non-empty title for the new case.",
        )
    created = create_case(conn, CreateCaseInput(title=title))
    attach_lead(
        conn,
        AttachLeadInput(lead_id=params.lead_id, case_id=created.case_id),
    )
    # attach_lead sets inbox_status=attached; promote uses promoted.
    now = _utc_now()
    conn.execute(
        update(leads)
        .where(leads.c.id == params.lead_id)
        .values(inbox_status="promoted", updated_at=now)
    )
    updated = _load_lead_row(conn, params.lead_id)
    assert updated is not None
    return PromoteLeadResult(**_row_to_lead(conn, updated).model_dump())


def dispose_lead(conn: Connection, params: DisposeLeadInput) -> DisposeLeadResult:
    """Dispose an open lead (not worth pursuing). Human-only. Capture bytes remain."""
    _require_open_lead(conn, params.lead_id)
    now = _utc_now()
    conn.execute(
        update(leads)
        .where(leads.c.id == params.lead_id)
        .values(inbox_status="disposed", updated_at=now)
    )
    updated = _load_lead_row(conn, params.lead_id)
    assert updated is not None
    return DisposeLeadResult(**_row_to_lead(conn, updated).model_dump())


def summarise_lead(conn: Connection, params: SummariseLeadInput) -> SummariseLeadResult:
    """Store an optional summary. Skippable — drop never requires this.

    Description only, not claim extraction (ADR 7). Human-only API surface.
    """
    row = _load_lead_row(conn, params.lead_id)
    if row is None:
        raise DeskRefusal(
            code="LEAD_NOT_FOUND",
            what_happened=f"No lead exists with id {params.lead_id}.",
            what_was_preserved="Existing leads are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="List leads and summarise an existing lead_id.",
        )
    summary = params.summary.strip()
    if not summary:
        raise DeskRefusal(
            code="LEAD_SUMMARY_EMPTY",
            what_happened="Summary was empty after trimming whitespace.",
            what_was_preserved="The lead is unchanged.",
            what_was_not_changed="No summary was stored.",
            what_you_can_do="Provide non-empty summary text, or skip summarising.",
        )
    now = _utc_now()
    conn.execute(
        update(leads).where(leads.c.id == params.lead_id).values(summary=summary, updated_at=now)
    )
    updated = _load_lead_row(conn, params.lead_id)
    assert updated is not None
    return SummariseLeadResult(**_row_to_lead(conn, updated).model_dump())
