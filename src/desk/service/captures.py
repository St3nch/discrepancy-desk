"""Governed capture operations — Vault write path (ADR 1).

Budget (F-15): a run's capture_budget counts *retained* captures only. Failed
fetches (timeout, DNS, HTTP error, SSRF block, unsupported type before store)
do not consume a slot — so flaky URLs do not burn the operator's allowance.
Wall-clock and rate limits bound retry loops; budget bounds Vault retention.

Regions (F-22): each element gets a full-span region row (0..len(text)). Locators
may address a sub-range as e/{ordinal}/r/{start}-{end}; propose_claim resolves
that slice of elements.text for quote verification.

Lead captures (ticket 09): same retain path as run captures — store, hash, parse,
elements. Ownership columns (run_id, case_id) may be null until a lead is attached.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest

from sqlalchemy import Connection, func, insert, select

from desk.db.schema import captures, document_versions, elements, regions, runs
from desk.refusals import DeskRefusal
from desk.service.lease import validate_and_refresh_claim, validate_claim
from desk.service.models import (
    CaptureUrlInput,
    CaptureUrlResult,
    FindQuoteInput,
    FindQuoteMatch,
    FindQuoteResult,
    LocatorElement,
    ReadCaptureInput,
    ReadCaptureResult,
)
from desk.vault.parse import (
    PARSER_NAME,
    assert_content_type_supported,
    parse_bytes,
)
from desk.vault.ssrf import assert_url_safe_to_fetch, safe_http_get
from desk.vault.store import VaultStore

FetchFn = Callable[[str], tuple[bytes, str]]

# Default locator-map cap when not overridden by settings at the call site.
DEFAULT_LOCATOR_MAP_CAP = 50


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def default_fetch(url: str) -> tuple[bytes, str]:
    """HTTP GET with SSRF guards (resolved IPs + manual redirect re-check)."""
    return safe_http_get(url)


def _validate_url(url: str) -> str:
    """Scheme + resolved-address SSRF check (re-applied on each redirect hop)."""
    return assert_url_safe_to_fetch(url)


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


@dataclass(frozen=True)
class RetainedCapture:
    """Result of the shared store+parse path used by run and lead capture."""

    capture_id: int
    url: str
    sha256: str
    content_type: str
    byte_size: int
    status: str
    element_count: int
    elements_returned: int
    truncated: bool
    elements: list[LocatorElement]
    projection_markdown: str


def retain_capture_from_bytes(
    conn: Connection,
    *,
    vault: VaultStore,
    url: str,
    raw: bytes,
    content_type: str,
    run_id: int | None,
    case_id: int | None,
    locator_map_cap: int = DEFAULT_LOCATOR_MAP_CAP,
) -> RetainedCapture:
    """Store raw bytes, hash, parse into elements — one path for runs and leads.

    F-14: refuse unparseable types before Vault/Record write so claims cannot
    bind to replacement-character garbage. Choice: do *not* retain the bytes
    when parse is refused. Budget (run path) is not consumed when this raises.
    """
    media_type = assert_content_type_supported(content_type, raw)

    digest = VaultStore.sha256_hex(raw)
    relpath = vault.write_raw(sha256=digest, data=raw)
    now = _utc_now()

    cap_result = conn.execute(
        insert(captures).values(
            run_id=run_id,
            case_id=case_id,
            url=url,
            sha256=digest,
            content_type=media_type,
            byte_size=len(raw),
            vault_relpath=relpath,
            status="unexamined",
            created_at=now,
        )
    )
    pk = cap_result.inserted_primary_key
    if pk is None or pk[0] is None:
        raise RuntimeError("insert into captures did not return a primary key")
    capture_id = int(pk[0])

    dv_result = conn.execute(
        insert(document_versions).values(
            capture_id=capture_id,
            version_number=1,
            parser_name=PARSER_NAME,
            created_at=now,
        )
    )
    dv_pk = dv_result.inserted_primary_key
    if dv_pk is None or dv_pk[0] is None:
        raise RuntimeError("insert into document_versions did not return a primary key")
    document_version_id = int(dv_pk[0])

    parsed = parse_bytes(raw, media_type)
    locator_elements: list[LocatorElement] = []
    for pe in parsed:
        el_result = conn.execute(
            insert(elements).values(
                document_version_id=document_version_id,
                locator=pe.locator,
                ordinal=pe.ordinal,
                element_type=pe.element_type,
                text=pe.text,
            )
        )
        el_pk = el_result.inserted_primary_key
        if el_pk is None or el_pk[0] is None:
            raise RuntimeError("insert into elements did not return a primary key")
        element_id = int(el_pk[0])
        # Full-span region placeholder — region locators address slices (F-22).
        conn.execute(
            insert(regions).values(
                element_id=element_id,
                start_offset=0,
                end_offset=len(pe.text),
            )
        )
        locator_elements.append(
            LocatorElement(
                locator=pe.locator,
                ordinal=pe.ordinal,
                element_type=pe.element_type,
                text=pe.text,
            )
        )

    capped = locator_elements[:locator_map_cap]
    truncated = len(locator_elements) > locator_map_cap
    projection = _projection_markdown(capped)

    return RetainedCapture(
        capture_id=capture_id,
        url=url,
        sha256=digest,
        content_type=media_type,
        byte_size=len(raw),
        status="unexamined",
        element_count=len(locator_elements),
        elements_returned=len(capped),
        truncated=truncated,
        elements=capped,
        projection_markdown=projection,
    )


def capture_url(
    conn: Connection,
    params: CaptureUrlInput,
    *,
    vault: VaultStore,
    fetch: FetchFn | None = None,
    locator_map_cap: int = DEFAULT_LOCATOR_MAP_CAP,
) -> CaptureUrlResult:
    """Fetch URL through the backend, store immutable bytes, parse locator map.

    Counts against the run capture budget before the fetch is retained. Only a
    claimed run may capture (executor work path).
    """
    do_fetch = fetch if fetch is not None else default_fetch
    url = _validate_url(params.url)

    # Shared validate-and-refresh: claimed + unexpired lease + claim_token (F-25).
    validate_and_refresh_claim(conn, params.run_id, params.claim_token)

    run_row = conn.execute(
        select(
            runs.c.id,
            runs.c.case_id,
            runs.c.status,
            runs.c.capture_budget,
        ).where(runs.c.id == params.run_id)
    ).one_or_none()
    if run_row is None:
        raise DeskRefusal(
            code="RUN_NOT_FOUND",
            what_happened=f"No run exists with id {params.run_id}.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="No capture was written.",
            what_you_can_do="Claim a run via claim_next_run, then capture against that run_id.",
        )

    used = int(
        conn.execute(
            select(func.count()).select_from(captures).where(captures.c.run_id == params.run_id)
        ).scalar_one()
    )
    budget = int(run_row.capture_budget)
    if used >= budget:
        raise DeskRefusal(
            code="BUDGET_EXHAUSTED",
            what_happened=(
                f"Run {params.run_id} has used {used} of {budget} capture budget slots."
            ),
            what_was_preserved="Existing captures are unchanged; no fetch was stored.",
            what_was_not_changed="No new capture was written; budget remains exhausted.",
            what_you_can_do=(
                "Close this run or ask the operator for a new run with a higher capture_budget."
            ),
        )

    try:
        raw, content_type = do_fetch(url)
    except DeskRefusal:
        # SSRF / HTTP / size / auth-wall refusals from safe_http_get keep their codes
        # (CAPTURE_URL_BLOCKED, CAPTURE_HTTP_ERROR, CAPTURE_AUTH_WALLED, …).
        # Failed fetches do not consume capture_budget (F-15).
        raise
    except Exception as exc:  # noqa: BLE001 — unexpected transport failures only
        raise DeskRefusal(
            code="CAPTURE_FETCH_FAILED",
            what_happened=f"Failed to fetch {url!r}: {type(exc).__name__}.",
            what_was_preserved="Existing captures and the run budget are unchanged.",
            what_was_not_changed="No capture was written.",
            what_you_can_do="Check the URL is reachable and retry capture_url.",
        ) from None

    case_id = int(run_row.case_id)
    retained = retain_capture_from_bytes(
        conn,
        vault=vault,
        url=url,
        raw=raw,
        content_type=content_type,
        run_id=params.run_id,
        case_id=case_id,
        locator_map_cap=locator_map_cap,
    )

    return CaptureUrlResult(
        capture_id=retained.capture_id,
        run_id=params.run_id,
        case_id=case_id,
        url=retained.url,
        sha256=retained.sha256,
        content_type=retained.content_type,
        byte_size=retained.byte_size,
        status=retained.status,
        element_count=retained.element_count,
        elements_returned=retained.elements_returned,
        truncated=retained.truncated,
        elements=retained.elements,
        projection_markdown=retained.projection_markdown,
        projection_is_authoritative=False,
    )


def assert_executor_may_read_capture(
    conn: Connection,
    capture_id: int,
    claim_token: str,
    *,
    refresh_lease: bool = True,
) -> None:
    """Authority gate for executor reads of a capture (read_capture / find_quote).

    Run-owned: claim_token must hold that run.
    Case-attached lead: claim_token must hold a claimed run on that case.
    Unattached lead: refused (operator-only).

    ``refresh_lease=False`` validates without extending the lease (find_quote is
    read-only and must not mutate run state — ticket 12a).
    """
    cap = conn.execute(
        select(captures.c.id, captures.c.run_id, captures.c.case_id).where(
            captures.c.id == capture_id
        )
    ).one_or_none()
    if cap is None:
        raise DeskRefusal(
            code="CAPTURE_NOT_FOUND",
            what_happened=f"No capture exists with id {capture_id}.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Call capture_url first, then read with that capture_id.",
        )

    if cap.run_id is not None:
        if refresh_lease:
            validate_and_refresh_claim(conn, int(cap.run_id), claim_token)
        else:
            validate_claim(conn, int(cap.run_id), claim_token, refresh=False)
        return

    if cap.case_id is not None:
        # Lead material attached to a case: claim_token must hold a claimed run
        # on that case (same token authority pattern as read_case_context).
        presented = (claim_token or "").strip()
        candidates = conn.execute(
            select(runs.c.id, runs.c.claim_token)
            .where(runs.c.case_id == int(cap.case_id))
            .where(runs.c.status == "claimed")
            .where(runs.c.claim_token.is_not(None))
        ).all()
        held_run_id: int | None = None
        for row in candidates:
            stored = row.claim_token
            if stored is not None and compare_digest(presented, str(stored)):
                held_run_id = int(row.id)
                break
        if held_run_id is None:
            raise DeskRefusal(
                code="RUN_CLAIM_STALE",
                what_happened=(
                    "claim_token does not hold a claimed run on the case that owns "
                    f"capture {capture_id}."
                ),
                what_was_preserved="Existing captures are unchanged.",
                what_was_not_changed="Nothing was written.",
                what_you_can_do=(
                    "Present the claim_token for a claimed run on this capture's case."
                ),
            )
        if refresh_lease:
            validate_and_refresh_claim(conn, held_run_id, presented)
        else:
            validate_claim(conn, held_run_id, presented, refresh=False)
        return

    raise DeskRefusal(
        code="CAPTURE_NOT_ON_CASE",
        what_happened=(
            f"Capture {capture_id} is unattached lead material and cannot "
            "be read through the executor tool surface."
        ),
        what_was_preserved="Existing captures are unchanged.",
        what_was_not_changed="Nothing was written.",
        what_you_can_do=(
            "The operator must attach the lead to a case before an executor can read this capture."
        ),
    )


def _latest_document_version_id(conn: Connection, capture_id: int) -> int:
    dv = conn.execute(
        select(document_versions.c.id)
        .where(document_versions.c.capture_id == capture_id)
        .order_by(document_versions.c.version_number.desc())
        .limit(1)
    ).one_or_none()
    if dv is None:
        raise DeskRefusal(
            code="CAPTURE_NOT_PARSED",
            what_happened=f"Capture {capture_id} has no document_version.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Re-capture the URL if parsing failed; report if this persists.",
        )
    return int(dv.id)


def read_capture(
    conn: Connection,
    params: ReadCaptureInput,
) -> ReadCaptureResult:
    """Read further elements from an already-made capture (beyond capture_url cap).

    Run-owned captures: claim_token must hold that run.
    Case-attached lead captures (run_id null, case_id set): claim_token must hold
    a claimed run on that case. Unattached lead captures are operator-only (API).
    """
    assert_executor_may_read_capture(
        conn,
        params.capture_id,
        params.claim_token,
        refresh_lease=True,
    )

    document_version_id = _latest_document_version_id(conn, params.capture_id)
    total = int(
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
        .where(elements.c.ordinal >= params.offset)
        .order_by(elements.c.ordinal.asc())
        .limit(params.limit)
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
    truncated = params.offset + len(elems) < total
    return ReadCaptureResult(
        capture_id=params.capture_id,
        offset=params.offset,
        limit=params.limit,
        element_count=total,
        elements_returned=len(elems),
        truncated=truncated,
        elements=elems,
        projection_markdown=_projection_markdown(elems),
        projection_is_authoritative=False,
    )


def find_quote(conn: Connection, params: FindQuoteInput) -> FindQuoteResult:
    """Locate an exact substring in a capture's element text (ticket 12a / F-55).

    Returns ``e/{n}/r/{start}-{end}`` when the substring occurs exactly once.
    Structured miss distinguishes not-found from ambiguous (multiple hits).
    Exact match only — never fuzzy, never normalised. Does not refresh the lease
    and does not consume capture budget. ``propose_claim`` still verifies independently.
    """
    quoted = params.quoted_text
    if quoted == "":
        raise DeskRefusal(
            code="FIND_QUOTE_EMPTY",
            what_happened="quoted_text was empty; every position would match.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do=(
                "Pass the exact non-empty substring to locate. "
                "Copy it from the element text returned by capture_url / read_capture."
            ),
        )

    assert_executor_may_read_capture(
        conn,
        params.capture_id,
        params.claim_token,
        refresh_lease=False,
    )

    document_version_id = _latest_document_version_id(conn, params.capture_id)
    rows = conn.execute(
        select(
            elements.c.locator,
            elements.c.ordinal,
            elements.c.text,
        )
        .where(elements.c.document_version_id == document_version_id)
        .order_by(elements.c.ordinal.asc())
    ).all()

    matches: list[FindQuoteMatch] = []
    for row in rows:
        text = str(row.text)
        element_locator = str(row.locator)
        start = 0
        while True:
            idx = text.find(quoted, start)
            if idx < 0:
                break
            end = idx + len(quoted)
            matches.append(
                FindQuoteMatch(
                    locator=f"{element_locator}/r/{idx}-{end}",
                    element_locator=element_locator,
                    start=idx,
                    end=end,
                )
            )
            start = idx + 1

    count = len(matches)
    if count == 0:
        return FindQuoteResult(
            capture_id=params.capture_id,
            found=False,
            reason="not_found",
            match_count=0,
            locator=None,
            matches=[],
        )
    if count > 1:
        element_ids = {m.element_locator for m in matches}
        reason = "multiple_elements" if len(element_ids) > 1 else "multiple_in_element"
        return FindQuoteResult(
            capture_id=params.capture_id,
            found=False,
            reason=reason,
            match_count=count,
            locator=None,
            matches=matches,
        )

    only = matches[0]
    return FindQuoteResult(
        capture_id=params.capture_id,
        found=True,
        reason="unique",
        match_count=1,
        locator=only.locator,
        matches=matches,
    )


def list_capture_summaries_for_case(conn: Connection, case_id: int) -> list:
    """Case-page capture rows for get_case (id, status, url)."""
    from desk.service.models import CaseCaptureSummary

    rows = conn.execute(
        select(captures.c.id, captures.c.url, captures.c.status)
        .where(captures.c.case_id == case_id)
        .order_by(captures.c.id.asc())
    ).all()
    return [
        CaseCaptureSummary(
            capture_id=int(r.id),
            url=str(r.url),
            status=str(r.status),
        )
        for r in rows
    ]
