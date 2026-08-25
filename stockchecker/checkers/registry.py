from __future__ import annotations

from stockchecker.checkers.base import StockChecker, UnsupportedWebsite
from stockchecker.checkers.disney_store import DisneyStoreChecker


class CheckerRegistry:
    def __init__(self) -> None:
        self._checkers: tuple[StockChecker, ...] = (DisneyStoreChecker(),)

    def for_url(self, url: str) -> StockChecker:
        for checker in self._checkers:
            if checker.supports(url):
                return checker
        raise UnsupportedWebsite("That website is not supported. Currently supported: Disney Store")
