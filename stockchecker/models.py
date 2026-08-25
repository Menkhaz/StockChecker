from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    COMING_SOON = "coming_soon"
    UNKNOWN = "unknown"

    @property
    def purchasable(self) -> bool:
        return self in {self.IN_STOCK, self.LOW_STOCK, self.PREORDER}

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    url: str
    retailer: str
    product_id: str
    name: str
    availability: Availability
    price: Decimal | None
    currency: str | None


@dataclass(frozen=True, slots=True)
class Subscription:
    user_id: int
    product_url: str
    max_price: Decimal | None
