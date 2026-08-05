"""MCP tool surface — only tools listed in wiring.mcp_tool_names()."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import Engine

from desk.config import get_settings
from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    capture_url,
    claim_next_run,
    propose_claim,
    read_capture,
    read_case_context,
    suspend_run,
)
from desk.service.models import (
    CaptureUrlInput,
    ClaimNextRunInput,
    EvidenceDimensions,
    ProposeClaimInput,
    QuoteBindingInput,
    ReadCaptureInput,
    ReadCaseContextInput,
    SuspendRunInput,
)
from desk.transports.refusal_mcp import raise_tool_refusal
from desk.transports.wiring import mcp_tool_names
from desk.vault.store import VaultStore


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
    def claim_next_run_tool() -> dict[str, Any]:
        try:
            with connection_scope(engine) as conn:
                result = claim_next_run(conn, ClaimNextRunInput())
            return result.model_dump()
        except DeskRefusal as refusal:
            raise_tool_refusal(refusal)

    @server.tool(
        name="read_case_context",
        description=(
            "Read case material and the run held by this claim_token: status, "
            "question, scope, rubric, capture budget/usage, claims made, and "
            "all suspension instances with operator answers. Use after resume "
            "or any refusal to learn current run state. Requires claim_token."
        ),
    )
    def read_case_context_tool(case_id: int, claim_token: str) -> dict[str, Any]:
        try:
            with connection_scope(engine) as conn:
                result = read_case_context(
                    conn,
                    ReadCaseContextInput(case_id=case_id, claim_token=claim_token),
                )
            return result.model_dump()
        except DeskRefusal as refusal:
            raise_tool_refusal(refusal)

    @server.tool(
        name="capture_url",
        description=(
            "Fetch a URL through the backend Vault. Requires claim_token from "
            "claim_next_run. Counts against the claimed run's capture budget."
        ),
    )
    def capture_url_tool(run_id: int, url: str, claim_token: str) -> dict[str, Any]:
        try:
            with connection_scope(engine) as conn:
                result = capture_url(
                    conn,
                    CaptureUrlInput(run_id=run_id, url=url, claim_token=claim_token),
                    vault=vault_store,
                    locator_map_cap=locator_cap,
                )
            return result.model_dump()
        except DeskRefusal as refusal:
            raise_tool_refusal(refusal)

    @server.tool(
        name="read_capture",
        description=(
            "Read further elements from a capture. Requires claim_token for the "
            "run that owns the capture."
        ),
    )
    def read_capture_tool(
        capture_id: int,
        claim_token: str,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        try:
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
        except DeskRefusal as refusal:
            raise_tool_refusal(refusal)

    @server.tool(
        name="propose_claim",
        description=(
            "Propose an unconfirmed claim. Requires claim_token from claim_next_run. "
            "Fails closed with distinct codes per verification step."
        ),
    )
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
        try:
            bindings = None
            if quote_bindings:
                bindings = [
                    QuoteBindingInput(
                        capture_id=int(b["capture_id"]),
                        locator=str(b["locator"]),
                        quoted_text=str(b["quoted_text"]),
                    )
                    for b in quote_bindings
                ]
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
        except DeskRefusal as refusal:
            raise_tool_refusal(refusal)

    @server.tool(
        name="suspend_run",
        description=(
            "Suspend a claimed run to ask the human mid-flight. State the "
            "question, what you are uncertain between, and what you would do "
            "by default. Requires claim_token. Work tools refuse until the "
            "operator answers and the run returns to claimed."
        ),
    )
    def suspend_run_tool(
        run_id: int,
        claim_token: str,
        question: str,
        uncertainty: str,
        default_action: str,
    ) -> dict[str, Any]:
        try:
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
        except DeskRefusal as refusal:
            raise_tool_refusal(refusal)

    registered = {t.name for t in server._tool_manager.list_tools()}  # noqa: SLF001
    expected = set(mcp_tool_names())
    if registered != expected:
        raise RuntimeError(
            f"MCP tool registration mismatch: registered={sorted(registered)} "
            f"expected={sorted(expected)}"
        )

    return server
