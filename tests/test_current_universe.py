import pandas as pd

from alt_asset_explorer.current_universe import build_current_asset_universe, calculate_current_universe_summary


def test_current_universe_excludes_fixture_exited_offering_only_and_stale_rows():
    assets = pd.DataFrame([
        {"asset_id":"a","ticker":"A","status":"trading","platform":"Rally","record_environment":"production"},
        {"asset_id":"b","ticker":"B","status":"sold","platform":"Rally","record_environment":"production"},
        {"asset_id":"c","ticker":"C","status":"trading","platform":"Rally","record_environment":"fixture"},
        {"asset_id":"d","ticker":"D","status":"trading","platform":"Rally","record_environment":"production"},
        {"asset_id":"e","ticker":"E","status":"trading","platform":"Rally","record_environment":"production"},
    ])
    hist = pd.DataFrame([
        {"date":"2026-01-31","asset_id":"a","ticker":"A","category":"watches","price":10,"shares_outstanding":100,"price_source":"observed_price","observation_age_days":0,"is_direct_observation":True,"is_stale":False},
        {"date":"2026-01-31","asset_id":"b","ticker":"B","category":"watches","price":10,"shares_outstanding":100,"price_source":"observed_price","observation_age_days":0,"is_direct_observation":True,"is_stale":False},
        {"date":"2026-01-31","asset_id":"c","ticker":"C","category":"watches","price":10,"shares_outstanding":100,"price_source":"observed_price","observation_age_days":0,"is_direct_observation":True,"is_stale":False},
        {"date":"2026-01-31","asset_id":"d","ticker":"D","category":"watches","price":10,"shares_outstanding":100,"price_source":"offering_price","observation_age_days":0,"is_direct_observation":False,"is_stale":False},
        {"date":"2026-01-31","asset_id":"e","ticker":"E","category":"watches","price":10,"shares_outstanding":100,"price_source":"carried_forward","observation_age_days":121,"is_direct_observation":False,"is_stale":True},
    ])
    universe = build_current_asset_universe(assets, hist)
    assert universe["asset_id"].tolist() == ["a"]
    summary = calculate_current_universe_summary(universe)
    assert summary["tradable_asset_count"] == 1
    assert summary["tradable_market_cap"] == 1000


def test_repository_current_summary_reconciles_canonical_market_calculation():
    from alt_asset_explorer.canonical_market import build_canonical_market_data

    market = build_canonical_market_data()
    universe = market.current_universe
    summary = market.current_summary.iloc[0].to_dict()
    assert summary["tradable_asset_count"] == universe["asset_id"].nunique()
    assert round(summary["tradable_market_cap"], 2) == round(universe["canonical_market_cap"].sum(), 2)
    assert summary["tradable_market_cap"] <= market.exchange_history.market_cap_history.iloc[-1]["total_market_cap"]
