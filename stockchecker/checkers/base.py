from __future__ import annotations

from abc import ABC, abstractmethod

import aiohttp

from stockchecker.models import ProductSnapshot


class UnsupportedWebsite(ValueError):
    pass


class ProductCheckError(RuntimeError):
    """A failed check is deliberately distinct from an out-of-stock result."""


class StockChecker(ABC):
    @abstractmethod
    def supports(self, url: str) -> bool: ...

    @abstractmethod
    async def check(self, session: aiohttp.ClientSession, url: str) -> ProductSnapshot: ...
