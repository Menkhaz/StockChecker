import json
from decimal import Decimal

from lxml import html

from stockchecker.checkers.disney_store import DisneyStoreChecker
from stockchecker.models import Availability

URL = "https://www.disneystore.com/mia-thermopolis-ear-headband-445031017687.html?x=1"


def test_canonicalizes_disney_product_url():
    canonical, product_id = DisneyStoreChecker.canonicalize(URL)
    assert canonical == "https://www.disneystore.com/mia-thermopolis-ear-headband-445031017687.html"
    assert product_id == "445031017687"


def test_extracts_product_json():
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Mia Thermopolis Ear Headband",
        "offers": {"price": "36.99", "priceCurrency": "USD", "availability": "https://schema.org/InStock"},
    }
    document = html.fromstring(
        f'<html><script type="application/ld+json">{json.dumps(product)}</script></html>'
    )
    extracted = DisneyStoreChecker._find_product_json(document)
    assert extracted["name"] == product["name"]
    assert DisneyStoreChecker._decimal(extracted["offers"]["price"]) == Decimal("36.99")
    assert DisneyStoreChecker._availability(extracted["offers"]["availability"], "") is Availability.IN_STOCK


def test_low_stock_text_overrides_in_stock():
    result = DisneyStoreChecker._availability("https://schema.org/InStock", "LOW STOCK")
    assert result is Availability.LOW_STOCK
