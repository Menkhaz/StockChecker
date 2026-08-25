from __future__ import annotations

import asyncio
import sqlite3
import threading
from decimal import Decimal
from pathlib import Path

from stockchecker.models import Availability, ProductSnapshot, Subscription

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version(version)
SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);

CREATE TABLE IF NOT EXISTS products (
    url TEXT PRIMARY KEY,
    retailer TEXT NOT NULL,
    product_id TEXT NOT NULL,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER NOT NULL,
    product_url TEXT NOT NULL REFERENCES products(url) ON DELETE CASCADE,
    max_price TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, product_url)
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_url TEXT NOT NULL REFERENCES products(url) ON DELETE CASCADE,
    availability TEXT NOT NULL,
    price TEXT,
    currency TEXT,
    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_observations_product
ON observations(product_url, id DESC);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as connection:
            connection.executescript(SCHEMA)

    async def subscribe(self, user_id: int, snapshot: ProductSnapshot, max_price: Decimal | None) -> None:
        await asyncio.to_thread(self._subscribe, user_id, snapshot, max_price)

    def _subscribe(self, user_id: int, snapshot: ProductSnapshot, max_price: Decimal | None) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO products(url, retailer, product_id, name) VALUES (?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET name=excluded.name""",
                (snapshot.url, snapshot.retailer, snapshot.product_id, snapshot.name),
            )
            connection.execute(
                """INSERT INTO subscriptions(user_id, product_url, max_price) VALUES (?, ?, ?)
                   ON CONFLICT(user_id, product_url) DO UPDATE SET max_price=excluded.max_price""",
                (user_id, snapshot.url, str(max_price) if max_price is not None else None),
            )

    async def unsubscribe(self, user_id: int, product_url: str) -> bool:
        return await asyncio.to_thread(self._unsubscribe, user_id, product_url)

    def _unsubscribe(self, user_id: int, product_url: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM subscriptions WHERE user_id=? AND product_url=?", (user_id, product_url)
            )
            return cursor.rowcount > 0

    async def subscriptions_for_user(self, user_id: int) -> list[tuple[str, str, str | None]]:
        return await asyncio.to_thread(self._subscriptions_for_user, user_id)

    def _subscriptions_for_user(self, user_id: int) -> list[tuple[str, str, str | None]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT p.name, p.url, s.max_price FROM subscriptions s
                   JOIN products p ON p.url=s.product_url WHERE s.user_id=? ORDER BY p.name""",
                (user_id,),
            ).fetchall()
        return [(row["name"], row["url"], row["max_price"]) for row in rows]

    async def products(self) -> list[str]:
        return await asyncio.to_thread(self._products)

    def _products(self) -> list[str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT product_url FROM subscriptions ORDER BY product_url"
            ).fetchall()
        return [row["product_url"] for row in rows]

    async def subscribers(self, url: str) -> list[Subscription]:
        return await asyncio.to_thread(self._subscribers, url)

    def _subscribers(self, url: str) -> list[Subscription]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, product_url, max_price FROM subscriptions WHERE product_url=?", (url,)
            ).fetchall()
        return [
            Subscription(
                user_id=row["user_id"],
                product_url=row["product_url"],
                max_price=Decimal(row["max_price"]) if row["max_price"] else None,
            )
            for row in rows
        ]

    async def latest(self, url: str) -> ProductSnapshot | None:
        return await asyncio.to_thread(self._latest, url)

    def _latest(self, url: str) -> ProductSnapshot | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """SELECT p.url, p.retailer, p.product_id, p.name,
                          o.availability, o.price, o.currency
                   FROM products p JOIN observations o ON o.product_url=p.url
                   WHERE p.url=? ORDER BY o.id DESC LIMIT 1""",
                (url,),
            ).fetchone()
        if row is None:
            return None
        return ProductSnapshot(
            url=row["url"], retailer=row["retailer"], product_id=row["product_id"],
            name=row["name"], availability=Availability(row["availability"]),
            price=Decimal(row["price"]) if row["price"] else None, currency=row["currency"],
        )

    async def observe(self, snapshot: ProductSnapshot) -> None:
        await asyncio.to_thread(self._observe, snapshot)

    def _observe(self, snapshot: ProductSnapshot) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("UPDATE products SET name=? WHERE url=?", (snapshot.name, snapshot.url))
            connection.execute(
                """INSERT INTO observations(product_url, availability, price, currency)
                   VALUES (?, ?, ?, ?)""",
                (snapshot.url, snapshot.availability.value,
                 str(snapshot.price) if snapshot.price is not None else None, snapshot.currency),
            )
            connection.execute(
                """DELETE FROM observations WHERE product_url=? AND id NOT IN (
                       SELECT id FROM observations WHERE product_url=? ORDER BY id DESC LIMIT 500
                   )""",
                (snapshot.url, snapshot.url),
            )
