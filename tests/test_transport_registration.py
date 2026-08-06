"""Bidirectional transport registration (closes F-03).

MCP already fails closed at startup when tools drift from mcp_tool_names().
Until ticket 10a, api_operation_names() had no call site — an API route could
appear for an unregistered name, or an API_ONLY entry could sit with no route,
and nothing would fail.

This module enforces both directions for the HTTP registry and keeps the MCP
check as a unit test (startup also runs it via build_mcp_server).
"""

from __future__ import annotations

from pathlib import Path

from desk.transports.api import router as api_router
from desk.transports.wiring import (
    API_ONLY,
    MCP_AND_API,
    MCP_ONLY,
    api_operation_names,
    mcp_tool_names,
)


def _api_route_names() -> set[str]:
    """Names declared on APIRouter routes (excludes unnamed utilities)."""
    names: set[str] = set()
    for route in api_router.routes:
        name = getattr(route, "name", None)
        if name and name != "http_exception":
            names.add(str(name))
    return names


def test_api_routes_match_api_operation_names_bidirectionally() -> None:
    """Every registered API route is in api_operation_names, and every name has a route.

    Failures name the offending operations — not just that counts differ (F-03).
    """
    routes = _api_route_names()
    registered = set(api_operation_names())

    on_router_not_registered = sorted(routes - registered)
    registered_without_route = sorted(registered - routes)

    assert not on_router_not_registered, (
        "API routes missing from api_operation_names() (add to wiring or remove "
        f"the route): {on_router_not_registered}"
    )
    assert not registered_without_route, (
        "api_operation_names() entries with no API route (add a route or remove "
        f"from wiring): {registered_without_route}"
    )


def test_mcp_and_api_only_partition() -> None:
    """Human-authority ops must not appear on MCP; dual-surface is explicit."""
    assert API_ONLY.isdisjoint(MCP_ONLY)
    assert MCP_AND_API <= api_operation_names()
    assert MCP_AND_API <= mcp_tool_names()
    # Human-only must never be MCP tools.
    assert API_ONLY.isdisjoint(mcp_tool_names())
    # MCP-only must never be pure API_ONLY.
    assert MCP_ONLY.isdisjoint(API_ONLY)


def test_mcp_tool_names_match_build_mcp_server(tmp_path: Path) -> None:
    """Same check build_mcp_server runs at startup — fail closed on drift."""
    from sqlalchemy import create_engine

    from desk.transports.mcp_tools import build_mcp_server
    from desk.vault.store import VaultStore

    engine = create_engine("sqlite://")
    # build_mcp_server raises RuntimeError if registration != mcp_tool_names().
    server = build_mcp_server(engine, vault=VaultStore(tmp_path / "vault"))
    registered = {t.name for t in server._tool_manager.list_tools()}  # noqa: SLF001
    assert registered == set(mcp_tool_names())
