from __future__ import annotations

from decimal import Decimal, InvalidOperation

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from stockchecker.checkers.base import ProductCheckError, UnsupportedWebsite
from stockchecker.checkers.disney_store import DisneyStoreChecker
from stockchecker.checkers.registry import CheckerRegistry
from stockchecker.database import Database
from stockchecker.models import Availability, ProductSnapshot
from stockchecker.notifications import format_stock_notification

TEST_NOTIFICATION = ProductSnapshot(
    url="https://www.disneystore.com/",
    retailer="Disney Store",
    product_id="notification-test",
    name="StockChecker Test Product",
    availability=Availability.IN_STOCK,
    price=Decimal("39.99"),
    currency="USD",
)


class StockCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, database: Database, registry: CheckerRegistry,
                 session: aiohttp.ClientSession) -> None:
        self.bot = bot
        self.database = database
        self.registry = registry
        self.session = session

    @app_commands.command(name="subscribe", description="Monitor a product for stock and price changes")
    @app_commands.describe(
        url="Product page URL from a supported retailer",
        max_price="Optional maximum price in USD",
    )
    async def subscribe(self, interaction: discord.Interaction, url: str,
                        max_price: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            threshold = self._price(max_price)
            checker = self.registry.for_url(url.strip())
            snapshot = await checker.check(self.session, url.strip())
            await self.database.subscribe(interaction.user.id, snapshot, threshold)
            await self.database.observe(snapshot)
            price = f"{snapshot.currency} {snapshot.price:.2f}" if snapshot.price else "unknown price"
            limit = f" at or below USD {threshold:.2f}" if threshold is not None else ""
            await interaction.followup.send(
                f"Now monitoring **{snapshot.name}** ({snapshot.availability.label}, {price}){limit}.",
                ephemeral=True,
            )
        except (UnsupportedWebsite, ProductCheckError, ValueError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @app_commands.command(name="unsubscribe", description="Stop monitoring a product")
    @app_commands.describe(url="The product page URL used to subscribe")
    async def unsubscribe(self, interaction: discord.Interaction, url: str) -> None:
        try:
            canonical, _ = DisneyStoreChecker.canonicalize(url.strip())
            removed = await self.database.unsubscribe(interaction.user.id, canonical)
            message = "Subscription removed." if removed else "You were not subscribed to that product."
        except ProductCheckError as exc:
            message = str(exc)
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="subscriptions", description="List products you monitor")
    async def subscriptions(self, interaction: discord.Interaction) -> None:
        entries = await self.database.subscriptions_for_user(interaction.user.id)
        if not entries:
            await interaction.response.send_message("You have no subscriptions.", ephemeral=True)
            return
        lines = []
        for name, url, max_price in entries:
            limit = f" — max USD {Decimal(max_price):.2f}" if max_price else ""
            lines.append(f"• **{name}**{limit}\n  {url}")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @app_commands.command(name="status", description="Show whether StockChecker is operating")
    async def status(self, interaction: discord.Interaction) -> None:
        product_count = len(await self.database.products())
        await interaction.response.send_message(
            f"StockChecker is online and monitoring {product_count} product(s).", ephemeral=True
        )

    @app_commands.command(
        name="test-notification",
        description="Send yourself a sample restock notification",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def test_notification(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await interaction.user.send(format_stock_notification(TEST_NOTIFICATION))
        except discord.Forbidden:
            await interaction.followup.send(
                "I could not send you a DM. Allow direct messages from this server and try again.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "Discord could not deliver the test DM. Please try again shortly.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "Test restock notification sent by DM. No subscription data was changed.",
            ephemeral=True,
        )

    @staticmethod
    def _price(value: str | None) -> Decimal | None:
        if value is None or not value.strip():
            return None
        try:
            price = Decimal(value.strip().replace("$", "")).quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            raise ValueError("max_price must be a number such as 36.99") from exc
        if price <= 0:
            raise ValueError("max_price must be greater than zero")
        return price
