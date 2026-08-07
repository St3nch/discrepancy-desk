"""Render DeskRefusal as an MCP tool error without leaking internals.

Ticket 12a: the tool boundary is a **three-category** invariant.

1. ``DeskRefusal`` — expected domain refusal, actionable, remedy stated.
   Pass through unchanged (body wrapper converts to the envelope).
2. Framework argument validation failure — correctable by the executor.
   ``TOOL_ARGUMENT_INVALID``: names the parameter and what was expected.
   Missing keys, wrong types, nulls. F-54 in a new costume if this stays
   unlearnable.
3. Anything genuinely unexpected — ``TOOL_INTERNAL_ERROR``, non-correctable,
   no internals leaked, loud in the logs. An executor must not loop trying to
   "fix" a programming error (F-17 one level up).

Schema validation still runs (loose types would cost the schema that teaches
parameter names). Failures are converted at **tool dispatch** on the way out,
so all registered tools share one intercept and the body wrapper is not the
only line of defence.
"""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable
from typing import Any, NoReturn, ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from desk.refusals import DeskRefusal

logger = logging.getLogger(__name__)

# Distinct from domain codes (QUOTE_MISMATCH, BUDGET_EXHAUSTED, …).
TOOL_INTERNAL_ERROR = "TOOL_INTERNAL_ERROR"
# Framework arg validation — actionable; executor should fix and retry.
TOOL_ARGUMENT_INVALID = "TOOL_ARGUMENT_INVALID"

P = ParamSpec("P")
R = TypeVar("R")


def raise_tool_refusal(refusal: DeskRefusal) -> NoReturn:
    """Raise ToolError carrying the five refusal fields, especially code."""
    payload = refusal.as_dict()
    # Structured JSON message keeps code machine-readable for executor self-correction.
    message = json.dumps({"refusal": payload}, separators=(",", ":"))
    # from None: do not chain internals into the client-visible exception.
    raise ToolError(message) from None


def is_refusal_envelope_message(message: str) -> bool:
    """True when ``message`` is our JSON ``{"refusal": {...}}`` payload."""
    try:
        data = json.loads(message)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict) or "refusal" not in data:
        return False
    refusal = data["refusal"]
    return isinstance(refusal, dict) and "code" in refusal


def unexpected_tool_refusal(*, tool_name: str) -> DeskRefusal:
    """Envelope for genuine programming/infrastructure failures.

    Deliberately non-actionable: no stack, no exception type, no retry recipe.
    """
    return DeskRefusal(
        code=TOOL_INTERNAL_ERROR,
        what_happened=(
            f"Tool {tool_name!r} failed with an unexpected internal error. "
            "This is not an actionable domain refusal."
        ),
        what_was_preserved="No successful result was produced for this call.",
        what_was_not_changed="The tool did not complete a governed write.",
        what_you_can_do=(
            "Do not retry with a different payload to correct this. "
            "This error is not correctable by the executor. "
            "Report the tool name and approximate time to the operator; "
            "details are in server logs only."
        ),
    )


def argument_invalid_refusal(
    *,
    tool_name: str,
    validation_error: ValidationError,
) -> DeskRefusal:
    """Envelope for MCP/Pydantic argument validation failures.

    Actionable: names each offending parameter and what was expected.
    """
    parts: list[str] = []
    for err in validation_error.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = str(err.get("msg", "invalid"))
        err_type = str(err.get("type", ""))
        if loc and err_type:
            parts.append(f"{loc}: {msg} (type={err_type})")
        elif loc:
            parts.append(f"{loc}: {msg}")
        else:
            parts.append(msg)
    detail = "; ".join(parts) if parts else "invalid arguments"
    return DeskRefusal(
        code=TOOL_ARGUMENT_INVALID,
        what_happened=(f"Tool {tool_name!r} received invalid arguments: {detail}"),
        what_was_preserved="No successful result was produced for this call.",
        what_was_not_changed="Nothing was written by a completed operation.",
        what_you_can_do=(
            f"Correct the arguments and retry {tool_name!r}. "
            f"Invalid: {detail}. "
            "Use the tool schema (required parameters and types) as the contract."
        ),
    )


def mcp_tool_boundary(tool_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Wrap one MCP tool **body** so domain and unexpected escapes are enveloped.

    Framework argument validation does not enter this wrapper — that is handled
    at dispatch (``install_tool_dispatch_envelope``). Together they cover the
    full tool boundary the ticket names.
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return fn(*args, **kwargs)
            except DeskRefusal as refusal:
                raise_tool_refusal(refusal)
            except ToolError:
                # Already a rendered tool error (should not come from our bodies).
                raise
            except Exception:
                logger.exception(
                    "Unexpected error escaping MCP tool %s (non-correctable)",
                    tool_name,
                )
                raise_tool_refusal(unexpected_tool_refusal(tool_name=tool_name))

        return wrapped

    return decorator


def _reraise_dispatch_tool_error(*, tool_name: str, error: ToolError) -> NoReturn:
    """Convert a ToolError leaving Tool.run into the three-category envelope.

    MCP's Tool.run wraps every exception as ``ToolError("Error executing tool
    …: {e}") from e``. Discriminate on ``__cause__``:

    * inner ToolError with our JSON envelope → re-raise clean (DeskRefusal or
      TOOL_INTERNAL_ERROR from the body wrapper)
    * pydantic ValidationError → TOOL_ARGUMENT_INVALID (correctable)
    * anything else → TOOL_INTERNAL_ERROR (non-correctable, logged)
    """
    cause = error.__cause__

    if isinstance(cause, ToolError) and is_refusal_envelope_message(str(cause)):
        # Body already rendered a five-field envelope; strip Tool.run's prefix.
        raise cause from None

    if isinstance(cause, ValidationError):
        raise_tool_refusal(argument_invalid_refusal(tool_name=tool_name, validation_error=cause))

    # Unknown-tool from ToolManager has no cause and is not our problem to rebrand.
    if cause is None and str(error).startswith("Unknown tool:"):
        raise error from None

    logger.exception(
        "Unexpected ToolError leaving MCP dispatch for %s (non-correctable)",
        tool_name,
        exc_info=error,
    )
    raise_tool_refusal(unexpected_tool_refusal(tool_name=tool_name))


def install_tool_dispatch_envelope(server: Any) -> None:
    """Intercept ToolManager.call_tool so validation failures leave as refusals.

    Schema validation still runs inside Tool.run (schemas stay intact). This
    only converts what escapes. One place covers every registered tool.
    """
    manager = server._tool_manager  # noqa: SLF001 — sole registration surface
    original_call_tool = manager.call_tool

    async def call_tool(
        name: str,
        arguments: dict[str, Any],
        context: Any,
        convert_result: bool = False,
    ) -> Any:
        try:
            return await original_call_tool(name, arguments, context, convert_result=convert_result)
        except ToolError as error:
            _reraise_dispatch_tool_error(tool_name=name, error=error)

    manager.call_tool = call_tool  # type: ignore[method-assign]
