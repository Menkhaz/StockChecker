from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from stockchecker.commands import TEST_NOTIFICATION, StockCommands
from stockchecker.models import Availability, ProductSnapshot
from stockchecker.notifications import format_stock_notification


def test_format_stock_notification() -> None:
    snapshot = ProductSnapshot(
        url="https://example.com/product",
        retailer="Example",
        product_id="123",
        name="Example Product",
        availability=Availability.IN_STOCK,
        price=Decimal("12.50"),
        currency="USD",
    )

    assert format_stock_notification(snapshot) == (
        "**Example Product** is **In Stock** at USD 12.50.\n"
        "https://example.com/product"
    )


@pytest.mark.asyncio
async def test_test_notification_dms_invoking_user_without_database_access() -> None:
    database = Mock()
    interaction = Mock()
    interaction.user.send = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    cog = StockCommands(Mock(), database, Mock(), Mock())

    await StockCommands.test_notification.callback(cog, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.user.send.assert_awaited_once_with(format_stock_notification(TEST_NOTIFICATION))
    interaction.followup.send.assert_awaited_once_with(
        "Test restock notification sent by DM. No subscription data was changed.",
        ephemeral=True,
    )
    assert database.mock_calls == []


def test_test_notification_requires_administrator_permission() -> None:
    permissions = StockCommands.test_notification.default_permissions

    assert permissions is not None
    assert permissions.administrator
