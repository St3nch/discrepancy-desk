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
    }
)

MCP_AND_API: frozenset[str] = frozenset()

MCP_ONLY: frozenset[str] = frozenset(
    {
        "claim_next_run",
        "capture_url",
        "read_capture",
        "propose_claim",
    }
)


def mcp_tool_names() -> frozenset[str]:
    return MCP_AND_API | MCP_ONLY


def api_operation_names() -> frozenset[str]:
    return API_ONLY | MCP_AND_API
