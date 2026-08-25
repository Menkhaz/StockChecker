from __future__ import annotations

import asyncio
import logging
import random
from decimal import Decimal

import aiohttp
import discord

from stockchecker.checkers.base import ProductCheckError, UnsupportedWebsite
from stockchecker.checkers.registry import CheckerRegistry
from stockchecker.database import Database
from stockchecker.models import ProductSnapshot, Subscription

log = logging.getLogger(__name__)


class StockPoller:
    def __init__(self, bot: discord.Client, database: Database, registry: CheckerRegistry,
                 session: aiohttp.ClientSession, interval: int) -> None:
        self.bot = bot
        self.database = database
        self.registry = registry
        self.session = session
        self.interval = interval
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        await self.bot.wait_until_ready()
        log.info("Stock polling started")
        while not self._stopping.is_set():
            await self.poll_once()
            delay = self.interval * random.uniform(0.9, 1.1)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=delay)
            except TimeoutError:
                pass
        log.info("Stock polling stopped")

    async def poll_once(self) -> None:
        for url in await self.database.products():
            try:
                checker = self.registry.for_url(url)
                snapshot = await checker.check(self.session, url)
                previous = await self.database.latest(url)
                await self.database.observe(snapshot)
                if previous is not None and self._changed(previous, snapshot):
                    await self._notify(snapshot)
            except (ProductCheckError, UnsupportedWebsite) as exc:
                log.warning("Check failed for %s: %s", url, exc)
            except Exception:
                log.exception("Unexpected check failure for %s", url)

    @staticmethod
    def _changed(previous: ProductSnapshot, current: ProductSnapshot) -> bool:
        return previous.availability != current.availability or previous.price != current.price

    async def _notify(self, snapshot: ProductSnapshot) -> None:
        for subscription in await self.database.subscribers(snapshot.url):
            if not self._matches(subscription, snapshot):
                continue
            price = f"{snapshot.currency} {snapshot.price:.2f}" if snapshot.price is not None else "unknown price"
            message = (
                f"**{snapshot.name}** is **{snapshot.availability.label}** at {price}.\n"
                f"{snapshot.url}"
            )
            try:
                user = self.bot.get_user(subscription.user_id) or await self.bot.fetch_user(subscription.user_id)
                await user.send(message)
            except discord.Forbidden:
                log.warning("Cannot DM Discord user %s", subscription.user_id)
            except discord.HTTPException:
                log.exception("Discord notification failed for user %s", subscription.user_id)

    @staticmethod
    def _matches(subscription: Subscription, snapshot: ProductSnapshot) -> bool:
        if not snapshot.availability.purchasable:
            return True
        if subscription.max_price is None:
            return True
        price: Decimal | None = snapshot.price
        return price is not None and price <= subscription.max_price
