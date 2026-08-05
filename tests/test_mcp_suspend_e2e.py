"""E2E: executor suspends → operator answers over HTTP → executor reads answer via MCP."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient
from mcp import Client
from sqlalchemy import Engine

from desk.app import create_app
from desk.config import Settings
from desk.db.session import connection_scope
from desk.service import approve_run, create_case, create_run
from desk.service.models import ApproveRunInput, CreateCaseInput, CreateRunInput
from desk.transports import api as api_transport
from desk.transports.wiring import mcp_tool_names


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_app(db_path: Path, engine: Engine) -> Iterator[tuple[str, TestClient, Engine]]:
    settings = Settings(database_path=db_path, vault_path=db_path.parent / "vault")
    app = create_app(settings=settings, engine=engine, run_migrations=False)

    def _engine() -> Engine:
        return engine

    app.dependency_overrides[api_transport.get_engine] = _engine

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
        case = create_case(conn, CreateCaseInput(title="E2E suspend case"))
        run = create_run(
            conn,
            CreateRunInput(
                case_id=case.case_id,
                question="E2E research question?",
                scope="E2E scope",
            ),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))

    http = TestClient(app)
    try:
        yield f"http://127.0.0.1:{port}/mcp", http, engine
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_mcp_suspend_http_answer_mcp_read(
    live_app: tuple[str, TestClient, Engine],
) -> None:
    mcp_url, http, _engine = live_app

    async with Client(mcp_url) as client:
        listed = await client.list_tools()
        names = {t.name for t in listed.tools}
        assert names == set(mcp_tool_names())
        assert "read_case_context" in names
        assert "suspend_run" in names
        assert "cancel_run" not in names

        claimed = await client.call_tool("claim_next_run", {})
        assert claimed.is_error is False
        packet = (claimed.structured_content or {}).get("run")
        assert packet is not None
        run_id = packet["run_id"]
        case_id = packet["case_id"]
        token = packet["claim_token"]

        suspended = await client.call_tool(
            "suspend_run",
            {
                "run_id": run_id,
                "claim_token": token,
                "question": "Is source A the same agency as source B?",
                "uncertainty": "Renamed unit vs unrelated agencies",
                "default_action": "Treat as unrelated",
            },
        )
        assert suspended.is_error is False
        sus_body = suspended.structured_content or {}
        assert sus_body["status"] == "suspended"
        assert sus_body["instance_vs_class_notice"]

        # Operator answers over HTTP (human transport).
        answer_text = "Same agency under a later name; treat as one lineage."
        answered = http.post(
            f"/api/runs/{run_id}/answer-suspension",
            json={"answer": answer_text},
        )
        assert answered.status_code == 200
        assert answered.json()["status"] == "claimed"
        assert answered.json()["human_answer"] == answer_text

        # Same active executor reads the exact answer through MCP.
        ctx = await client.call_tool(
            "read_case_context",
            {"case_id": case_id, "claim_token": token},
        )
        assert ctx.is_error is False
        data = ctx.structured_content or {}
        held = data["held_run"]
        assert held["run_id"] == run_id
        assert held["status"] == "claimed"
        assert held["current_suspension"] is not None
        assert held["current_suspension"]["human_answer"] == answer_text
        assert held["current_suspension"]["question"] == (
            "Is source A the same agency as source B?"
        )
        assert len(held["suspensions"]) == 1
        assert held["suspensions"][0]["human_answer"] == answer_text
