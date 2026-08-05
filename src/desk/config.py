"""Runtime configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = _REPO_ROOT / "data" / "desk.db"
_DEFAULT_VAULT = _REPO_ROOT / "data" / "vault"


class Settings(BaseSettings):
    """Env-overridable settings for the Desk process."""

    model_config = SettingsConfigDict(env_prefix="DESK_", extra="ignore")

    database_path: Path = Field(default=_DEFAULT_DB)
    vault_path: Path = Field(default=_DEFAULT_VAULT)
    host: str = "127.0.0.1"
    port: int = 8000
    # Max elements returned in capture_url locator map before read_capture.
    locator_map_element_cap: int = 50
    default_capture_budget: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear cached settings (tests)."""
    get_settings.cache_clear()
