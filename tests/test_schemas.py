from datetime import date

import pytest
from pydantic import ValidationError

from alt_asset_explorer.schemas import Asset, ComparableSale, PriceObservation


def test_asset_validates_category_and_positive_price():
    with pytest.raises(ValidationError):
        Asset(
            asset_id="a",
            ticker="BAD",
            name="Bad Asset",
            category="not_a_category",
            offering_price=-1,
            shares=10,
            source_confidence=0.5,
        )


def test_comparable_sale_normalizes_currency():
    sale = ComparableSale(
        comp_id="c1",
        category="handbags",
        subcategory="birkin",
        source="manual",
        date=date(2026, 1, 1),
        price_usd=100,
        currency="usd",
        exactness_score=0.8,
        source_confidence=0.7,
    )
    assert sale.currency == "USD"


def test_price_observation_rejects_crossed_market():
    with pytest.raises(ValidationError):
        PriceObservation(
            date=date(2026, 1, 1),
            asset_id="a",
            bid=12,
            ask=10,
            last=11,
            volume=0,
            source="manual",
        )
