"""Render DeskRefusal as an MCP tool error without leaking internals."""

from __future__ import annotations

import json
from typing import NoReturn

from mcp.server.mcpserver.exceptions import ToolError

from desk.refusals import DeskRefusal


def raise_tool_refusal(refusal: DeskRefusal) -> NoReturn:
    """Raise ToolError carrying the five refusal fields, especially code."""
    payload = refusal.as_dict()
    # Structured JSON message keeps code machine-readable for executor self-correction.
    message = json.dumps({"refusal": payload}, separators=(",", ":"))
    raise ToolError(message) from None
