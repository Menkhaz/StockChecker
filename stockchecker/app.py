from __future__ import annotations

import asyncio
import logging

import aiohttp
import discord
from discord.ext import commands

from stockchecker.checkers.registry import CheckerRegistry
from stockchecker.commands import StockCommands
from stockchecker.config import Settings
from stockchecker.database import Database
from stockchecker.poller import StockPoller


class StockCheckerBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.none())
        self.settings = settings
        self.database = Database(settings.database_path)
        self.registry = CheckerRegistry()
        self.http_session: aiohttp.ClientSession | None = None
        self.poller: StockPoller | None = None
        self.poller_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        await self.database.initialize()
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout_seconds)
        self.http_session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.settings.user_agent, "Accept-Language": "en-US,en;q=0.9"},
        )
        await self.add_cog(StockCommands(self, self.database, self.registry, self.http_session))
        await self._sync_commands()
        self.poller = StockPoller(
            self, self.database, self.registry, self.http_session, self.settings.poll_seconds
        )
        self.poller_task = asyncio.create_task(self.poller.run(), name="stock-poller")

    async def _sync_commands(self) -> None:
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            # Guild commands appear immediately during development. Remove any
            # previously published global copies so Discord does not show both.
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        logging.getLogger(__name__).info("Connected to Discord as %s", self.user)

    async def close(self) -> None:
        if self.poller:
            self.poller.stop()
        if self.poller_task:
            try:
                await asyncio.wait_for(self.poller_task, timeout=10)
            except TimeoutError:
                self.poller_task.cancel()
        if self.http_session:
            await self.http_session.close()
        await super().close()


async def run() -> None:
    settings = Settings.load()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = StockCheckerBot(settings)
    async with bot:
        await bot.start(settings.discord_token)
