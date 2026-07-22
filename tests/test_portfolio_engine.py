import pandas as pd
import pytest

from alt_asset_explorer.portfolio_engine import PortfolioDefinition, simulate_portfolio


def _assets():
    return pd.DataFrame(
        [
            {"asset_id": "a", "ticker": "A", "name": "Asset A", "category": "art", "offering_date": "2025-01-01", "share_count": 100, "offering_price_usd": 10},
            {"asset_id": "b", "ticker": "B", "name": "Asset B", "category": "books", "offering_date": "2025-04-01", "share_count": 100, "offering_price_usd": 20},
        ]
    )


def test_equal_weight_portfolio_keeps_unlaunched_weight_as_cash_until_rebalance():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2025-01-01", "last": 10},
            {"asset_id": "a", "date": "2025-04-01", "last": 12},
            {"asset_id": "b", "date": "2025-04-01", "last": 20},
        ]
    )
    definition = PortfolioDefinition(
        name="Two Asset Basket",
        asset_ids=("a", "b"),
        weighting_method="equal_weight",
        rebalance_frequency="quarterly",
        start_date="2025-01-01",
        end_date="2025-04-01",
    )

    result = simulate_portfolio(definition, _assets(), prices)

    assert result.series.iloc[0]["cash_value"] == pytest.approx(50.0)
    assert result.series.iloc[-1]["portfolio_value"] == pytest.approx(110.0)
    assert result.series.iloc[-1]["cumulative_return"] == pytest.approx(0.10)
    assert result.series.iloc[-1]["rebalance_frequency"] == "quarterly"
    assert result.series.iloc[-1]["asset_entry_policy"] == "enter_on_rebalance_when_eligible"


def test_buy_and_hold_weights_drift_and_do_not_enter_late_assets_without_rebalance():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2025-01-01", "last": 10},
            {"asset_id": "a", "date": "2025-04-01", "last": 12},
            {"asset_id": "b", "date": "2025-04-01", "last": 20},
        ]
    )
    definition = PortfolioDefinition(
        name="Buy Hold Basket",
        asset_ids=("a", "b"),
        rebalance_frequency="none",
        start_date="2025-01-01",
        end_date="2025-04-01",
    )

    result = simulate_portfolio(definition, _assets(), prices)

    assert result.series.iloc[-1]["portfolio_value"] == pytest.approx(110.0)
    latest_constituents = result.constituents[result.constituents["date"].eq(pd.Timestamp("2025-04-01"))]
    assert latest_constituents.loc[latest_constituents["asset_id"].eq("b"), "units_held"].iloc[0] == pytest.approx(0.0)


def test_exit_proceeds_are_held_as_cash_until_next_rebalance():
    assets = _assets().iloc[:1].copy()
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2025-01-01", "last": 10},
            {"asset_id": "a", "date": "2025-03-01", "last": 15},
        ]
    )
    exits = pd.DataFrame(
        [
            {"asset_id": "a", "ticker": "A", "exit_type": "buyout", "exit_status": "settled", "sale_date": "2025-03-01", "exit_effective_date": "2025-03-01", "settlement_date": "2025-03-01", "exit_price_per_share": 15, "shares_at_exit": 100, "is_confirmed": True}
        ]
    )
    definition = PortfolioDefinition(name="Exit Basket", asset_ids=("a",), start_date="2025-01-01", end_date="2025-04-01")

    result = simulate_portfolio(definition, assets, prices, exits)

    assert result.series.iloc[-1]["portfolio_value"] == pytest.approx(150.0)
    assert result.series.iloc[-1]["cash_value"] == pytest.approx(150.0)
    assert result.series.iloc[-1]["active_constituent_count"] == 0


def test_current_survivors_policy_excludes_exited_assets():
    assets = _assets().iloc[:1].copy()
    prices = pd.DataFrame([{"asset_id": "a", "date": "2025-01-01", "last": 10}])
    exits = pd.DataFrame([{"asset_id": "a", "ticker": "A", "exit_type": "buyout", "exit_status": "settled", "sale_date": "2025-03-01", "exit_effective_date": "2025-03-01", "exit_price_per_share": 15, "shares_at_exit": 100, "is_confirmed": True}])
    definition = PortfolioDefinition(name="Survivors", asset_ids=("a",), universe_policy="current_survivors_only")

    result = simulate_portfolio(definition, assets, prices, exits)

    assert result.series.empty
    assert any("Excluded exited assets" in warning for warning in result.warnings)
