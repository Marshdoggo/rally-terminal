import pandas as pd

from alt_asset_explorer.birkin import build_birkin_comparison, birkin_market_summary, parse_birkin_features


def test_parse_birkin_features_identifies_size_material_year_and_exotic():
    features = parse_birkin_features("Violet Shiny Porosus Crocodile Birkin 35 Palladium Hardware, 2011")

    assert features["brand"] == "Hermes"
    assert features["model"] == "Birkin"
    assert features["size"] == "35"
    assert features["material"] == "Porosus Crocodile"
    assert features["year"] == "2011"
    assert features["is_exotic"]


def test_parse_birkin_features_excludes_kelly_model():
    features = parse_birkin_features("Gold Madame Kelly Elan Palladium Hardware, 2023")

    assert features["model"] == ""
    assert features["size"] == ""


def test_build_birkin_comparison_includes_sec_and_sothebys_birkin_only():
    assets = pd.DataFrame(
        [
            {
                "asset_id": "rally-hermes-birkin-35",
                "ticker": "HERMES35",
                "name": "2012 Hermes Birkin 35 Handbag",
                "series_name": "Series #HermesBirkin35",
                "offering_date": "2021-05-14",
                "offering_price": 10,
                "shares": 14000,
                "market_cap_usd": 168000,
                "source_url": "manual_seed",
                "source_confidence": 0.7,
            }
        ]
    )
    comps = pd.DataFrame(
        [
            {
                "source": "Sothebys",
                "category": "handbags",
                "notes": "Gold Togo Birkin 25 Gold Hardware, 2021",
                "date": "2026-02-12",
                "price_usd": 27940,
                "estimate_low_usd": 15000,
                "estimate_high_usd": 20000,
                "exactness_score": 0.85,
                "source_confidence": 0.9,
                "lot_id": "60",
                "auction_name": "Handbags & Accessories",
                "source_url": "https://www.sothebys.com/example",
            },
            {
                "source": "Sothebys",
                "category": "handbags",
                "notes": "Gold Madame Kelly Elan Palladium Hardware, 2023",
                "date": "2026-02-12",
                "price_usd": 16510,
                "exactness_score": 0.85,
                "source_confidence": 0.9,
            },
        ]
    )
    sec = pd.DataFrame(
        [
            {
                "series_id": "sec-birkin",
                "series_name": "SERIES #BIRKINBLU",
                "asset_name": "SERIES #BIRKINBLU",
                "filing_url": "https://www.sec.gov/example",
                "filing_date": "2025-05-20",
                "offering_price": 58000,
                "shares": 55,
                "source_confidence": 0.8,
            }
        ]
    )

    comparison = build_birkin_comparison(assets, comps, sec)

    assert set(comparison["record_type"]) == {"rally_asset", "rally_sec_series", "sothebys_comp"}
    assert len(comparison[comparison["record_type"] == "sothebys_comp"]) == 1
    assert comparison.loc[comparison["record_type"] == "sothebys_comp", "size"].iloc[0] == "25"

    summary = birkin_market_summary(comparison)
    assert summary.iloc[0]["comp_count"] == 1
    assert summary.iloc[0]["secondary_nav_usd"] == 27940
