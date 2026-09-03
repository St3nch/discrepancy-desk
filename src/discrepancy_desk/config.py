"""Fail-closed runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from discrepancy_desk.errors import ConfigurationError, DecisionAuthorityError


def require_data_root(env: Mapping[str, str] | None = None) -> Path:
    values = os.environ if env is None else env
    raw = values.get("DESK_DATA_ROOT", "")
    if not raw:
        raise ConfigurationError("DESK_DATA_ROOT is required for Vault writes")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise ConfigurationError("DESK_DATA_ROOT must be an absolute path")
    if root.exists() and not root.is_dir():
        raise ConfigurationError("DESK_DATA_ROOT must name a directory")
    return root


def _require_postgres_url(name: str, env: Mapping[str, str]) -> str:
    raw = env.get(name, "")
    if not raw:
        raise ConfigurationError(f"{name} is required")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ConfigurationError(f"{name} must use a PostgreSQL URL")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ConfigurationError(f"{name} must identify a host and database")
    return raw


def require_database_url(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    return _require_postgres_url("DESK_POSTGRES_URL", values)


def require_admin_database_url(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    return _require_postgres_url("DESK_ADMIN_POSTGRES_URL", values)


def require_human_database_url(env: Mapping[str, str] | None = None) -> str:
    values = os.environ if env is None else env
    try:
        return _require_postgres_url("DESK_HUMAN_POSTGRES_URL", values)
    except ConfigurationError as exc:
        raise DecisionAuthorityError(
            "DESK_HUMAN_POSTGRES_URL is required; the Decision path never falls back"
        ) from exc
