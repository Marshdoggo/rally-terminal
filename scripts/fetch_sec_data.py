from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.connectors.sec_edgar import EdgarClient, build_sec_outputs
from alt_asset_explorer.paths import DATA_PROCESSED, ensure_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache SEC EDGAR filings for Rally/RSE issuers.")
    parser.add_argument("--max-filings", type=int, default=40, help="Maximum qualifying filings per issuer to fetch.")
    args = parser.parse_args()

    ensure_dirs()
    client = EdgarClient.from_env()
    series, exits = build_sec_outputs(client, max_filings=args.max_filings)
    series.to_csv(DATA_PROCESSED / "rally_sec_series.csv", index=False)
    exits.to_csv(DATA_PROCESSED / "rally_exits.csv", index=False)
    print(f"Fetched SEC series rows: {len(series)}")
    print(f"Fetched SEC exit rows: {len(exits)}")
    print(f"Cache directory: {client.cache_dir}")


if __name__ == "__main__":
    main()
