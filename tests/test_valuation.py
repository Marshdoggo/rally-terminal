from datetime import date

import pandas as pd

from alt_asset_explorer.valuation import estimate_navs


def test_weighted_nav_uses_comps_and_market_premium_discount():
    assets = pd.DataFrame(
        [
            {
                "asset_id": "a1",
                "ticker": "A1",
                "category": "handbags",
                "market_cap_usd": 110,
            }
        ]
    )
    comps = pd.DataFrame(
        [
            {"asset_id": "a1", "date": "2026-01-01", "price_usd": 100, "condition": "excellent", "exactness_score": 1, "source_confidence": 1},
            {"asset_id": "a1", "date": "2025-01-01", "price_usd": 80, "condition": "good", "exactness_score": 0.5, "source_confidence": 0.5},
        ]
    )
    navs = estimate_navs(assets, comps, as_of=date(2026, 7, 1))
    assert len(navs) == 1
    assert navs.iloc[0]["estimated_nav_usd"] > 90
    assert navs.iloc[0]["premium_discount_pct"] > 0
    assert navs.iloc[0]["discount_to_secondary_nav"] < 0
