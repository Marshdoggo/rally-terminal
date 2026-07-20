import pandas as pd
import pytest

from alt_asset_explorer.indices import (
    RALLY_INDEX_COLUMNS,
    build_index_from_selection,
    build_quarterly_rally_indices,
    prepare_quarterly_observations,
    build_rally_indices,
    summarize_contributions,
)


def test_rally_indices_normalize_to_100_and_calculate_equal_weight_return():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2026-07-01", "last": 20, "market_cap_usd": 300},
            {"asset_id": "a", "date": "2026-07-02", "last": 11, "market_cap_usd": 110},
            {"asset_id": "b", "date": "2026-07-02", "last": 18, "market_cap_usd": 270},
        ]
    )

    indices = build_rally_indices(prices)
    equal = indices[indices["index_id"] == "rally_market_equal_weight"].sort_values("date")

    assert list(indices.columns) == RALLY_INDEX_COLUMNS
    assert equal.iloc[0]["index_level"] == 100.0
    assert equal.iloc[1]["return_1d"] == pytest.approx(0.0)
    assert equal.iloc[1]["index_level"] == pytest.approx(100.0)


def test_market_cap_weighted_index_uses_available_market_caps():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2026-07-01", "last": 20, "market_cap_usd": 300},
            {"asset_id": "a", "date": "2026-07-02", "last": 11, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2026-07-02", "last": 22, "market_cap_usd": 300},
        ]
    )

    indices = build_rally_indices(prices)
    cap_weight = indices[indices["index_id"] == "rally_market_market_cap_weight"].sort_values("date")

    assert cap_weight.iloc[1]["return_1d"] == pytest.approx(0.1)
    assert cap_weight.iloc[1]["index_level"] == pytest.approx(110.0)


def test_indices_skip_missing_prices_and_missing_market_caps_for_cap_weight():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2026-07-01", "last": None, "market_cap_usd": 300},
            {"asset_id": "a", "date": "2026-07-02", "last": 11, "market_cap_usd": None},
            {"asset_id": "b", "date": "2026-07-02", "last": 22, "market_cap_usd": 300},
        ]
    )

    indices = build_rally_indices(prices)
    equal = indices[indices["index_id"] == "rally_market_equal_weight"].sort_values("date")
    cap_weight = indices[indices["index_id"] == "rally_market_market_cap_weight"].sort_values("date")

    assert equal.iloc[0]["constituent_count"] == 1
    assert equal.iloc[1]["constituent_count"] == 2
    assert cap_weight.iloc[0]["constituent_count"] == 1
    assert cap_weight.iloc[1]["constituent_count"] == 1


def test_indices_exclude_offering_and_distribution_events():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": 100, "event_type": "offering_price"},
            {"asset_id": "a", "date": "2026-07-02", "last": 20, "market_cap_usd": 200, "event_type": "distribution"},
        ]
    )

    assert build_rally_indices(prices).empty


def test_market_cap_index_excludes_missing_cap_but_equal_weight_includes_price():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": None},
            {"asset_id": "a", "date": "2026-07-02", "last": 11, "market_cap_usd": None},
        ]
    )

    indices = build_rally_indices(prices)
    assert len(indices[indices["index_id"] == "rally_market_equal_weight"]) == 2
    assert indices[indices["index_id"] == "rally_market_market_cap_weight"].empty


def test_market_cap_weighted_index_uses_prior_period_weights():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2026-07-01", "last": 10, "market_cap_usd": 300},
            {"asset_id": "a", "date": "2026-07-02", "last": 20, "market_cap_usd": 900},
            {"asset_id": "b", "date": "2026-07-02", "last": 10, "market_cap_usd": 100},
        ]
    )

    cap_weight = build_rally_indices(prices)
    cap_weight = cap_weight[cap_weight["index_id"] == "rally_market_market_cap_weight"].sort_values("date")
    assert cap_weight.iloc[1]["return_1d"] == pytest.approx(0.25)


def test_index_rebuild_is_deterministic():
    prices = pd.DataFrame(
        [
            {"asset_id": "b", "date": "2026-07-02", "last": 22, "market_cap_usd": 300},
            {"asset_id": "a", "date": "2026-07-01", "last": 10, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2026-07-01", "last": 20, "market_cap_usd": 300},
            {"asset_id": "a", "date": "2026-07-02", "last": 11, "market_cap_usd": 100},
        ]
    )

    pd.testing.assert_frame_equal(build_rally_indices(prices), build_rally_indices(prices))


def test_quarterly_indices_use_period_end_and_category_membership():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "period_end": "2026-03-31", "observed_at": "2026-03-28", "last": 10, "market_cap_usd": 100, "event_type": "executed_trade", "frequency": "quarterly"},
            {"asset_id": "b", "period_end": "2026-03-31", "observed_at": "2026-03-30", "last": 20, "market_cap_usd": 300, "event_type": "executed_trade", "frequency": "quarterly"},
            {"asset_id": "a", "period_end": "2026-06-30", "observed_at": "2026-06-28", "last": 20, "market_cap_usd": 900, "event_type": "executed_trade", "frequency": "quarterly"},
            {"asset_id": "b", "period_end": "2026-06-30", "observed_at": "2026-06-29", "last": 20, "market_cap_usd": 100, "event_type": "executed_trade", "frequency": "quarterly"},
        ]
    )
    assets = pd.DataFrame([{"asset_id": "a", "category": "cards"}, {"asset_id": "b", "category": "watches"}])

    indices = build_quarterly_rally_indices(prices, assets)
    cap_weight = indices[indices["index_id"] == "rally_quarterly_all_market_cap_weight"].sort_values("date")

    assert "2026-03-31" in set(indices["date"])
    assert "rally_quarterly_cards_equal_weight" in set(indices["index_id"])
    assert cap_weight.iloc[1]["return_1d"] == pytest.approx(0.25)


def test_quarterly_indices_use_offering_price_as_inception_baseline():
    prices = pd.DataFrame(
        [
            {
                "asset_id": "watch",
                "period_end": "2020-12-31",
                "observed_at": "2020-10-05",
                "last": 5.00,
                "market_cap_usd": 69000,
                "event_type": "offering_price",
                "frequency": "quarterly",
            },
            {
                "asset_id": "watch",
                "period_end": "2021-03-31",
                "observed_at": "2021-04-15",
                "last": 2.75,
                "market_cap_usd": 37950,
                "event_type": "chart_observation",
                "frequency": "quarterly",
            },
        ]
    )
    assets = pd.DataFrame([{"asset_id": "watch", "category": "watches"}])

    indices = build_quarterly_rally_indices(prices, assets)
    watches = indices[indices["index_id"] == "rally_quarterly_watches_equal_weight"].sort_values("date")

    assert watches["date"].tolist() == ["2020-12-31", "2021-03-31"]
    assert watches.iloc[0]["index_level"] == pytest.approx(100.0)
    assert watches.iloc[1]["return_1d"] == pytest.approx(-0.45)
    assert watches.iloc[1]["index_level"] == pytest.approx(55.0)


def test_quarterly_indices_prefer_terminal_buyout_over_intra_quarter_observation():
    prices = pd.DataFrame(
        [
            {
                "asset_id": "watch",
                "period_end": "2021-03-31",
                "observed_at": "2021-03-02",
                "last": 40.50,
                "market_cap_usd": 40500,
                "event_type": "chart_observation",
                "frequency": "quarterly",
            },
            {
                "asset_id": "watch",
                "period_end": "2021-06-30",
                "observed_at": "2021-05-10",
                "last": 40.65,
                "market_cap_usd": 40650,
                "event_type": "chart_observation",
                "frequency": "quarterly",
            },
            {
                "asset_id": "watch",
                "period_end": "2021-06-30",
                "observed_at": "2021-06-30",
                "last": 110.00,
                "market_cap_usd": 110000,
                "event_type": "buyout",
                "frequency": "quarterly",
            },
        ]
    )
    assets = pd.DataFrame([{"asset_id": "watch", "category": "watches"}])

    observations = prepare_quarterly_observations(prices, assets)
    q2 = observations[observations["date"].astype(str).eq("2021-06-30")].iloc[0]

    assert q2["last"] == pytest.approx(110.00)
    assert q2["event_type"] == "buyout"


def test_custom_index_accepts_arbitrary_asset_selection_and_date_range():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2025-03-31", "last": 5, "market_cap_usd": 50},
            {"asset_id": "a", "date": "2025-06-30", "last": 10, "market_cap_usd": 100},
            {"asset_id": "b", "date": "2025-06-30", "last": 10, "market_cap_usd": 100},
            {"asset_id": "c", "date": "2025-06-30", "last": 10, "market_cap_usd": 100},
            {"asset_id": "a", "date": "2025-09-30", "last": 12, "market_cap_usd": 120},
            {"asset_id": "b", "date": "2025-09-30", "last": 8, "market_cap_usd": 80},
            {"asset_id": "c", "date": "2025-09-30", "last": 30, "market_cap_usd": 300},
        ]
    )

    result = build_index_from_selection(
        prices,
        asset_ids=["a", "b"],
        start_date="2025-06-01",
        weighting_method="equal",
    )

    assert result.series["date"].tolist() == ["2025-06-30", "2025-09-30"]
    assert result.series.iloc[-1]["index_level"] == pytest.approx(100.0)
    assert set(result.contributions["asset_id"]) == {"a", "b"}


def test_contribution_points_reconcile_to_index_move():
    prices = pd.DataFrame(
        [
            {"asset_id": "winner", "date": "2026-03-31", "last": 10, "market_cap_usd": 100},
            {"asset_id": "loser", "date": "2026-03-31", "last": 10, "market_cap_usd": 100},
            {"asset_id": "winner", "date": "2026-06-30", "last": 12, "market_cap_usd": 120},
            {"asset_id": "loser", "date": "2026-06-30", "last": 9, "market_cap_usd": 90},
        ]
    )
    assets = pd.DataFrame(
        [
            {"asset_id": "winner", "name": "Winner", "ticker": "WIN", "category": "watches"},
            {"asset_id": "loser", "name": "Loser", "ticker": "LOSE", "category": "watches"},
        ]
    )

    result = build_index_from_selection(prices, weighting_method="equal")
    summary = summarize_contributions(result.contributions, assets)
    index_move = result.series.iloc[-1]["index_level"] - result.series.iloc[0]["index_level"]

    assert summary["contribution_points"].sum() == pytest.approx(index_move)
    assert summary.iloc[0]["ticker"] == "WIN"
    assert summary.iloc[0]["contribution_points"] == pytest.approx(10.0)
    assert summary.iloc[-1]["contribution_points"] == pytest.approx(-5.0)
