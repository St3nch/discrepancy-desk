"""MCP tool surface — only tools listed in wiring.mcp_tool_names().

Ticket 12a — three-category refusal boundary:

* Body: ``mcp_tool_boundary`` — DeskRefusal passes through; unexpected →
  TOOL_INTERNAL_ERROR (non-correctable, logged).
* Dispatch: ``install_tool_dispatch_envelope`` — framework arg validation
  failures leave as TOOL_ARGUMENT_INVALID (correctable); already-enveloped
  body errors are unwrapped from Tool.run's prefix. Schemas stay intact.

Do not add bare try/except Exception in tool bodies that re-labels domain refusals.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import Engine

from desk.config import get_settings
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    add_lead,
    capture_url,
    claim_next_run,
    close_run,
    find_quote,
    propose_claim,
    propose_rendition,
    read_capture,
    read_case_context,
    suspend_run,
)
from desk.service.models import (
    AddLeadInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CloseRunInput,
    EvidenceDimensions,
    FindQuoteInput,
    ProposeClaimInput,
    ProposedOpenQuestionInput,
    ProposeRenditionInput,
    QuoteBindingInput,
    ReadCaptureInput,
    ReadCaseContextInput,
    RenditionUnitInput,
    SuspendRunInput,
)
from desk.transports.refusal_mcp import (
    install_tool_dispatch_envelope,
    mcp_tool_boundary,
)
from desk.transports.wiring import mcp_tool_names
from desk.vault.store import VaultStore


def parse_proposed_open_question(
    item: object,
    *,
    index: int,
) -> ProposedOpenQuestionInput:
    """Map one close_run proposed_questions dict to the service model (F-54).

    Canonical keys: ``text``, ``rationale``, ``proposed_scope``.
    Alias: ``scope`` is accepted for ``proposed_scope`` (the tool description
    historically said "scope"; bare KeyError on ``proposed_scope`` leaked as a
    non-refusal string at the last step of a live run).
    """
    if not isinstance(item, dict):
        raise DeskRefusal(
            code="OPEN_QUESTION_SHAPE_INVALID",
            what_happened=(
                f"proposed_questions[{index}] must be an object with text, "
                "rationale, and proposed_scope (or scope)."
            ),
            what_was_preserved="The run was not closed; no agenda was written.",
            what_was_not_changed="Run status, captures, and claims are unchanged.",
            what_you_can_do=(
                "Pass a list of objects: "
                '{"text": "...", "rationale": "...", "proposed_scope": "..."}.'
            ),
        )

    missing: list[str] = []
    if "text" not in item:
        missing.append("text")
    if "rationale" not in item:
        missing.append("rationale")
    has_scope = "proposed_scope" in item or "scope" in item
    if not has_scope:
        missing.append("proposed_scope (or scope)")

    if missing:
        raise DeskRefusal(
            code="OPEN_QUESTION_FIELD_MISSING",
            what_happened=(
                f"proposed_questions[{index}] is missing required field(s): {', '.join(missing)}."
            ),
            what_was_preserved="The run was not closed; no agenda was written.",
            what_was_not_changed="Run status, captures, and claims are unchanged.",
            what_you_can_do=(
                "Each proposed question needs text, rationale, and proposed_scope. "
                "The field name is proposed_scope (scope is accepted as an alias). "
                "Do not omit keys — empty string is different from missing."
            ),
        )

    # Prefer the canonical key when both are present.
    scope_val = item["proposed_scope"] if "proposed_scope" in item else item["scope"]
    return ProposedOpenQuestionInput(
        text=str(item["text"]),
        rationale=str(item["rationale"]),
        proposed_scope=str(scope_val),
    )


def parse_rendition_unit(item: object, *, index: int) -> RenditionUnitInput:
    """Map one propose_rendition units dict to the service model (F-58).

    Required keys: ``body``, ``claim_ids`` (list of ints). Missing or wrong
    shape refuses with DeskRefusal — never AttributeError/ValueError.
    """
    if not isinstance(item, dict):
        raise DeskRefusal(
            code="RENDITION_UNIT_SHAPE_INVALID",
            what_happened=(f"units[{index}] must be an object with body and claim_ids."),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=('Pass units as objects: {"body": "...", "claim_ids": [1, 2]}.'),
        )

    missing: list[str] = []
    if "body" not in item:
        missing.append("body")
    if "claim_ids" not in item:
        missing.append("claim_ids")
    if missing:
        raise DeskRefusal(
            code="RENDITION_UNIT_FIELD_MISSING",
            what_happened=(f"units[{index}] is missing required field(s): {', '.join(missing)}."),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Each unit needs body (string) and claim_ids (list of claim id integers). "
                "Keys are body and claim_ids."
            ),
        )

    claim_raw = item["claim_ids"]
    if not isinstance(claim_raw, list):
        raise DeskRefusal(
            code="RENDITION_UNIT_CLAIM_IDS_INVALID",
            what_happened=(
                f"units[{index}].claim_ids must be a list of integers "
                f"(got {type(claim_raw).__name__})."
            ),
            what_was_preserved="No rendition was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Pass claim_ids as a JSON array of integers, e.g. [12, 15].",
        )
    claim_ids: list[int] = []
    for j, c in enumerate(claim_raw):
        try:
            claim_ids.append(int(c))
        except (TypeError, ValueError):
            raise DeskRefusal(
                code="RENDITION_UNIT_CLAIM_IDS_INVALID",
                what_happened=(f"units[{index}].claim_ids[{j}] is not an integer (got {c!r})."),
                what_was_preserved="No rendition was written.",
                what_was_not_changed="The Record is unchanged.",
                what_you_can_do="Use integer claim ids from the angle's eligible set.",
            ) from None

    return RenditionUnitInput(body=str(item["body"]), claim_ids=claim_ids)


def parse_quote_binding(item: object, *, index: int) -> QuoteBindingInput:
    """Map one propose_claim quote_bindings dict (same class as F-54 / F-58)."""
    if not isinstance(item, dict):
        raise DeskRefusal(
            code="QUOTE_BINDING_SHAPE_INVALID",
            what_happened=(
                f"quote_bindings[{index}] must be an object with capture_id, locator, "
                "and quoted_text."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                'Pass objects: {"capture_id": 1, "locator": "e/0/r/0-10", "quoted_text": "..."}.'
            ),
        )
    missing: list[str] = []
    for key in ("capture_id", "locator", "quoted_text"):
        if key not in item:
            missing.append(key)
    if missing:
        raise DeskRefusal(
            code="QUOTE_BINDING_FIELD_MISSING",
            what_happened=(
                f"quote_bindings[{index}] is missing required field(s): {', '.join(missing)}."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do=(
                "Each quote binding needs capture_id (int), locator (string), "
                "and quoted_text (exact substring). Prefer find_quote to obtain the locator."
            ),
        )
    try:
        capture_id = int(item["capture_id"])
    except (TypeError, ValueError):
        raise DeskRefusal(
            code="QUOTE_BINDING_FIELD_MISSING",
            what_happened=(
                f"quote_bindings[{index}].capture_id is not an integer "
                f"(got {item['capture_id']!r})."
            ),
            what_was_preserved="No claim was written.",
            what_was_not_changed="The Record is unchanged.",
            what_you_can_do="Use the integer capture_id from capture_url / read_capture.",
        ) from None
    return QuoteBindingInput(
        capture_id=capture_id,
        locator=str(item["locator"]),
        quoted_text=str(item["quoted_text"]),
    )


def build_mcp_server(engine: Engine, *, vault: VaultStore | None = None) -> MCPServer[Any]:
    """Create MCP server with executor tools only (no human-only ops)."""
    settings = get_settings()
    vault_store = vault or VaultStore(settings.vault_path)
    locator_cap = settings.locator_map_element_cap
    server = MCPServer(name="discrepancy-desk", version="0.1.0")

    @server.tool(
        name="claim_next_run",
        description=(
            "Claim the oldest approved research run (pull-only). Returns the work "
            "packet including claim_token, or null when idle. Present claim_token "
            "on every subsequent tool call for that claim."
        ),
    )
    @mcp_tool_boundary("claim_next_run")
    def claim_next_run_tool() -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = claim_next_run(conn, ClaimNextRunInput())
        return result.model_dump()

    @server.tool(
        name="read_case_context",
        description=(
            "Read case material and the run held by this claim_token: status, "
            "question, scope, rubric, capture budget/usage, claims made, and "
            "all suspension instances with operator answers. Use after resume "
            "or any refusal to learn current run state. Requires case_id and "
            "claim_token."
        ),
    )
    @mcp_tool_boundary("read_case_context")
    def read_case_context_tool(case_id: int, claim_token: str) -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = read_case_context(
                conn,
                ReadCaseContextInput(case_id=case_id, claim_token=claim_token),
            )
        return result.model_dump()

    @server.tool(
        name="capture_url",
        description=(
            "Fetch a URL through the backend Vault. Requires run_id, url, and "
            "claim_token from claim_next_run. Counts against the claimed run's "
            "capture budget."
        ),
    )
    @mcp_tool_boundary("capture_url")
    def capture_url_tool(run_id: int, url: str, claim_token: str) -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = capture_url(
                conn,
                CaptureUrlInput(run_id=run_id, url=url, claim_token=claim_token),
                vault=vault_store,
                locator_map_cap=locator_cap,
            )
        return result.model_dump()

    @server.tool(
        name="read_capture",
        description=(
            "Read further elements from a capture. Requires capture_id and "
            "claim_token for the run that owns the capture. Optional offset and "
            "limit paginate the element list."
        ),
    )
    @mcp_tool_boundary("read_capture")
    def read_capture_tool(
        capture_id: int,
        claim_token: str,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = read_capture(
                conn,
                ReadCaptureInput(
                    capture_id=capture_id,
                    claim_token=claim_token,
                    offset=offset,
                    limit=limit,
                ),
            )
        return result.model_dump()

    @server.tool(
        name="find_quote",
        description=(
            "Locate an exact substring inside a capture's element text and return "
            "the e/{n}/r/{start}-{end} locator (end exclusive). Requires "
            "capture_id, claim_token, and quoted_text. Exact match only — no fuzzy "
            "or normalised search. Returns found=true with locator when unique; "
            "found=false with reason not_found, multiple_elements, or "
            "multiple_in_element when the text is absent or appears more than once. "
            "Read-only: does not refresh the lease and does not consume budget. "
            "propose_claim still verifies the quote independently."
        ),
    )
    @mcp_tool_boundary("find_quote")
    def find_quote_tool(
        capture_id: int,
        claim_token: str,
        quoted_text: str,
    ) -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = find_quote(
                conn,
                FindQuoteInput(
                    capture_id=capture_id,
                    claim_token=claim_token,
                    quoted_text=quoted_text,
                ),
            )
        return result.model_dump()

    @server.tool(
        name="propose_claim",
        description=(
            "Propose an unconfirmed claim. Requires run_id, claim_token, proposition, "
            "and the dimension fields source_basis, corroboration, certainty, posture, "
            "publication_risk. Fails closed with distinct codes per verification step. "
            "Quote path needs capture_id, locator, and quoted_text (or quote_bindings "
            "objects with those same keys). Prefer find_quote to obtain the region "
            "locator. Optional qualification, cited_claim_ids for desk_inference."
        ),
    )
    @mcp_tool_boundary("propose_claim")
    def propose_claim_tool(
        run_id: int,
        claim_token: str,
        proposition: str,
        source_basis: str,
        corroboration: str,
        certainty: str,
        posture: str,
        publication_risk: str,
        qualification: str = "",
        capture_id: int | None = None,
        locator: str | None = None,
        quoted_text: str | None = None,
        quote_bindings: list[dict[str, Any]] | None = None,
        cited_claim_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        bindings = None
        if quote_bindings:
            bindings = [parse_quote_binding(b, index=i) for i, b in enumerate(quote_bindings)]
        params = ProposeClaimInput(
            run_id=run_id,
            claim_token=claim_token,
            proposition=proposition,
            dimensions=EvidenceDimensions(
                source_basis=source_basis,
                corroboration=corroboration,
                certainty=certainty,
                posture=posture,
                publication_risk=publication_risk,
            ),
            qualification=qualification,
            capture_id=capture_id,
            locator=locator,
            quoted_text=quoted_text,
            quote_bindings=bindings,
            cited_claim_ids=cited_claim_ids,
        )
        with connection_scope(engine) as conn:
            result = propose_claim(conn, params)
        return result.model_dump()

    @server.tool(
        name="propose_rendition",
        description=(
            "Propose a draft rendition for a chosen angle — ordered units "
            "written natively for the platform (destination: x/thread). "
            "Requires run_id, claim_token, angle_id, platform, format, and units. "
            "units is a list of objects with keys body (string) and claim_ids "
            "(list of integers). Each unit may cite only confirmed claims linked "
            "to that angle; required qualification language on a cited claim must "
            "appear in the unit body. Backend never generates text — the executor "
            "composes. Missing unit keys refuse with RENDITION_UNIT_FIELD_MISSING."
        ),
    )
    @mcp_tool_boundary("propose_rendition")
    def propose_rendition_tool(
        run_id: int,
        claim_token: str,
        angle_id: int,
        platform: str,
        format: str,
        units: list[dict[str, Any]],
    ) -> dict[str, Any]:
        unit_models = [parse_rendition_unit(u, index=i) for i, u in enumerate(units)]
        params = ProposeRenditionInput(
            run_id=run_id,
            claim_token=claim_token,
            angle_id=angle_id,
            platform=platform,
            format=format,
            units=unit_models,
        )
        with connection_scope(engine) as conn:
            result = propose_rendition(conn, params)
        return result.model_dump()

    @server.tool(
        name="suspend_run",
        description=(
            "Suspend a claimed run to ask the human mid-flight. Requires run_id, "
            "claim_token, question, uncertainty, and default_action (what you would "
            "do by default). Work tools refuse until the operator answers and the "
            "run returns to claimed."
        ),
    )
    @mcp_tool_boundary("suspend_run")
    def suspend_run_tool(
        run_id: int,
        claim_token: str,
        question: str,
        uncertainty: str,
        default_action: str,
    ) -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = suspend_run(
                conn,
                SuspendRunInput(
                    run_id=run_id,
                    claim_token=claim_token,
                    question=question,
                    uncertainty=uncertainty,
                    default_action=default_action,
                ),
            )
        return result.model_dump()

    @server.tool(
        name="close_run",
        description=(
            "Close a claimed run. Requires run_id and claim_token. Optionally "
            "propose new open questions as objects with keys text, rationale, and "
            "proposed_scope (scope is accepted as an alias for proposed_scope); "
            "report low_confidence_areas; list uncited capture ids you examined "
            "and found nothing worth claiming in examined_capture_ids (only those "
            "become examined; omit any you did not look at); set status complete. "
            "Missing keys refuse with OPEN_QUESTION_FIELD_MISSING — never a bare "
            "field name."
        ),
    )
    @mcp_tool_boundary("close_run")
    def close_run_tool(
        run_id: int,
        claim_token: str,
        proposed_questions: list[dict[str, Any]] | None = None,
        low_confidence_areas: list[str] | None = None,
        examined_capture_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        props = [
            parse_proposed_open_question(p, index=i) for i, p in enumerate(proposed_questions or [])
        ]
        with connection_scope(engine) as conn:
            result = close_run(
                conn,
                CloseRunInput(
                    run_id=run_id,
                    claim_token=claim_token,
                    proposed_questions=props,
                    low_confidence_areas=list(low_confidence_areas or []),
                    examined_capture_ids=list(examined_capture_ids or []),
                ),
            )
        return result.model_dump()

    @server.tool(
        name="add_lead",
        description=(
            "Park a URL in the lead inbox, unattached to any case. Captures "
            "immediately via the same Vault path as capture_url. Use for material "
            "outside this run's question — do not capture against the wrong run. "
            "Requires run_id, url, and claim_token from claim_next_run (lease "
            "refreshed); optional note. Does not consume the run capture_budget. "
            "Auth-walled URLs become identity-only leads (not captured). Holds "
            "material only; never creates claims."
        ),
    )
    @mcp_tool_boundary("add_lead")
    def add_lead_tool(
        run_id: int,
        url: str,
        claim_token: str,
        note: str = "",
    ) -> dict[str, Any]:
        with connection_scope(engine) as conn:
            result = add_lead(
                conn,
                AddLeadInput(
                    url=url,
                    note=note,
                    run_id=run_id,
                    claim_token=claim_token,
                ),
                vault=vault_store,
                locator_map_cap=locator_cap,
            )
        return result.model_dump()

    registered = {t.name for t in server._tool_manager.list_tools()}  # noqa: SLF001
    expected = set(mcp_tool_names())
    if registered != expected:
        raise RuntimeError(
            f"MCP tool registration mismatch: registered={sorted(registered)} "
            f"expected={sorted(expected)}"
        )

    # After registration: convert validation escapes at the one dispatch point.
    # Schema validation still runs inside Tool.run; this only reshapes what leaves.
    install_tool_dispatch_envelope(server)

    return server
