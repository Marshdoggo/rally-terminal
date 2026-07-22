import pandas as pd

from alt_asset_explorer.custom_portfolios import PortfolioDefinition, PortfolioMethodology, simulate_portfolio


def _assets():
    return pd.DataFrame([
        {"asset_id": "a", "ticker": "A", "name": "A", "category": "fossils", "status": "trading", "offering_date": "2020-01-01", "share_count": 10, "offering_price_usd": 10},
        {"asset_id": "b", "ticker": "B", "name": "B", "category": "fossils", "status": "trading", "offering_date": "2020-01-01", "share_count": 10, "offering_price_usd": 20},
    ])


def _prices():
    return pd.DataFrame([
        {"asset_id": "a", "date": "2020-03-31", "last": 10},
        {"asset_id": "b", "date": "2020-03-31", "last": 20},
        {"asset_id": "a", "date": "2020-06-30", "last": 20},
        {"asset_id": "b", "date": "2020-06-30", "last": 20},
    ])


def test_equal_weight_custom_portfolio_simulates_growth():
    definition = PortfolioDefinition(
        name="Test",
        asset_ids=("a", "b"),
        methodology=PortfolioMethodology(weighting_method="equal_weight", rebalance_frequency="quarterly"),
    )

    result = simulate_portfolio(definition, _assets(), _prices(), pd.DataFrame())

    assert result.warnings == ()
    assert not result.series.empty
    assert round(float(result.series.iloc[-1]["index_level"]), 2) == 150.00
    assert result.methodology.missing_price_policy == "carry_forward"


def test_custom_weight_definition_validates_weights():
    definition = PortfolioDefinition(
        name="Weighted",
        asset_ids=("a", "b"),
        methodology=PortfolioMethodology(weighting_method="custom_weight", rebalance_frequency="none", universe_policy="include_exited"),
        custom_weights={"a": 0.25, "b": 0.75},
    )

    result = simulate_portfolio(definition, _assets(), _prices(), pd.DataFrame())

    assert not result.series.empty
    assert float(result.series.iloc[-1]["index_level"]) > 100
    assert result.methodology.rebalance_frequency == "none"
