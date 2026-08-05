"""Render DeskRefusal as HTTP JSON without leaking internals."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from desk.refusals import DeskRefusal

# Domain refusals are conflicts with the current Record state, not request-shape errors.
REFUSAL_HTTP_STATUS = 409


def refusal_response(refusal: DeskRefusal) -> JSONResponse:
    return JSONResponse(
        status_code=REFUSAL_HTTP_STATUS,
        content={"refusal": refusal.as_dict()},
    )


async def desk_refusal_handler(_request: Request, exc: DeskRefusal) -> JSONResponse:
    return refusal_response(exc)
