"""End-to-end MCP transport tests for claim_next_run."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from mcp import Client
from sqlalchemy import Engine

from desk.app import create_app
from desk.config import Settings
from desk.db.session import connection_scope
from desk.service import approve_run, create_case, create_run
from desk.service.models import ApproveRunInput, CreateCaseInput, CreateRunInput
from desk.transports.wiring import API_ONLY, mcp_tool_names


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def mcp_server_url(db_path: Path, engine: Engine) -> Iterator[str]:
    settings = Settings(database_path=db_path, vault_path=db_path.parent / "vault")
    app = create_app(settings=settings, engine=engine, run_migrations=False)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while time.time() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("uvicorn did not start in time")

    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="MCP case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="MCP question?",
                scope="MCP scope",
                coverage_dimension="official_foundation",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))

    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_mcp_lists_only_claim_next_run(mcp_server_url: str) -> None:
    async with Client(mcp_server_url) as client:
        listed = await client.list_tools()
        names = {t.name for t in listed.tools}
        assert names == set(mcp_tool_names())
        assert "claim_next_run" in names
        assert "capture_url" in names
        assert "read_capture" in names
        # Human dispatch must never appear on the tool surface.
        for name in ("create_run", "approve_run", "create_case"):
            assert name not in names
        # D18: add_lead is MCP_AND_API (not API_ONLY). All other API-only ops stay off MCP.
        assert "add_lead" in names
        assert names.isdisjoint(API_ONLY)


@pytest.mark.asyncio
async def test_mcp_claim_next_run_round_trip(mcp_server_url: str) -> None:
    async with Client(mcp_server_url) as client:
        result = await client.call_tool("claim_next_run", {})
        assert result.is_error is False
        data = result.structured_content or {}
        packet = data.get("run")
        assert packet is not None
        assert packet["status"] == "claimed"
        assert packet["question"] == "MCP question?"
        assert packet["scope"] == "MCP scope"
        assert packet["rubric_version"]
        assert packet["rubric_text"]

        idle = await client.call_tool("claim_next_run", {})
        assert idle.is_error is False
        idle_data = idle.structured_content or {}
        assert idle_data.get("run") is None


def test_probe_ops_removed_from_wiring() -> None:
    for name in (
        "ensure_probe_parent",
        "record_probe_note",
        "list_probe_notes",
    ):
        assert name not in mcp_tool_names()
        assert name not in API_ONLY
