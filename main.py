"""StockChecker entry point for local use and AMP Python App Runner."""

import asyncio

from stockchecker.app import run

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        # AMP stops the instance by sending an interrupt signal. asyncio first
        # cancels the main task so its cleanup can run, then raises
        # KeyboardInterrupt to the caller; that is a normal shutdown here.
        pass
