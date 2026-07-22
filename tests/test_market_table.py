import pandas as pd
import pytest

from alt_asset_explorer.market_table import build_market_table, filter_market_table


def test_market_table_keeps_missing_bid_ask_and_spread_null():
    canonical = pd.DataFrame(
        [
            {
                "asset_id": "rally-soblack",
                "ticker": "SOBLACK",
                "name": "So Black Birkin",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "share_count": 1000,
                "offering_price_usd": 35.2,
                "offering_valuation_usd": 35200,
                "source_type": "rally_portfolio_capture",
                "status": "trading",
                "last_quote_observed_at": "2026-07-02",
                "data_quality_status": "usable",
            }
        ]
    )
    decision = pd.DataFrame(
        [
            {
                "asset_id": "rally-soblack",
                "current_market_cap_usd": 35200,
                "estimated_nav_usd": 40000,
                "nav_confidence": 0.5,
            }
        ]
    )
    prices = pd.DataFrame([{"asset_id": "rally-soblack", "date": "2026-07-02", "last": 35.2, "market_cap_usd": 35200}])
    liquidity = pd.DataFrame([{"asset_id": "rally-soblack", "bid_ask_spread_pct": None}])

    table = build_market_table(canonical, decision, prices, liquidity)

    assert pd.isna(table.iloc[0]["best_bid"])
    assert pd.isna(table.iloc[0]["best_ask"])
    assert pd.isna(table.iloc[0]["bid_ask_spread_pct"])
    assert table.iloc[0]["premium_discount_to_fair_value"] == pytest.approx(-0.12)
    assert table.iloc[0]["is_current_listed"]


def test_market_table_marks_manual_trading_asset_with_quote_current():
    canonical = pd.DataFrame(
        [
            {
                "asset_id": "rally-mosasaur",
                "ticker": "MOSASAUR",
                "name": "Mosasaur",
                "category": "fossils",
                "subcategory": "",
                "share_count": 6000,
                "offering_price_usd": 5.0,
                "offering_valuation_usd": 30000,
                "source_type": "manual_seed",
                "status": "trading",
                "last_quote_observed_at": "2026-06-29",
                "data_quality_status": "usable",
            }
        ]
    )
    decision = pd.DataFrame([{"asset_id": "rally-mosasaur", "current_market_cap_usd": 34200}])
    prices = pd.DataFrame([{"asset_id": "rally-mosasaur", "date": "2026-06-29", "last": 5.7, "market_cap_usd": 34200}])

    table = build_market_table(canonical, decision, prices)

    assert table.iloc[0]["is_current_listed"]


def test_market_table_marks_manual_trading_asset_without_quote_current():
    canonical = pd.DataFrame(
        [
            {
                "asset_id": "rally-pappy1",
                "ticker": "PAPPY1",
                "name": "Pappy Van Winkle Bourbon Assortment",
                "category": "wine and whiskey",
                "subcategory": "bourbon",
                "share_count": 2000,
                "offering_price_usd": 7.0,
                "offering_valuation_usd": 14000,
                "source_type": "manual_seed",
                "status": "trading",
                "data_quality_status": "usable",
            }
        ]
    )
    decision = pd.DataFrame([{"asset_id": "rally-pappy1"}])
    prices = pd.DataFrame(columns=["asset_id", "date", "last", "market_cap_usd"])

    table = build_market_table(canonical, decision, prices)

    assert table.iloc[0]["is_current_listed"]


def test_current_listed_filter_excludes_sec_synthesized_without_quote():
    table = pd.DataFrame(
        [
            {
                "asset_id": "rally-soblack",
                "ticker": "SOBLACK",
                "name": "So Black Birkin",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "data_quality_status": "usable",
                "nav_confidence": 0.5,
                "premium_discount_to_fair_value": -0.1,
                "is_current_listed": True,
            },
            {
                "asset_id": "sec-rally-warhol1",
                "ticker": "WARHOL1",
                "name": "Warhol Print",
                "category": "art",
                "subcategory": "warhol",
                "data_quality_status": "limited",
                "nav_confidence": None,
                "premium_discount_to_fair_value": None,
                "is_current_listed": False,
            },
        ]
    )

    filtered = filter_market_table(table, current_listed_only=True)

    assert filtered["ticker"].tolist() == ["SOBLACK"]


def test_market_table_filters_below_estimated_fair_value_and_confidence():
    table = pd.DataFrame(
        [
            {
                "asset_id": "a",
                "ticker": "A",
                "name": "Asset A",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "data_quality_status": "usable",
                "nav_confidence": 0.75,
                "premium_discount_to_fair_value": -0.2,
                "is_current_listed": True,
            },
            {
                "asset_id": "b",
                "ticker": "B",
                "name": "Asset B",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "data_quality_status": "usable",
                "nav_confidence": 0.20,
                "premium_discount_to_fair_value": -0.3,
                "is_current_listed": True,
            },
        ]
    )

    filtered = filter_market_table(table, valuation_filter="Below estimated fair value", min_confidence=0.5)

    assert filtered["ticker"].tolist() == ["A"]


def test_market_table_adds_trailing_and_full_returns_from_valid_prices():
    canonical = pd.DataFrame([
        {"asset_id": "a", "ticker": "A", "name": "Asset A", "category": "art", "subcategory": "", "share_count": 100, "offering_price_usd": 10, "offering_valuation_usd": 1000, "source_type": "manual_seed", "status": "trading", "data_quality_status": "usable"}
    ])
    decision = pd.DataFrame([{"asset_id": "a"}])
    prices = pd.DataFrame([
        {"asset_id": "a", "date": "2025-01-01", "last": 10.0, "event_type": "chart_observation"},
        {"asset_id": "a", "date": "2025-07-01", "last": 12.0, "event_type": "chart_observation"},
        {"asset_id": "a", "date": "2026-04-01", "last": 15.0, "event_type": "chart_observation"},
        {"asset_id": "a", "date": "2026-07-01", "last": 18.0, "event_type": "chart_observation"},
    ])

    table = build_market_table(canonical, decision, prices)

    assert table.iloc[0]["return_1q"] == pytest.approx(0.2)
    assert table.iloc[0]["return_1y"] == pytest.approx(0.5)
    assert table.iloc[0]["return_full_history"] == pytest.approx(0.8)


def test_market_table_leaves_insufficient_trailing_history_blank():
    canonical = pd.DataFrame([
        {"asset_id": "new", "ticker": "NEW", "name": "New Asset", "category": "books", "subcategory": "", "share_count": 100, "offering_price_usd": 10, "offering_valuation_usd": 1000, "source_type": "manual_seed", "status": "trading", "data_quality_status": "usable"}
    ])
    decision = pd.DataFrame([{"asset_id": "new"}])
    prices = pd.DataFrame([
        {"asset_id": "new", "date": "2026-06-01", "last": 10.0, "event_type": "chart_observation"},
        {"asset_id": "new", "date": "2026-07-01", "last": 11.0, "event_type": "chart_observation"},
    ])

    table = build_market_table(canonical, decision, prices)

    assert pd.isna(table.iloc[0]["return_1q"])
    assert pd.isna(table.iloc[0]["return_1y"])
    assert table.iloc[0]["return_full_history"] == pytest.approx(0.1)
