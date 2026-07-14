from pathlib import Path
import importlib.util

import pandas as pd
import pytest
from pydantic import ValidationError

from alt_asset_explorer.connectors.category_imports import load_handbag_imports, load_watch_imports
from alt_asset_explorer.connectors.category_imports import (
    load_chrono24_market_data,
    load_fashionphile_listings,
    load_phillips_results,
    load_sothebys_results,
)
from alt_asset_explorer.connectors.rally_manual import load_rally_snapshot_imports


def _load_rally_capture_parser():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "import_rally_portfolio_capture.py"
    spec = importlib.util.spec_from_file_location("import_rally_portfolio_capture", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.parse_portfolio_text


def test_handbag_import_normalizes_to_comparable_sale(tmp_path: Path):
    path = tmp_path / "handbags.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "rally-hermes-birkin-35",
                "brand": "Hermes",
                "model": "Birkin",
                "size": "35",
                "material": "Togo",
                "condition": "excellent",
                "source": "Sothebys",
                "source_url": "https://example.com/sale",
                "date": "2026-03-01",
                "price_usd": 180000,
            }
        ]
    ).to_csv(path, index=False)

    comps = load_handbag_imports(path)

    assert len(comps) == 1
    assert comps.iloc[0]["category"] == "handbags"
    assert comps.iloc[0]["exactness_score"] > 0.75
    assert comps.iloc[0]["source_confidence"] == 0.7


def test_watch_import_normalizes_to_comparable_sale(tmp_path: Path):
    path = tmp_path / "watches.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "rally-rolex-daytona",
                "brand": "Rolex",
                "reference": "116500LN",
                "condition": "excellent",
                "box_papers": "yes",
                "source": "Phillips",
                "date": "2026-03-15",
                "sale_price": 195000,
            }
        ]
    ).to_csv(path, index=False)

    comps = load_watch_imports(path)

    assert len(comps) == 1
    assert comps.iloc[0]["category"] == "watches"
    assert comps.iloc[0]["exactness_score"] > 0.75


def test_rally_snapshot_import_validates_crossed_market(tmp_path: Path):
    path = tmp_path / "rally_snapshots.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-07-01",
                "asset_id": "a1",
                "ticker": "A1",
                "price": 10,
                "bid": 12,
                "ask": 11,
                "volume": 0,
                "source": "user_export",
                "source_confidence": 0.8,
            }
        ]
    ).to_csv(path, index=False)

    with pytest.raises(ValidationError):
        load_rally_snapshot_imports(path)


def test_rally_portfolio_capture_parses_assets_and_snapshots():
    parse_portfolio_text = _load_rally_capture_parser()
    text = """
#SOBLACK
Hermes 30cm “So Black” Birkin
$35.20
$35.2K
Market Cap
#HIMALAYA
Hermes 30cm Himalaya Birkin
$46.90
$93.8K
Market Cap
"""
    assets, snapshots = parse_portfolio_text(text, capture_date="2026-07-02", source_url="https://app.rallyrd.com/app/investments")

    assert len(assets) == 2
    assert len(snapshots) == 2
    assert assets.iloc[0]["ticker"] == "SOBLACK"
    assert assets.iloc[0]["market_cap_usd"] == 35200
    assert assets.iloc[1]["shares"] == 2000
    assert snapshots.iloc[0]["source"] == "rally_portfolio_capture"


def test_sothebys_result_requires_source_url(tmp_path: Path):
    path = tmp_path / "sothebys_results.csv"
    pd.DataFrame(
        [
            {
                "category": "handbags",
                "title": "Hermes Birkin 35",
                "brand": "Hermes",
                "model": "Birkin",
                "sale_date": "2026-01-01",
                "realized_price_usd": 180000,
            }
        ]
    ).to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_sothebys_results(path)


def test_phillips_result_normalizes_watch_auction_metadata(tmp_path: Path):
    path = tmp_path / "phillips_results.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "rally-rolex-daytona",
                "category": "watches",
                "brand": "Rolex",
                "model": "Daytona",
                "reference": "116500LN",
                "condition": "excellent",
                "box_papers": "yes",
                "sale_date": "2026-01-01",
                "realized_price_usd": 195000,
                "source_url": "https://www.phillips.com/example",
                "auction_name": "Watch Auction",
                "lot_id": "12",
                "source_access": "user_export",
            }
        ]
    ).to_csv(path, index=False)

    comps = load_phillips_results(path)

    assert len(comps) == 1
    assert comps.iloc[0]["source"] == "Phillips"
    assert comps.iloc[0]["price_type"] == "realized_with_premium"
    assert comps.iloc[0]["source_access"] == "user_export"
    assert comps.iloc[0]["lot_id"] == "12"


def test_fashionphile_active_listing_has_lower_confidence_than_auction(tmp_path: Path):
    path = tmp_path / "fashionphile_listings.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "rally-hermes-birkin-35",
                "brand": "Hermes",
                "model": "Birkin",
                "size": "35",
                "condition": "excellent",
                "status": "active",
                "listing_date": "2026-01-01",
                "list_price_usd": 175000,
                "source_url": "https://www.fashionphile.com/example",
            }
        ]
    ).to_csv(path, index=False)

    comps = load_fashionphile_listings(path)

    assert len(comps) == 1
    assert comps.iloc[0]["source"] == "Fashionphile"
    assert comps.iloc[0]["price_type"] == "ask"
    assert comps.iloc[0]["source_confidence"] <= 0.65


def test_chrono24_market_data_stays_out_of_comparable_sales(tmp_path: Path):
    path = tmp_path / "chrono24_market_data.csv"
    pd.DataFrame(
        [
            {
                "source": "Chrono24",
                "source_url": "https://www.chrono24.com/chronopulse.htm",
                "date": "2026-01-01",
                "brand": "Rolex",
                "model": "Daytona",
                "reference": "116500LN",
                "metric_name": "index",
                "metric_value": 1050,
                "source_confidence": 0.75,
            }
        ]
    ).to_csv(path, index=False)

    market = load_chrono24_market_data(path)

    assert len(market) == 1
    assert "price_usd" not in market.columns
    assert market.iloc[0]["category"] == "watches"
