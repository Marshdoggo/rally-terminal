from __future__ import annotations

import pandas as pd

from alt_asset_explorer.exchange_history import ExchangeHistoryConfig, rebuild_exchange_history, validate_exchange_inputs


def assets() -> pd.DataFrame:
    return pd.DataFrame([
        {"asset_id": "a", "ticker": "A", "name": "Alpha", "category": "cars", "share_count": 10, "offering_date": "2020-01-01", "offering_price_usd": 10, "status": "trading"},
        {"asset_id": "b", "ticker": "B", "name": "Beta", "category": "watches", "share_count": 5, "offering_date": "2020-01-15", "offering_price_usd": 20, "status": "trading"},
    ])


def prices() -> pd.DataFrame:
    return pd.DataFrame([
        {"asset_id": "a", "date": "2020-01-01", "last": 10, "event_type": "offering_price"},
        {"asset_id": "a", "date": "2020-01-08", "last": 12, "event_type": "chart_observation"},
        {"asset_id": "a", "date": "2020-01-22", "last": 12, "event_type": "chart_observation"},
        {"asset_id": "b", "date": "2020-01-15", "last": 20, "event_type": "offering_price"},
        {"asset_id": "b", "date": "2020-01-22", "last": 22, "event_type": "chart_observation"},
    ])


def test_constant_and_appreciating_assets_with_issuance_and_reconciliation(tmp_path):
    result = rebuild_exchange_history(assets(), prices(), pd.DataFrame(), frequency="native", output_dir=tmp_path)
    total = result.market_cap_history.set_index(pd.to_datetime(result.market_cap_history["date"]))
    assert total.loc[pd.Timestamp("2020-01-01"), "total_market_cap"] == 100
    assert total.loc[pd.Timestamp("2020-01-08"), "price_effect"] == 20
    assert total.loc[pd.Timestamp("2020-01-15"), "new_issuance"] == 100
    assert total.loc[pd.Timestamp("2020-01-15"), "assets_added_count"] == 1
    assert "B — Beta ($100)" in total.loc[pd.Timestamp("2020-01-15"), "assets_added_since_last_plot"]
    assert total.loc[pd.Timestamp("2020-01-08"), "assets_added_since_last_plot"] == "None"
    assert total["reconciles"].all()
    assert total.loc[pd.Timestamp("2020-01-15"), "period_return"] == 0


def test_categories_reconcile_and_direct_carried_forward_flags(tmp_path):
    result = rebuild_exchange_history(assets(), prices(), pd.DataFrame(), frequency="weekly", output_dir=tmp_path)
    cat_sum = result.category_history.groupby("date")["category_market_cap"].sum().reset_index()
    merged = result.market_cap_history[["date", "total_market_cap"]].merge(cat_sum, on="date")
    assert (merged["total_market_cap"].round(6) == merged["category_market_cap"].round(6)).all()
    row = result.asset_history[(pd.to_datetime(result.asset_history["date"]) == pd.Timestamp("2020-01-17")) & (result.asset_history["asset_id"].eq("a"))].iloc[0]
    assert row["price_source"] == "carried_forward"
    assert not bool(row["is_direct_observation"])


def test_no_lookahead_before_offering_and_staleness(tmp_path):
    result = rebuild_exchange_history(assets().iloc[[1]], prices(), pd.DataFrame(), frequency="weekly", output_dir=tmp_path, config=ExchangeHistoryConfig(staleness_days=1))
    assert result.asset_history["date"].min() >= pd.Timestamp("2020-01-15")
    assert result.asset_history["is_stale"].any()


def test_exit_removes_asset_after_sale_date(tmp_path):
    exits = pd.DataFrame([{"asset_id": "a", "sale_date": "2020-01-08", "sale_price": 12}])
    result = rebuild_exchange_history(assets().iloc[[0]], prices(), exits, frequency="weekly", output_dir=tmp_path)
    assert result.asset_history["date"].max() <= pd.Timestamp("2020-01-08")


def test_invalid_and_duplicate_data_are_flagged(tmp_path):
    bad_assets = assets()
    bad_assets.loc[0, "share_count"] = -1
    bad_prices = pd.concat([prices(), prices().iloc[[1]]], ignore_index=True)
    warnings = validate_exchange_inputs(bad_assets, bad_prices, pd.DataFrame())
    assert "non_positive_share_count" in set(warnings["warning"])
    # duplicate rows are de-duplicated for calculation, but validation remains non-blocking
    result = rebuild_exchange_history(bad_assets, bad_prices, pd.DataFrame(), frequency="monthly", output_dir=tmp_path)
    assert not result.market_cap_history.empty


def test_empty_and_single_date_dataset(tmp_path):
    empty = rebuild_exchange_history(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), output_dir=tmp_path)
    assert empty.market_cap_history.empty
    one = rebuild_exchange_history(assets().iloc[[0]], prices().iloc[[0]], pd.DataFrame(), output_dir=tmp_path)
    assert len(one.market_cap_history) == 1
    assert one.market_cap_history.iloc[0]["return_index"] == 100


def test_historical_edit_recalculates_from_changed_input(tmp_path):
    base = rebuild_exchange_history(assets(), prices(), pd.DataFrame(), output_dir=tmp_path / "base")
    edited_prices = prices().copy(); edited_prices.loc[1, "last"] = 15
    edited = rebuild_exchange_history(assets(), edited_prices, pd.DataFrame(), output_dir=tmp_path / "edited")
    assert edited.market_cap_history.loc[1, "total_market_cap"] > base.market_cap_history.loc[1, "total_market_cap"]


def test_frequency_outputs(tmp_path):
    for freq in ["native", "weekly", "monthly", "quarterly"]:
        result = rebuild_exchange_history(assets(), prices(), pd.DataFrame(), frequency=freq, output_dir=tmp_path / freq)
        assert set(result.market_cap_history["frequency"]) == {freq}

from alt_asset_explorer.total_return import TotalReturnConfig, build_total_return_indexes, normalize_exit_events


def two_asset_example_assets() -> pd.DataFrame:
    return pd.DataFrame([
        {"asset_id": "a", "ticker": "A", "name": "Alpha", "category": "cars", "share_count": 1, "offering_date": "2020-01-01", "offering_price_usd": 50, "status": "trading"},
        {"asset_id": "b", "ticker": "B", "name": "Beta", "category": "cars", "share_count": 1, "offering_date": "2020-01-01", "offering_price_usd": 50, "status": "trading"},
    ])


def test_two_asset_hand_calculated_exit_total_return_vs_tradable_market_cap(tmp_path):
    a = two_asset_example_assets()
    p = pd.DataFrame([
        {"asset_id": "a", "date": "2020-01-01", "last": 50, "event_type": "offering_price"},
        {"asset_id": "b", "date": "2020-01-01", "last": 50, "event_type": "offering_price"},
        {"asset_id": "a", "date": "2020-02-01", "last": 100, "event_type": "chart_observation"},
        {"asset_id": "b", "date": "2020-02-01", "last": 50, "event_type": "chart_observation"},
    ])
    e = pd.DataFrame([{"asset_id": "a", "sale_date": "2020-02-01", "exit_price_per_share": 100, "exit_status": "settled", "exit_type": "buyout"}])
    port, const, exits, analytics = build_total_return_indexes(a, p, e, frequency="native", config=TotalReturnConfig(rebalance_frequency="monthly"))
    full_eq = port[(port["category"].eq("all")) & (port["weighting_method"].eq("equal_weight"))].sort_values("date")
    assert full_eq.iloc[0]["index_level"] == 100
    assert round(float(full_eq.iloc[-1]["index_level"]), 6) == 150
    result = rebuild_exchange_history(a, p, e, frequency="native", output_dir=tmp_path)
    latest_mcap = result.market_cap_history.sort_values("date").iloc[-1]["total_market_cap"]
    assert latest_mcap == 50
    assert result.market_cap_history.sort_values("date").iloc[-1]["removed_capital"] == 100


def test_exit_price_hierarchy_cancelled_and_fallback_last_trade():
    a = assets()
    p = prices()
    e = pd.DataFrame([
        {"asset_id": "a", "sale_date": "2020-01-22", "exit_total_value": 130, "shares_at_exit": 10, "exit_status": "settled"},
        {"asset_id": "b", "sale_date": "2020-01-22", "exit_price_per_share": 50, "exit_status": "cancelled_exit"},
        {"asset_id": "b", "sale_date": "2020-01-22", "exit_status": "settled"},
    ])
    norm = normalize_exit_events(a, e, p)
    assert norm.loc[norm["asset_id"].eq("a"), "terminal_price"].iloc[0] == 13
    assert pd.isna(norm.loc[norm["exit_status"].eq("cancelled_exit"), "terminal_price"].iloc[0])
    fallback = norm[(norm["asset_id"].eq("b")) & (norm["exit_status"].eq("settled"))].iloc[0]
    assert fallback["terminal_price"] == 22
    assert fallback["terminal_price_source"] == "last_valid_secondary_market_price"


def test_pending_settlement_cash_reinvests_at_next_monthly_rebalance():
    a = assets()
    p = pd.concat([prices(), pd.DataFrame([{"asset_id": "a", "date": "2020-02-28", "last": 12, "event_type": "chart_observation"}, {"asset_id": "b", "date": "2020-02-28", "last": 22, "event_type": "chart_observation"}])], ignore_index=True)
    e = pd.DataFrame([{"asset_id": "a", "sale_date": "2020-01-22", "settlement_date": "2020-02-15", "exit_price_per_share": 12, "exit_status": "pending_settlement"}])
    port, _, _, _ = build_total_return_indexes(a, p, e, frequency="native", config=TotalReturnConfig(rebalance_frequency="monthly"))
    full = port[(port["category"].eq("all")) & (port["weighting_method"].eq("equal_weight"))].sort_values("date")
    assert full["pending_settlement_value"].max() >= 100
    assert full.iloc[-1]["cash_value"] == 0
    assert full.iloc[-1]["active_constituent_count"] == 1


def test_cap_weight_and_equal_weight_differ_with_unequal_market_caps():
    a = assets()
    a.loc[1, "offering_date"] = "2020-01-01"
    a.loc[1, "share_count"] = 20
    p = prices()
    port, _, _, _ = build_total_return_indexes(a, p, pd.DataFrame(), frequency="weekly", config=TotalReturnConfig(rebalance_frequency="weekly"))
    latest = port[port["category"].eq("all")].sort_values("date").groupby("weighting_method").tail(1).set_index("weighting_method")
    assert latest.loc["equal_weight", "index_level"] != latest.loc["market_cap_weight", "index_level"]


def test_default_total_return_rebalance_is_quarterly():
    config = TotalReturnConfig()
    assert config.rebalance_frequency == "quarterly"


def test_equal_weight_rebalancing_harvests_rise_then_fall_path():
    a = pd.DataFrame([
        {"asset_id": "a", "ticker": "A", "name": "Alpha", "category": "synthetic", "share_count": 1, "offering_date": "2020-01-01", "offering_price_usd": 100, "status": "trading"},
        {"asset_id": "b", "ticker": "B", "name": "Beta", "category": "synthetic", "share_count": 1, "offering_date": "2020-01-01", "offering_price_usd": 100, "status": "trading"},
    ])
    p = pd.DataFrame([
        {"asset_id": "a", "date": "2020-01-01", "last": 100, "event_type": "offering_price"},
        {"asset_id": "b", "date": "2020-01-01", "last": 100, "event_type": "offering_price"},
        {"asset_id": "a", "date": "2020-02-01", "last": 200, "event_type": "chart_observation"},
        {"asset_id": "b", "date": "2020-02-01", "last": 100, "event_type": "chart_observation"},
        {"asset_id": "a", "date": "2020-03-01", "last": 100, "event_type": "chart_observation"},
        {"asset_id": "b", "date": "2020-03-01", "last": 100, "event_type": "chart_observation"},
    ])
    port, _, _, _ = build_total_return_indexes(
        a,
        p,
        pd.DataFrame(),
        frequency="native",
        config=TotalReturnConfig(rebalance_frequency="monthly"),
    )
    full = port[(port["category"].eq("all")) & (port["weighting_method"].eq("equal_weight"))].sort_values("date")
    assert full.iloc[-1]["index_level"] == 112.5

    buy_and_hold_final = 100 * (0.5 * (100 / 100) + 0.5 * (100 / 100))
    assert buy_and_hold_final == 100
