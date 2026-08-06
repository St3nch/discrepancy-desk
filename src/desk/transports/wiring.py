"""Explicit transport registration for governed operations."""

from __future__ import annotations

API_ONLY: frozenset[str] = frozenset(
    {
        "create_case",
        "list_cases",
        "get_case",
        "create_run",
        "approve_run",
        "list_runs",
        "answer_suspended_run",
        "cancel_run",
        "get_run_close",
        "decide_open_question",
        "create_operator_open_question",
        # Lead inbox after drop — editorial judgements (D18).
        "list_leads",
        "attach_lead",
        "promote_lead",
        "dispose_lead",
        "summarise_lead",
    }
)

# D18: first and only deliberate dual-surface entry. Dropping a URL commits
# nothing (material only, no case, no claims). Do not cite this as precedent
# for a second MCP_AND_API operation without the same scrutiny.
MCP_AND_API: frozenset[str] = frozenset(
    {
        "add_lead",
    }
)

MCP_ONLY: frozenset[str] = frozenset(
    {
        "claim_next_run",
        "read_case_context",
        "capture_url",
        "read_capture",
        "propose_claim",
        "suspend_run",
        "close_run",
    }
)


def mcp_tool_names() -> frozenset[str]:
    return MCP_AND_API | MCP_ONLY


def api_operation_names() -> frozenset[str]:
    return API_ONLY | MCP_AND_API
