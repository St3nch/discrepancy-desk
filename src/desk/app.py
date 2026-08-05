"""ASGI application: FastAPI `/api` + mounted MCP `/mcp` over one service layer."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.types import ASGIApp

from desk.config import Settings, get_settings
from desk.db.engine import create_db_engine
from desk.refusals import DeskRefusal
from desk.transports import api as api_transport
from desk.transports.api import router as api_router
from desk.transports.mcp_tools import build_mcp_server
from desk.transports.refusal_http import desk_refusal_handler
from desk.vault.store import VaultStore


def _run_migrations(database_path: Path) -> None:
    """Apply Alembic migrations to the configured database file."""
    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.resolve()}")
    command.upgrade(cfg, "head")


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    run_migrations: bool = True,
) -> FastAPI:
    """Compose the dual-transport application."""
    settings = settings or get_settings()
    if run_migrations:
        _run_migrations(settings.database_path)
    db_engine = engine or create_db_engine(settings.database_path)
    vault = VaultStore(settings.vault_path)

    mcp_server = build_mcp_server(db_engine, vault=vault)

    # Mounted at `/mcp`; sub-app path is `/` so the external URL is `/mcp`.
    # The streamable HTTP session manager requires its lifespan (`run()`) to start.
    mcp_starlette = mcp_server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
    )
    mcp_asgi: ASGIApp = mcp_starlette

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Parent must enter the MCP Starlette lifespan so the session task group starts.
        async with mcp_starlette.router.lifespan_context(mcp_starlette):
            yield
        db_engine.dispose()

    app = FastAPI(title="Discrepancy Desk", version="0.1.0", lifespan=lifespan)
    app.state.engine = db_engine
    app.state.settings = settings
    app.state.vault = vault

    def engine_dep() -> Engine:
        return db_engine

    app.dependency_overrides[api_transport.get_engine] = engine_dep
    app.add_exception_handler(DeskRefusal, desk_refusal_handler)  # type: ignore[arg-type]
    app.include_router(api_router, prefix="/api")
    app.mount("/mcp", mcp_asgi)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def main() -> None:
    """CLI entry: run uvicorn against the default app."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "desk.app:app",
        host=settings.host,
        port=settings.port,
        factory=False,
        reload=False,
    )


# Module-level app for `uvicorn desk.app:app`. Built lazily via factory pattern
# for tests; production uses create_app at import for simple run commands.
def _lazy_app() -> FastAPI:
    return create_app()


class _AppProxy:
    """Delay create_app until first ASGI call so tests can import without side effects."""

    def __init__(self) -> None:
        self._app: FastAPI | None = None

    def _ensure(self) -> FastAPI:
        if self._app is None:
            self._app = create_app()
        return self._app

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        await self._ensure()(scope, receive, send)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ensure(), name)


app: Any = _AppProxy()
