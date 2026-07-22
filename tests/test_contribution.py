import pytest
import pandas as pd

from alt_asset_explorer.contribution import attribution_from_index_result, attribution_from_portfolio_result, breadth_metrics, concentration_metrics
from alt_asset_explorer.indices import build_index_from_selection
from alt_asset_explorer.custom_portfolios import PortfolioDefinition, PortfolioMethodology, simulate_portfolio


def _assets():
    return pd.DataFrame([
        {"asset_id": "a", "ticker": "AAA", "name": "Alpha", "category": "watches", "offering_date": "2020-01-01", "share_count": 100, "offering_price_usd": 10, "status": "active_tradable"},
        {"asset_id": "b", "ticker": "BBB", "name": "Beta", "category": "watches", "offering_date": "2020-01-01", "share_count": 100, "offering_price_usd": 10, "status": "active_tradable"},
        {"asset_id": "x", "ticker": "XXX", "name": "Exited", "category": "fossils", "offering_date": "2020-01-01", "share_count": 100, "offering_price_usd": 10, "status": "exited"},
    ])


def _prices():
    return pd.DataFrame([
        {"asset_id": "a", "date": "2020-01-01", "last": 10, "market_cap_usd": 1000},
        {"asset_id": "b", "date": "2020-01-01", "last": 10, "market_cap_usd": 3000},
        {"asset_id": "x", "date": "2020-01-01", "last": 10, "market_cap_usd": 1000},
        {"asset_id": "a", "date": "2020-04-01", "last": 12, "market_cap_usd": 1200},
        {"asset_id": "b", "date": "2020-04-01", "last": 9, "market_cap_usd": 2700},
        {"asset_id": "x", "date": "2020-04-01", "last": 8, "market_cap_usd": 800},
        {"asset_id": "a", "date": "2020-07-01", "last": 15, "market_cap_usd": 1500},
        {"asset_id": "b", "date": "2020-07-01", "last": 11, "market_cap_usd": 3300},
        {"asset_id": "x", "date": "2020-07-01", "last": 7, "market_cap_usd": 700},
    ])


def test_index_attribution_reconciles_and_ranks():
    idx = build_index_from_selection(_prices(), asset_ids=["a", "b"], weighting_method="equal")
    result = attribution_from_index_result(idx, _assets(), target_name="Watches")
    assert result.reconciles
    assert result.reconciliation_metadata["asset_contribution_sum"] + result.residual == pytest.approx(result.total_change)
    assert result.constituent_contributions.iloc[0]["asset_id"] == "a"
    assert result.constituent_contributions.sort_values("contribution").iloc[0]["asset_id"] == "b"


def test_date_window_changes_attribution():
    idx = build_index_from_selection(_prices(), asset_ids=["a", "b"], weighting_method="equal")
    full = attribution_from_index_result(idx, _assets(), target_name="Watches")
    short = attribution_from_index_result(idx, _assets(), target_name="Watches", start_date="2020-04-01")
    assert short.reconciles
    assert full.total_change != pytest.approx(short.total_change)


def test_market_cap_weighting_matches_engine_move():
    idx = build_index_from_selection(_prices(), asset_ids=["a", "b"], weighting_method="market_cap")
    result = attribution_from_index_result(idx, _assets(), target_name="Market Cap Watches")
    assert result.reconciles
    assert result.constituent_contributions["contribution"].sum() + result.residual == pytest.approx(result.total_change)


def test_full_market_and_category_work():
    market = attribution_from_index_result(build_index_from_selection(_prices(), weighting_method="equal"), _assets(), target_name="Full Rally Market")
    category = attribution_from_index_result(build_index_from_selection(_prices(), asset_ids=["a", "b"], weighting_method="equal"), _assets(), target_name="Watches")
    assert market.reconciles and category.reconciles
    assert len(market.constituent_contributions) == 3
    assert len(category.constituent_contributions) == 2


def test_portfolio_attribution_uses_holdings_and_reconciles_rebalance_cash():
    definition = PortfolioDefinition(name="Custom Portfolio", asset_ids=("a", "b"), methodology=PortfolioMethodology(weighting_method="equal_weight", rebalance_frequency="quarterly", universe_policy="include_exited"), base_value=100)
    sim = simulate_portfolio(definition, _assets(), _prices())
    result = attribution_from_portfolio_result(sim, _assets())
    assert result.reconciles
    assert result.constituent_contributions["contribution"].sum() + result.cash_contribution + result.residual == pytest.approx(result.total_change)
    assert not result.constituent_contributions.empty


def test_universe_survivor_vs_exited_inputs_match_selection():
    prices = _prices(); assets = _assets()
    include = attribution_from_index_result(build_index_from_selection(prices, weighting_method="equal"), assets, target_name="All")
    survivors = attribution_from_index_result(build_index_from_selection(prices, asset_ids=["a", "b"], weighting_method="equal"), assets, target_name="Survivors")
    assert "x" in set(include.constituent_contributions["asset_id"])
    assert "x" not in set(survivors.constituent_contributions["asset_id"])


def test_concentration_and_breadth_denominators():
    c = pd.DataFrame({"contribution": [4.0, 3.0, -2.0, 0.0]})
    conc = concentration_metrics(c); breadth = breadth_metrics(c)
    assert conc["positive_top_1"] == pytest.approx(4/7)
    assert conc["negative_top_1"] == pytest.approx(1.0)
    assert conc["absolute_top_3"] == pytest.approx(1.0)
    assert breadth == {"positive_count": 2, "negative_count": 1, "flat_count": 1, "total_count": 4, "percent_positive": 0.5}


def test_insufficient_history_is_graceful():
    idx = build_index_from_selection(_prices().head(1), weighting_method="equal")
    result = attribution_from_index_result(idx, _assets(), target_name="Too Short")
    assert not result.reconciles
    assert result.constituent_contributions.empty
    assert result.warnings
