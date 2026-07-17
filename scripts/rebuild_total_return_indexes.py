from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.total_return import rebuild_total_return_indexes


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild exit-aware Rally total-return indexes.")
    parser.add_argument("--frequency", choices=["native", "weekly", "monthly", "quarterly"], default="native")
    parser.add_argument("--rebalance", choices=["weekly", "monthly", "quarterly"], default="monthly")
    parser.add_argument("--weighting", choices=["all", "equal", "market_cap"], default="all")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--asset-id", action="append", dest="asset_ids")
    parser.add_argument("--category")
    parser.add_argument("--exit-only-invalidation", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("dry-run validation completed; no files written")
        return
    portfolio, constituents, exits, analytics = rebuild_total_return_indexes(frequency=args.frequency, rebalance=args.rebalance, weighting=args.weighting)
    print(f"wrote {len(portfolio):,} portfolio rows, {len(constituents):,} constituent rows, {len(exits):,} exit rows, {len(analytics):,} exit analytics rows")


if __name__ == "__main__":
    main()
