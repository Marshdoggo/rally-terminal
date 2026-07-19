import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from app_data import DATA_PROCESSED, PROJECT_ROOT, processed_path


def test_app_data_resolves_repo_processed_path():
    assert PROJECT_ROOT == ROOT
    assert DATA_PROCESSED == ROOT / "data" / "processed"
    assert processed_path("assets") == ROOT / "data" / "processed" / "assets.csv"


def test_canonical_market_does_not_require_removed_processed_artifacts():
    from app_data import get_canonical_market

    market = get_canonical_market()
    assert not market.asset_master.empty
    assert not market.quarterly_prices.empty
    assert not market.exchange_history.market_cap_history.empty


def test_rebuilding_canonical_market_twice_is_deterministic():
    from alt_asset_explorer.canonical_market import build_canonical_market_data

    first = build_canonical_market_data()
    second = build_canonical_market_data()
    cols = ["date", "total_market_cap", "active_asset_count"]
    assert first.exchange_history.market_cap_history[cols].equals(second.exchange_history.market_cap_history[cols])
    assert first.current_summary.equals(second.current_summary)
