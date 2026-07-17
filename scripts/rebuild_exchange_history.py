from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.exchange_history import rebuild_exchange_history


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Rally exchange market-cap analytics.")
    parser.add_argument("--frequency", choices=["native", "weekly", "monthly", "quarterly"], default="native")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--asset-id", action="append", dest="asset_ids")
    args = parser.parse_args()
    result = rebuild_exchange_history(start_date=args.start_date, end_date=args.end_date, frequency=args.frequency, asset_ids=args.asset_ids, force=True)
    print(f"wrote {len(result.market_cap_history):,} exchange rows, {len(result.category_history):,} category rows, {len(result.asset_history):,} asset-date rows")


if __name__ == "__main__":
    main()
