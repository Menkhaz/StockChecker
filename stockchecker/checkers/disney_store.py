from __future__ import annotations

import json
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from lxml import html

from stockchecker.checkers.base import ProductCheckError, StockChecker
from stockchecker.models import Availability, ProductSnapshot

# Disney uses a 12-digit ID for ordinary product pages and a 13-digit master
# style ID followed by "M" for products with selectable variants such as size.
_PRODUCT_ID = re.compile(r"-(\d{12}|\d{13}M)\.html$", re.IGNORECASE)


class DisneyStoreChecker(StockChecker):
    retailer = "Disney Store"
    valid_hosts: ClassVar[set[str]] = {"disneystore.com", "www.disneystore.com"}

    def supports(self, url: str) -> bool:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and parsed.hostname in self.valid_hosts

    @staticmethod
    def canonicalize(url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        if parsed.hostname not in DisneyStoreChecker.valid_hosts:
            raise ProductCheckError("Only disneystore.com product URLs are supported")
        match = _PRODUCT_ID.search(parsed.path)
        if not match:
            raise ProductCheckError("The Disney Store URL does not contain a product ID")
        canonical = urlunsplit(("https", "www.disneystore.com", parsed.path, "", ""))
        return canonical, match.group(1)

    async def check(self, session: aiohttp.ClientSession, url: str) -> ProductSnapshot:
        canonical, product_id = self.canonicalize(url)
        try:
            async with session.get(canonical, allow_redirects=True) as response:
                body = await response.text(errors="replace")
                if response.status == 404:
                    raise ProductCheckError("Disney Store no longer has this product page")
                if response.status == 429:
                    raise ProductCheckError("Disney Store rate-limited the stock check")
                if response.status >= 400:
                    raise ProductCheckError(f"Disney Store returned HTTP {response.status}")
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ProductCheckError(f"Disney Store request failed: {exc}") from exc

        document = html.fromstring(body)
        product = self._find_product_json(document)
        if product is None:
            raise ProductCheckError("Disney Store product data was not present in the page")
        name = str(product.get("name") or "").strip()
        offer = self._first_offer(product.get("offers"))
        if not name or offer is None:
            raise ProductCheckError("Disney Store returned incomplete product data")

        availability = self._availability(offer.get("availability"), body)
        price = self._decimal(offer.get("price") or offer.get("lowPrice"))
        currency = str(offer.get("priceCurrency") or "USD").upper()
        return ProductSnapshot(
            url=canonical,
            retailer=self.retailer,
            product_id=product_id,
            name=name,
            availability=availability,
            price=price,
            currency=currency if price is not None else None,
        )

    @staticmethod
    def _json_nodes(value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            graph = value.get("@graph")
            if isinstance(graph, list):
                for node in graph:
                    yield from DisneyStoreChecker._json_nodes(node)
        elif isinstance(value, list):
            for node in value:
                yield from DisneyStoreChecker._json_nodes(node)

    @classmethod
    def _find_product_json(cls, document: Any) -> dict[str, Any] | None:
        for raw in document.xpath('//script[@type="application/ld+json"]/text()'):
            try:
                decoded = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            for node in cls._json_nodes(decoded):
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if "Product" in types:
                    return node
        return cls._find_product_microdata(document)

    @classmethod
    def _find_product_microdata(cls, document: Any) -> dict[str, Any] | None:
        products = document.xpath(
            '//*[@itemscope and '
            '(substring-after(@itemtype, "schema.org/") = "Product")]'
        )
        for product in products:
            name = cls._microdata_value(product, "name")
            offer_nodes = product.xpath('.//*[@itemprop="offers" and @itemscope]')
            if not name or not offer_nodes:
                continue

            offer = {
                key: cls._microdata_value(offer_nodes[0], key)
                for key in ("price", "lowPrice", "priceCurrency", "availability")
            }
            return {
                "@type": "Product",
                "name": name,
                "offers": {key: value for key, value in offer.items() if value},
            }
        return None

    @staticmethod
    def _microdata_value(scope: Any, itemprop: str) -> str:
        nodes = scope.xpath(f'.//*[@itemprop="{itemprop}"][1]')
        if not nodes:
            return ""
        node = nodes[0]
        return str(node.get("content") or node.get("href") or node.text_content()).strip()

    @staticmethod
    def _first_offer(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            offers = value.get("offers")
            if isinstance(offers, list):
                return next((item for item in offers if isinstance(item, dict)), None)
            return value
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), None)
        return None

    @staticmethod
    def _availability(value: Any, body: str) -> Availability:
        normalized = str(value or "").rsplit("/", 1)[-1].lower()
        mapping = {
            "instock": Availability.IN_STOCK,
            "limitedavailability": Availability.LOW_STOCK,
            "outofstock": Availability.OUT_OF_STOCK,
            "soldout": Availability.OUT_OF_STOCK,
            "preorder": Availability.PREORDER,
            "presale": Availability.PREORDER,
        }
        result = mapping.get(normalized, Availability.UNKNOWN)
        body_lower = body.lower()
        if result.purchasable and "low stock" in body_lower:
            return Availability.LOW_STOCK
        if result is Availability.UNKNOWN and "coming soon" in body_lower:
            return Availability.COMING_SOON
        return result

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return None
