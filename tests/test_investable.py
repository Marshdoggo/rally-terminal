from datetime import date

import pandas as pd
import pytest

from alt_asset_explorer.export import MME_UNIVERSE_COLUMNS, build_mme_universe_export, build_newsletter_exports
from alt_asset_explorer.investable import (
    COMPARABLE_SALE_COLUMNS,
    RALLY_ASSET_COLUMNS,
    build_comparable_sales_universe,
    build_data_diagnostics,
    build_rally_asset_universe,
    estimate_secondary_navs,
    infer_rally_category,
    match_assets_to_comps,
    parse_collectible_title,
)


def test_parse_collectible_title_extracts_birkin_features():
    parsed = parse_collectible_title("Gold Togo Birkin 25 Gold Hardware, 2021")
    assert parsed["brand"] == ""
    assert parsed["model"] == "Birkin"
    assert parsed["size"] == "25"
    assert parsed["material"] == "Togo"
    assert parsed["color"] == "Gold"
    assert parsed["hardware"] == "Gold Hardware"
    assert parsed["year"] == 2021

    exotic = parse_collectible_title("Hermès Violet Shiny Porosus Crocodile Birkin 35 Palladium Hardware, 2011")
    assert exotic["brand"] == "Hermes"
    assert exotic["material"] == "Porosus Crocodile"
    assert exotic["size"] == "35"

    picnic = parse_collectible_title("Limited Edition Natural Barénia Leather & Osier Picnic Kelly 35cm Bag")
    assert picnic["model"] == "Kelly"


def test_rally_category_inference_conservatively_classifies_sec_titles():
    assert infer_rally_category("2015 Hermès 30cm Birkin Tangerine Ostrich") == "handbags"
    assert infer_rally_category("Audemars Piguet Royal Oak Jumbo A-Series Ref.5402") == "watches"
    assert infer_rally_category("1986 Fleer #57 Michael Jordan Card") == "cards"
    assert infer_rally_category("1962 Journey Into Mystery #83 CGC NM 9.4") == "comics"


def test_build_rally_asset_universe_uses_unified_schema():
    assets = pd.DataFrame(
        [
            {
                "asset_id": "a1",
                "ticker": "BIRKIN",
                "name": "Hermes Gold Togo Birkin 25 Gold Hardware, 2021",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "offering_date": "2024-01-01",
                "offering_price": 10,
                "shares": 1000,
                "market_cap_usd": 12000,
                "last_price_usd": 12,
                "source_url": "manual",
                "source_confidence": 0.8,
                "rarity_score": 0.5,
                "status": "active",
            }
        ]
    )
    prices = pd.DataFrame([{"asset_id": "a1", "date": "2026-07-01", "last": 12, "bid": 11.5, "ask": 12.5, "market_cap_usd": 12000}])
    universe = build_rally_asset_universe(assets, prices, pd.DataFrame(), pd.DataFrame())
    assert list(universe.columns) == RALLY_ASSET_COLUMNS
    assert universe.iloc[0]["model"] == "Birkin"
    assert universe.iloc[0]["offering_market_cap_usd"] == 10000
    assert universe.iloc[0]["current_market_cap_usd"] == 12000
    assert universe.iloc[0]["status"] == "trading"


def test_comps_matching_and_nav_metrics(tmp_path):
    rally_assets = pd.DataFrame(
        [
            {
                "asset_id": "a1",
                "ticker": "BIRKIN",
                "name": "Hermes Gold Togo Birkin 25 Gold Hardware, 2021",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "brand": "Hermes",
                "model": "Birkin",
                "year": 2021,
                "size": "25",
                "material": "Togo",
                "color": "Gold",
                "hardware": "Gold Hardware",
                "offering_date": "2024-01-01",
                "offering_market_cap_usd": 10000,
                "current_market_cap_usd": 9000,
                "acquisition_cost_usd": None,
                "last_trade_price": 9,
                "bid_price": 8.8,
                "ask_price": 9.2,
                "share_count": 1000,
                "sec_filing_url": "manual",
                "status": "trading",
                "exit_date": None,
                "exit_market_cap_usd": None,
                "source_notes": "test",
            }
        ]
    )
    raw_comps = pd.DataFrame(
        [
            {
                "comp_id": "c1",
                "source": "Sothebys",
                "auction_name": "Handbags",
                "auction_url": "https://example.com",
                "date": "2026-02-01",
                "price_usd": 12000,
                "currency": "USD",
                "title": "Hermès Gold Togo Birkin 25 Gold Hardware, 2021",
                "lot_url": "https://example.com/1",
                "exactness_score": 0.9,
                "source_confidence": 0.9,
                "estimate_low_usd": 10000,
                "estimate_high_usd": 14000,
            },
            {
                "comp_id": "c2",
                "source": "Sothebys",
                "date": "2026-03-01",
                "price_usd": 8000,
                "currency": "USD",
                "title": "Hermès Black Box Kelly 28 Gold Hardware, 2021",
                "lot_url": "https://example.com/2",
                "exactness_score": 0.8,
                "source_confidence": 0.8,
            },
        ]
    )
    comps = build_comparable_sales_universe(raw_comps)
    assert list(comps.columns) == COMPARABLE_SALE_COLUMNS
    matches = match_assets_to_comps(rally_assets, comps, min_score=0.1)
    assert matches.iloc[0]["comp_id"] == "c1"
    navs = estimate_secondary_navs(rally_assets, comps, matches, as_of=date(2026, 7, 2))
    assert navs.iloc[0]["estimated_nav_usd"] > 0
    assert navs.iloc[0]["discount_to_secondary_nav"] < 0
    assert navs.iloc[0]["premium_to_offering"] == pytest.approx(-0.1)
    diagnostics = build_data_diagnostics(rally_assets, comps, navs, tmp_path / "missing.csv")
    assert set(diagnostics["metric"]).issuperset({"rally_assets", "comparable_sales", "duplicate_possible_lots"})


def test_mme_universe_export_shape():
    decision = pd.DataFrame(
        [
            {
                "ticker": "BIRKIN",
                "name": "Birkin",
                "category": "handbags",
                "discount_to_secondary_nav": -0.25,
                "nav_confidence": 0.75,
                "liquidity_score": 0.5,
                "mispricing_score": 22,
            }
        ]
    )
    export = build_mme_universe_export(decision, as_of=date(2026, 7, 2))
    assert list(export.columns) == MME_UNIVERSE_COLUMNS
    assert export.iloc[0]["universe"] == "alternative_assets"


def test_newsletter_exports_shape():
    decision = pd.DataFrame(
        [
            {
                "ticker": "BIRKIN",
                "name": "Birkin",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "status": "trading",
                "current_market_cap_usd": 9000,
                "offering_market_cap_usd": 10000,
                "discount_to_secondary_nav": -0.25,
                "premium_to_offering": -0.10,
                "nav_confidence": 0.75,
                "comp_count": 5,
                "sec_filing_url": "https://example.com/sec",
            },
            {
                "ticker": "EXITED",
                "name": "Exited Asset",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "status": "exited",
                "current_market_cap_usd": None,
                "offering_market_cap_usd": 100000,
                "exit_market_cap_usd": 150000,
                "exit_date": "2026-01-01",
                "discount_to_secondary_nav": None,
                "premium_to_offering": None,
                "nav_confidence": 0.0,
                "comp_count": 0,
                "sec_filing_url": "https://example.com/exit",
            },
        ]
    )
    exports = build_newsletter_exports(decision, as_of=date(2026, 7, 2))
    assert set(exports) == {
        "newsletter_market_movers",
        "newsletter_notable_discounts",
        "newsletter_recent_exits",
        "newsletter_weak_data",
    }
    assert exports["newsletter_notable_discounts"].iloc[0]["ticker"] == "BIRKIN"
    assert exports["newsletter_recent_exits"].iloc[0]["ticker"] == "EXITED"
