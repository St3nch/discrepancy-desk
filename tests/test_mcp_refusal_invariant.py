"""Ticket 12a — MCP tool boundary is a three-category refusal invariant.

1. DeskRefusal — five-field envelope, domain code unchanged.
2. Framework argument validation — TOOL_ARGUMENT_INVALID (correctable).
3. Unexpected — TOOL_INTERNAL_ERROR (non-correctable, logged).

Tests go through ToolManager.call_tool (the registered dispatch path), not
tool.fn — calling the body directly bypasses schema validation and cannot
establish the ticket's claim.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import create_engine

from desk.refusals import DeskRefusal
from desk.transports.mcp_tools import build_mcp_server
from desk.transports.refusal_mcp import TOOL_ARGUMENT_INVALID, TOOL_INTERNAL_ERROR
from desk.transports.wiring import mcp_tool_names
from desk.vault.store import VaultStore

# Nested dict keys that free-form schema items accept — description must name them.
NESTED_DESCRIPTION_KEYS: dict[str, frozenset[str]] = {
    "close_run": frozenset({"text", "rationale", "proposed_scope"}),
    "propose_rendition": frozenset({"body", "claim_ids"}),
    "propose_claim": frozenset({"capture_id", "locator", "quoted_text", "quote_bindings"}),
    "find_quote": frozenset({"capture_id", "claim_token", "quoted_text"}),
}

REFUSAL_FIELDS = (
    "code",
    "what_happened",
    "what_was_preserved",
    "what_was_not_changed",
    "what_you_can_do",
)


def _server(tmp_path: Path) -> Any:
    return build_mcp_server(
        create_engine("sqlite://"),
        vault=VaultStore(tmp_path / "vault"),
    )


def _tools(server: Any) -> dict[str, Any]:
    return {t.name: t for t in server._tool_manager.list_tools()}  # noqa: SLF001


def _parse_refusal(exc: ToolError) -> dict[str, str]:
    payload = json.loads(str(exc))
    assert "refusal" in payload, f"missing refusal envelope: {exc!s}"
    refusal = payload["refusal"]
    for field in REFUSAL_FIELDS:
        assert field in refusal, f"missing {field} in {refusal}"
        assert isinstance(refusal[field], str) and refusal[field], field
    return refusal


async def _dispatch(server: Any, name: str, arguments: dict[str, Any]) -> Any:
    """Call through the real registered path (validation + dispatch envelope)."""
    return await server._tool_manager.call_tool(name, arguments, Context())  # noqa: SLF001


# --- Registration ------------------------------------------------------------


def test_every_registered_tool_is_listed(tmp_path: Path) -> None:
    server = _server(tmp_path)
    assert set(_tools(server)) == set(mcp_tool_names())
    assert set(mcp_tool_names()) == {
        "claim_next_run",
        "read_case_context",
        "capture_url",
        "read_capture",
        "find_quote",
        "propose_claim",
        "propose_rendition",
        "suspend_run",
        "close_run",
        "add_lead",
    }


# --- Framework arg validation (category 2) via real dispatch -----------------


@pytest.mark.asyncio
async def test_malformed_payloads_always_return_refusal_envelope(tmp_path: Path) -> None:
    """Missing / wrong-type / null top-level args → five-field envelope.

    Goes through ToolManager.call_tool so MCP schema validation actually runs.
    This is the test that fails if the intercept sits only on the body decorator.
    """
    server = _server(tmp_path)
    tools = _tools(server)

    # (tool_name, arguments, expected substrings in what_happened)
    cases: list[tuple[str, dict[str, Any], tuple[str, ...]]] = [
        # missing required
        ("read_case_context", {}, ("case_id", "claim_token")),
        ("capture_url", {}, ("run_id",)),
        ("read_capture", {}, ("capture_id",)),
        ("find_quote", {}, ("capture_id", "quoted_text")),
        ("propose_claim", {}, ("run_id", "proposition")),
        ("propose_rendition", {}, ("units", "angle_id")),
        ("suspend_run", {}, ("question", "uncertainty")),
        ("close_run", {}, ("run_id", "claim_token")),
        ("add_lead", {}, ("url", "run_id")),
        # wrong types
        (
            "read_case_context",
            {"case_id": "not-an-int", "claim_token": "t"},
            ("case_id",),
        ),
        (
            "capture_url",
            {"run_id": "x", "url": "https://example.com", "claim_token": "t"},
            ("run_id",),
        ),
        (
            "find_quote",
            {"capture_id": "nope", "claim_token": "t", "quoted_text": "hi"},
            ("capture_id",),
        ),
        (
            "close_run",
            {"run_id": "not-int", "claim_token": "t"},
            ("run_id",),
        ),
        (
            "propose_rendition",
            {
                "run_id": 1,
                "claim_token": "t",
                "angle_id": 1,
                "platform": "x",
                "format": "thread",
                "units": "not-a-list",
            },
            ("units",),
        ),
        # nulls where values are required
        (
            "read_capture",
            {"capture_id": None, "claim_token": "t"},
            ("capture_id",),
        ),
        (
            "close_run",
            {"run_id": 1, "claim_token": None},
            ("claim_token",),
        ),
        (
            "add_lead",
            {"run_id": None, "url": "https://example.com", "claim_token": "t"},
            ("run_id",),
        ),
        (
            "suspend_run",
            {
                "run_id": 1,
                "claim_token": "t",
                "question": None,
                "uncertainty": "u",
                "default_action": "d",
            },
            ("question",),
        ),
        # empty string where an int is required (wrong type at the framework)
        (
            "find_quote",
            {"capture_id": "", "claim_token": "t", "quoted_text": "hi"},
            ("capture_id",),
        ),
        (
            "propose_claim",
            {
                "run_id": "",
                "claim_token": "t",
                "proposition": "p",
                "source_basis": "contemporaneous_report",
                "corroboration": "single_source",
                "certainty": "probable",
                "posture": "factual_assertion",
                "publication_risk": "not_applicable",
            },
            ("run_id",),
        ),
    ]

    covered = {name for name, _, _ in cases}
    # claim_next_run has no parameters — covered by idle success + internal-error tests.
    assert covered | {"claim_next_run"} == set(tools)

    for name, arguments, expected_names in cases:
        with pytest.raises(ToolError) as ei:
            await _dispatch(server, name, arguments)
        refusal = _parse_refusal(ei.value)
        assert refusal["code"] == TOOL_ARGUMENT_INVALID, (
            f"{name} {arguments!r} → {refusal['code']}: {refusal['what_happened']}"
        )
        happened = refusal["what_happened"]
        for fragment in expected_names:
            assert fragment in happened, f"{name}: expected {fragment!r} in {happened!r}"
        # Correctable — must not tell the executor to stop retrying.
        assert "not correctable" not in refusal["what_you_can_do"].lower()
        assert "retry" in refusal["what_you_can_do"].lower()


@pytest.mark.asyncio
async def test_empty_string_quoted_text_is_domain_not_argument_invalid(
    tmp_path: Path,
) -> None:
    """Empty string is a valid str at the schema; domain refuses FIND_QUOTE_EMPTY."""
    server = _server(tmp_path)
    with pytest.raises(ToolError) as ei:
        await _dispatch(
            server,
            "find_quote",
            {"capture_id": 1, "claim_token": "t", "quoted_text": ""},
        )
    refusal = _parse_refusal(ei.value)
    assert refusal["code"] == "FIND_QUOTE_EMPTY"
    assert refusal["code"] != TOOL_ARGUMENT_INVALID
    assert refusal["code"] != TOOL_INTERNAL_ERROR


@pytest.mark.asyncio
async def test_nested_missing_keys_still_domain_via_dispatch(tmp_path: Path) -> None:
    """F-54: missing proposed_scope is OPEN_QUESTION_FIELD_MISSING through dispatch."""
    server = _server(tmp_path)
    with pytest.raises(ToolError) as ei:
        await _dispatch(
            server,
            "close_run",
            {
                "run_id": 1,
                "claim_token": "x",
                "proposed_questions": [{"text": "t", "rationale": "r"}],
            },
        )
    refusal = _parse_refusal(ei.value)
    assert refusal["code"] == "OPEN_QUESTION_FIELD_MISSING"
    assert "proposed_scope" in refusal["what_happened"]


# --- Domain pass-through (category 1) ----------------------------------------


@pytest.mark.asyncio
async def test_desk_refusal_passes_through_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from desk.transports import mcp_tools as mcp_mod

    def domain(*_a: Any, **_k: Any) -> Any:
        raise DeskRefusal(
            code="CAPTURE_NOT_FOUND",
            what_happened="No capture exists with id 99999.",
            what_was_preserved="Existing captures are unchanged.",
            what_was_not_changed="Nothing was written.",
            what_you_can_do="Call capture_url first.",
        )

    monkeypatch.setattr(mcp_mod, "read_capture", domain)
    server = _server(tmp_path)
    with pytest.raises(ToolError) as ei:
        await _dispatch(
            server,
            "read_capture",
            {"capture_id": 99999, "claim_token": "x"},
        )
    refusal = _parse_refusal(ei.value)
    assert refusal["code"] == "CAPTURE_NOT_FOUND"
    assert "capture_url" in refusal["what_you_can_do"]


@pytest.mark.asyncio
async def test_unexpected_does_not_swallow_desk_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CAPTURE_URL_BLOCKED must not become TOOL_INTERNAL_ERROR (F-17 shape)."""
    from desk.transports import mcp_tools as mcp_mod

    def blocked(*_a: Any, **_k: Any) -> Any:
        raise DeskRefusal(
            code="CAPTURE_URL_BLOCKED",
            what_happened="blocked",
            what_was_preserved="nothing fetched",
            what_was_not_changed="budget unchanged",
            what_you_can_do="pick another URL",
        )

    monkeypatch.setattr(mcp_mod, "capture_url", blocked)
    server = _server(tmp_path)
    with pytest.raises(ToolError) as ei:
        await _dispatch(
            server,
            "capture_url",
            {"run_id": 1, "url": "https://example.com", "claim_token": "t"},
        )
    refusal = _parse_refusal(ei.value)
    assert refusal["code"] == "CAPTURE_URL_BLOCKED"
    assert "pick another URL" in refusal["what_you_can_do"]


# --- Unexpected (category 3) -------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_exception_is_non_correctable_and_logged(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from desk.transports import mcp_tools as mcp_mod

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("simulated adapter bug with secret path /tmp/xyz")

    monkeypatch.setattr(mcp_mod, "claim_next_run", boom)
    server = _server(tmp_path)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ToolError) as ei:
            await _dispatch(server, "claim_next_run", {})

    refusal = _parse_refusal(ei.value)
    assert refusal["code"] == TOOL_INTERNAL_ERROR
    assert "not correctable" in refusal["what_you_can_do"].lower()
    assert "RuntimeError" not in refusal["what_happened"]
    assert "secret" not in refusal["what_happened"]
    assert "/tmp/xyz" not in refusal["what_happened"]
    assert any("claim_next_run" in rec.message for rec in caplog.records), [
        r.message for r in caplog.records
    ]


@pytest.mark.asyncio
async def test_claim_next_run_success_through_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No-arg tool: a valid empty call still succeeds through the dispatch wrap."""
    from desk.service.models import ClaimNextRunResult
    from desk.transports import mcp_tools as mcp_mod

    def idle(*_a: Any, **_k: Any) -> ClaimNextRunResult:
        return ClaimNextRunResult(run=None)

    monkeypatch.setattr(mcp_mod, "claim_next_run", idle)
    server = _server(tmp_path)
    result = await _dispatch(server, "claim_next_run", {})
    # convert_result=False on manager → raw dict from tool body
    assert result == {"run": None}


# --- Description / schema agreement ------------------------------------------


def test_tool_descriptions_agree_with_accepted_schemas(tmp_path: Path) -> None:
    """Two artifacts describing one contract must agree (F-51 / F-54 / F-58 class)."""
    server = _server(tmp_path)
    tools = _tools(server)
    assert set(tools) == set(mcp_tool_names())

    for name, tool in tools.items():
        schema = tool.parameters
        assert isinstance(schema, dict), name
        required = schema.get("required") or []
        props = schema.get("properties") or {}
        desc = (tool.description or "").lower()

        for key in required:
            assert key in props, f"{name}: required {key} missing from properties"
            if required:
                assert key.lower() in desc or key.replace("_", " ") in desc, (
                    f"{name}: required param {key!r} not mentioned in description"
                )

        for nested in NESTED_DESCRIPTION_KEYS.get(name, frozenset()):
            assert nested.lower() in desc, (
                f"{name}: nested/contract key {nested!r} not mentioned in description"
            )


def test_find_quote_in_mcp_registration(tmp_path: Path) -> None:
    server = _server(tmp_path)
    tools = _tools(server)
    assert "find_quote" in tools
    assert "find_quote" in mcp_tool_names()
    props = tools["find_quote"].parameters["properties"]
    assert set(props) == {"capture_id", "claim_token", "quoted_text"}


def test_dispatch_envelope_installed(tmp_path: Path) -> None:
    """build_mcp_server must install the dispatch wrapper (not body-only)."""
    server = _server(tmp_path)
    # The installed wrapper is a local function, not ToolManager.call_tool unbound.
    assert server._tool_manager.call_tool.__name__ == "call_tool"  # noqa: SLF001
    assert "install_tool_dispatch_envelope" in (
        server._tool_manager.call_tool.__module__  # noqa: SLF001
        or ""
    ) or server._tool_manager.call_tool.__qualname__ == (  # noqa: SLF001
        "install_tool_dispatch_envelope.<locals>.call_tool"
    )
