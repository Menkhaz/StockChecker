from pathlib import Path
from unittest.mock import AsyncMock, Mock, call

import pytest

from stockchecker.app import StockCheckerBot
from stockchecker.config import Settings


def settings(guild_id: int | None) -> Settings:
    return Settings(
        discord_token="test-token",
        discord_guild_id=guild_id,
        database_path=Path("test.db"),
        poll_seconds=180,
        request_timeout_seconds=30,
        user_agent="StockChecker tests",
        log_level="INFO",
    )


@pytest.mark.asyncio
async def test_guild_sync_removes_stale_global_commands() -> None:
    bot = StockCheckerBot(settings(1234))
    bot._BotBase__tree = Mock()
    bot.tree.sync = AsyncMock()

    await bot._sync_commands()

    guild = bot.tree.copy_global_to.call_args.kwargs["guild"]
    assert guild.id == 1234
    bot.tree.sync.assert_has_awaits([call(guild=guild), call()])
    bot.tree.clear_commands.assert_called_once_with(guild=None)


@pytest.mark.asyncio
async def test_global_sync_does_not_clear_commands() -> None:
    bot = StockCheckerBot(settings(None))
    bot._BotBase__tree = Mock()
    bot.tree.sync = AsyncMock()

    await bot._sync_commands()

    bot.tree.sync.assert_awaited_once_with()
    bot.tree.copy_global_to.assert_not_called()
    bot.tree.clear_commands.assert_not_called()
