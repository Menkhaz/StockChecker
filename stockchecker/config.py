from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    pass


def _integer(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None
    database_path: Path
    poll_seconds: int
    request_timeout_seconds: int
    user_agent: str
    log_level: str

    @classmethod
    def load(cls) -> Settings:
        load_dotenv()
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token or token == "replace-me":
            raise ConfigurationError("DISCORD_TOKEN is required")
        guild_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
        try:
            guild_id = int(guild_raw) if guild_raw else None
        except ValueError as exc:
            raise ConfigurationError("DISCORD_GUILD_ID must be a Discord numeric ID") from exc
        database_path = Path(os.getenv("DB_PATH", "./data/stockchecker.db")).expanduser()
        return cls(
            discord_token=token,
            discord_guild_id=guild_id,
            database_path=database_path,
            poll_seconds=_integer("POLL_SECONDS", 180, 60),
            request_timeout_seconds=_integer("REQUEST_TIMEOUT_SECONDS", 30, 5),
            user_agent=os.getenv("HTTP_USER_AGENT", "StockChecker/2.0").strip(),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
