"""
Database configuration module.

Loads database settings from environment variables and provides
connection URLs for both async and sync operations.
"""

import os
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database configuration loaded from environment variables."""

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "solver"
    db_password: str = "solver123"
    db_name: str = "solver_db"

    # Connection timeout in seconds (shared by app and scripts)
    db_connect_timeout: int = 10

    # Optional: override full URL
    database_url: str | None = None
    database_url_sync: str | None = None

    @field_validator("db_port", "db_connect_timeout", mode="before")
    @classmethod
    def _validate_plain_int(cls, value: Any, info: Any) -> Any:
        if isinstance(value, dict):
            raise ValueError(
                f"{info.field_name.upper()} must be a plain integer, not a dict. "
                "Check .env and Windows environment variables."
            )
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def async_url(self) -> str:
        """Get async database URL (for asyncpg)."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def sync_url(self) -> str:
        """Get sync database URL (for psycopg v3, used by Alembic)."""
        if self.database_url_sync:
            return self.database_url_sync
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            f"?connect_timeout={self.db_connect_timeout}"
        )


@lru_cache
def get_db_settings() -> DatabaseSettings:
    """Get cached database settings instance."""
    return DatabaseSettings()


# Convenience exports
db_settings = get_db_settings()
