"""StockChecker entry point for local use and AMP Python App Runner."""

import asyncio

from stockchecker.app import run

if __name__ == "__main__":
    asyncio.run(run())
