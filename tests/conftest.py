"""Shared fixtures: temp SQLite, migrations, engine, FastAPI client."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from desk.app import create_app
from desk.config import Settings, reset_settings_cache
from desk.db.engine import create_db_engine
from desk.transports import api as api_transport

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_upgrade(database_path: Path) -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.resolve()}")
    command.upgrade(cfg, "head")


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test.db"
    _alembic_upgrade(path)
    return path


@pytest.fixture()
def engine(db_path: Path) -> Iterator[Engine]:
    eng = create_db_engine(db_path)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture()
def client(db_path: Path, engine: Engine, tmp_path: Path) -> Iterator[TestClient]:
    reset_settings_cache()
    settings = Settings(database_path=db_path, vault_path=tmp_path / "vault")
    app = create_app(settings=settings, engine=engine, run_migrations=False)

    def _engine() -> Engine:
        return engine

    app.dependency_overrides[api_transport.get_engine] = _engine
    with TestClient(app) as test_client:
        yield test_client
