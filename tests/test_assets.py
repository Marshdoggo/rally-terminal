from datetime import date

import pandas as pd

from alt_asset_explorer.assets import CANONICAL_ASSET_COLUMNS, build_canonical_asset_master


def test_canonical_asset_master_preserves_provenance_and_quote_dates():
    universe = pd.DataFrame(
        [
            {
                "asset_id": "rally-soblack",
                "ticker": "soblack",
                "name": "Hermes So Black Birkin",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "brand": "Hermes",
                "model": "Birkin",
                "offering_market_cap_usd": 35200,
                "share_count": 1000,
                "sec_filing_url": "https://app.rallyrd.com/app/investments",
                "status": "trading",
                "source_notes": "Imported from visible Rally portfolio capture.",
            }
        ]
    )
    prices = pd.DataFrame(
        [
            {"asset_id": "rally-soblack", "date": "2026-07-01", "last": 35.0},
            {"asset_id": "rally-soblack", "date": "2026-07-02", "last": 35.2},
        ]
    )

    master = build_canonical_asset_master(universe, prices, as_of=date(2026, 7, 11))

    assert list(master.columns) == CANONICAL_ASSET_COLUMNS
    assert master.iloc[0]["ticker"] == "SOBLACK"
    assert master.iloc[0]["offering_price_usd"] == 35.2
    assert master.iloc[0]["source_type"] == "rally_portfolio_capture"
    assert master.iloc[0]["last_quote_observed_at"] == "2026-07-02"
    assert master.iloc[0]["data_quality_status"] == "usable"


def test_canonical_asset_master_flags_sec_synthesized_rows_without_quotes():
    universe = pd.DataFrame(
        [
            {
                "asset_id": "sec-rally-birkintan",
                "ticker": "BIRKINTAN",
                "name": "Hermes Tangerine Birkin",
                "category": "handbags",
                "subcategory": "hermes_birkin",
                "offering_market_cap_usd": 28000,
                "share_count": 1000,
                "sec_filing_url": "https://www.sec.gov/Archives/example",
                "status": "trading",
                "source_notes": "Synthesized from cached SEC offering tables.",
            }
        ]
    )

    master = build_canonical_asset_master(universe, pd.DataFrame(), as_of=date(2026, 7, 11))

    assert master.iloc[0]["source_type"] == "sec_synthesized"
    assert master.iloc[0]["data_quality_status"] == "limited"
    assert "missing_quote_snapshot" in master.iloc[0]["data_quality_warnings"]
    assert "sec_synthesized_not_live_rally_quote" in master.iloc[0]["data_quality_warnings"]
