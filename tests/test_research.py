import pandas as pd
import pytest

from alt_asset_explorer.research import calculate_sector_performance, completed_categories


def test_completed_categories_only_requires_current_trading_targets():
    coverage = pd.DataFrame(
        [
            {"asset_id": "watch", "category": "watches", "observation_count": 4},
            {"asset_id": "old-watch", "category": "watches", "observation_count": 0},
            {"asset_id": "bag", "category": "handbags", "observation_count": 0},
        ]
    )
    assets = pd.DataFrame(
        [
            {"asset_id": "watch", "status": "trading"},
            {"asset_id": "old-watch", "status": "sold"},
            {"asset_id": "bag", "status": "trading"},
        ]
    )

    assert completed_categories(coverage, assets) == ["watches"]


def test_sector_performance_calculates_since_inception_and_last_year():
    observations = pd.DataFrame(
        [
            {"asset_id": "watch", "date": "2024-03-31", "last": 10, "market_cap_usd": 100},
            {"asset_id": "watch", "date": "2025-03-31", "last": 12, "market_cap_usd": 120},
            {"asset_id": "watch", "date": "2026-03-31", "last": 15, "market_cap_usd": 150},
        ]
    )
    assets = pd.DataFrame([{"asset_id": "watch", "category": "watches"}])

    result = calculate_sector_performance(observations, assets, ["watches"])

    assert result.iloc[0]["since_inception"] == pytest.approx(0.5)
    assert result.iloc[0]["last_year"] == pytest.approx(0.25)
    assert result.iloc[0]["constituent_count"] == 1


def test_sector_performance_includes_partially_researched_category_with_coverage():
    observations = pd.DataFrame(
        [
            {"asset_id": "researched", "date": "2025-03-31", "last": 10, "market_cap_usd": 100},
            {"asset_id": "researched", "date": "2026-03-31", "last": 12, "market_cap_usd": 120},
        ]
    )
    assets = pd.DataFrame(
        [
            {"asset_id": "researched", "category": "wine and whiskey", "status": "trading"},
            {"asset_id": "pending", "category": "wine and whiskey", "status": "trading"},
        ]
    )
    coverage = pd.DataFrame(
        [
            {"asset_id": "researched", "category": "wine and whiskey", "observation_count": 2},
            {"asset_id": "pending", "category": "wine and whiskey", "observation_count": 0},
        ]
    )

    result = calculate_sector_performance(observations, assets, ["wine and whiskey"], coverage=coverage)

    assert len(result) == 1
    assert result.iloc[0]["since_inception"] == pytest.approx(0.2)
    assert result.iloc[0]["researched_asset_count"] == 1
    assert result.iloc[0]["target_asset_count"] == 2
    assert result.iloc[0]["coverage_pct"] == pytest.approx(0.5)
    assert result.iloc[0]["coverage_status"] == "Building"
