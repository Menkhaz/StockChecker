from __future__ import annotations

from stockchecker.models import ProductSnapshot


def format_stock_notification(snapshot: ProductSnapshot) -> str:
    """Build the DM used for both real and test stock notifications."""
    price = (
        f"{snapshot.currency} {snapshot.price:.2f}"
        if snapshot.price is not None
        else "unknown price"
    )
    return (
        f"**{snapshot.name}** is **{snapshot.availability.label}** at {price}.\n"
        f"{snapshot.url}"
    )
