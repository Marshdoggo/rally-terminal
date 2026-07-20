import pandas as pd

from alt_asset_explorer.canonical_market import build_canonical_market_data
from alt_asset_explorer.indices import build_index_from_selection, prepare_quarterly_observations
from alt_asset_explorer.universe import build_asset_universe, build_asset_universe_diagnostics, eligible_asset_ids

REPRESENTATIVE_EXIT_AWARE_ASSETS = {
    "rally-deaton": "fossils",
    "rally-faubourg2": "handbags",
    "rally-birkinblu": "handbags",
    "rally-7orlex": "watches",
    "rally-aproak": "watches",
    "rally-17dujac": "wine and whiskey",
}


def _market():
    return build_canonical_market_data(as_of=pd.Timestamp("2026-07-20").date())


def test_exit_aware_representative_assets_have_traceable_universe_fate():
    market = _market()
    observations = prepare_quarterly_observations(market.quarterly_prices, market.asset_master)
    diagnostics = build_asset_universe_diagnostics(
        market.asset_master,
        observations,
        market.exit_events,
        include_exited=True,
    ).set_index("asset_id")

    for asset_id, category in REPRESENTATIVE_EXIT_AWARE_ASSETS.items():
        row = diagnostics.loc[asset_id]
        assert row["category"] == category
        assert row["has_price_history"]
        assert row["quarterly_eligible"]
        assert row["equal_weight_eligible"]
        assert row["market_cap_weight_eligible"]
        assert row["exclusion_reason"] == "included"


def test_active_only_excludes_exited_assets_but_include_exited_keeps_them():
    market = _market()
    observations = prepare_quarterly_observations(market.quarterly_prices, market.asset_master)

    active_only = build_asset_universe(market.asset_master, observations, include_exited=False, require_price_history=True)
    exit_aware = build_asset_universe(market.asset_master, observations, include_exited=True, require_price_history=True)

    active_ids = set(eligible_asset_ids(active_only))
    exit_aware_ids = set(eligible_asset_ids(exit_aware))

    for asset_id in REPRESENTATIVE_EXIT_AWARE_ASSETS:
        if asset_id != "rally-deaton":
            assert asset_id not in active_ids
        assert asset_id in exit_aware_ids


def test_category_universe_propagates_from_source_data_without_static_lists():
    assets = pd.DataFrame(
        [
            {"asset_id": "new-bag", "ticker": "NEWBAG", "name": "New Bag", "category": "handbags", "status": "sold", "platform": "Rally", "record_environment": "production"},
        ]
    )
    prices = pd.DataFrame(
        [
            {"asset_id": "new-bag", "date": "2024-03-31", "last": 10, "market_cap_usd": 10000},
            {"asset_id": "new-bag", "date": "2024-06-30", "last": 12, "market_cap_usd": 12000},
        ]
    )

    universe = build_asset_universe(assets, prices, categories=["handbags"], include_exited=True, require_price_history=True)

    assert eligible_asset_ids(universe) == ["new-bag"]


def test_index_constituent_count_matches_assets_used_at_each_observation():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2024-03-31", "last": 10, "market_cap_usd": 100},
            {"asset_id": "a", "date": "2024-06-30", "last": 11, "market_cap_usd": 110},
            {"asset_id": "b", "date": "2024-06-30", "last": 20, "market_cap_usd": 200},
        ]
    )

    series = build_index_from_selection(prices, asset_ids=["a", "b"]).series

    actual_counts = prices.groupby("date")["asset_id"].nunique().astype(int).to_dict()
    for _, row in series.iterrows():
        assert int(row["constituent_count"]) == actual_counts[row["date"]]


def test_total_return_scopes_include_representative_exits_only_in_exit_aware_scope():
    market = _market()
    portfolio = market.total_return_portfolio
    constituents = market.total_return_constituents

    assert {"include_exited", "active_only"}.issubset(set(portfolio["universe_scope"]))
    exit_scope_ids = set(constituents.loc[constituents["universe_scope"].eq("include_exited"), "asset_id"].astype(str))
    active_scope_ids = set(constituents.loc[constituents["universe_scope"].eq("active_only"), "asset_id"].astype(str))

    for asset_id in REPRESENTATIVE_EXIT_AWARE_ASSETS:
        assert asset_id in exit_scope_ids
        if asset_id != "rally-deaton":
            assert asset_id not in active_scope_ids
