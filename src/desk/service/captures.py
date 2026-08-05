"""Governed capture operations — Vault write path (ADR 1).

Budget (F-15): a run's capture_budget counts *retained* captures only. Failed
fetches (timeout, DNS, HTTP error, SSRF block, unsupported type before store)
do not consume a slot — so flaky URLs do not burn the operator's allowance.
Wall-clock and rate limits bound retry loops; budget bounds Vault retention.

Regions (F-22): each element gets a full-span region row (0..len(text)). Locators
may address a sub-range as e/{ordinal}/r/{start}-{end}; propose_claim resolves
that slice of elements.text for quote verification.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Connection, func, insert, select

from desk.db.schema import captures, document_versions, elements, regions, runs
from desk.refusals import DeskRefusal
from desk.service.lease import validate_and_refresh_claim
from desk.service.models import (
    CaptureUrlInput,
    CaptureUrlResult,
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


def capture_url(
    conn: Connection,
    params: CaptureUrlInput,
    *,
    vault: VaultStore,
    fetch: FetchFn = default_fetch,
    locator_map_cap: int = DEFAULT_LOCATOR_MAP_CAP,
) -> CaptureUrlResult:
    """Fetch URL through the backend, store immutable bytes, parse locator map.

    Counts against the run capture budget before the fetch is retained. Only a
    claimed run may capture (executor work path).
    """
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
        raw, content_type = fetch(url)
    except DeskRefusal:
        # SSRF / HTTP / size refusals from safe_http_get must keep their codes
        # (CAPTURE_URL_BLOCKED, CAPTURE_HTTP_ERROR, CAPTURE_TOO_LARGE, …).
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

    # F-14: refuse unparseable types before Vault/Record write so ticket 05 cannot
    # bind claims to replacement-character garbage. Choice: do *not* retain the
    # bytes as a capture when parse is refused — without a quotation surface the
    # capture cannot participate in capture-then-cite; a future PDF/parser ticket
    # will store + parse properly. Budget is not consumed (no retained capture).
    media_type = assert_content_type_supported(content_type, raw)

    digest = VaultStore.sha256_hex(raw)
    relpath = vault.write_raw(sha256=digest, data=raw)
    now = _utc_now()
    case_id = int(run_row.case_id)

    cap_result = conn.execute(
        insert(captures).values(
            run_id=params.run_id,
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
        # Full-span region placeholder — not addressable until locator grammar grows (F-16).
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

    return CaptureUrlResult(
        capture_id=capture_id,
        run_id=params.run_id,
        case_id=case_id,
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
        projection_is_authoritative=False,
    )


def read_capture(
    conn: Connection,
    params: ReadCaptureInput,
) -> ReadCaptureResult:
    """Read further elements from an already-made capture (beyond capture_url cap)."""
    cap = conn.execute(
        select(captures.c.id, captures.c.run_id).where(captures.c.id == params.capture_id)
    ).one_or_none()
    if cap is None:
        raise DeskRefusal(
            code="CAPTURE_NOT_FOUND",
            what_happened=f"No capture exists with id {params.capture_id}.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Call capture_url first, then read_capture with that capture_id.",
        )
    validate_and_refresh_claim(conn, int(cap.run_id), params.claim_token)

    dv = conn.execute(
        select(document_versions.c.id)
        .where(document_versions.c.capture_id == params.capture_id)
        .order_by(document_versions.c.version_number.desc())
        .limit(1)
    ).one_or_none()
    if dv is None:
        raise DeskRefusal(
            code="CAPTURE_NOT_PARSED",
            what_happened=f"Capture {params.capture_id} has no document_version.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Re-capture the URL if parsing failed; report if this persists.",
        )

    document_version_id = int(dv.id)
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


def list_capture_summaries_for_case(conn: Connection, case_id: int) -> list[str]:
    """Human projection strings for get_case (grows later into full capture views)."""
    rows = conn.execute(
        select(captures.c.id, captures.c.url, captures.c.status)
        .where(captures.c.case_id == case_id)
        .order_by(captures.c.id.asc())
    ).all()
    return [f"#{int(r.id)} {r.status} {r.url}" for r in rows]
