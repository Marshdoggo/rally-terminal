import pandas as pd

from alt_asset_explorer.scoring import compute_scores


def test_scoring_returns_transparent_components():
    assets = pd.DataFrame([{"asset_id": "a1", "ticker": "A1", "source_confidence": 0.8, "rarity_score": 0.9}])
    navs = pd.DataFrame([{"asset_id": "a1", "premium_discount_pct": -0.2, "nav_confidence": 0.75}])
    liquidity = pd.DataFrame([{"asset_id": "a1", "bid_ask_spread_pct": 0.05, "stale_mark_flag": False}])
    scores = compute_scores(assets, navs, liquidity)
    assert scores.iloc[0]["investment_score"] > 50
    assert {"valuation_score", "liquidity_score", "data_quality_score"}.issubset(scores.columns)
