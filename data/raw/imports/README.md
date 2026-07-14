# User-Provided Imports

Drop permitted exports or manually reviewed CSVs in this folder, then run:

```bash
python3 scripts/build_dataset.py
```

Supported files:

- `rally_snapshots.csv`: current Rally bid, ask, last price, volume, and market-cap observations.
- `handbags_comps.csv`: handbag resale or auction comparable sales.
- `watches_comps.csv`: watch resale or auction comparable sales.
- `sothebys_results.csv`: user-reviewed Sotheby's auction result rows.
- `christies_results.csv`: user-reviewed Christie's auction result rows.
- `phillips_results.csv`: user-reviewed Phillips auction result rows.
- `fashionphile_listings.csv`: user-reviewed Fashionphile listing or sold rows.
- `chrono24_market_data.csv`: Chrono24 market/index/appraisal context rows.

Use the `*_template.csv` files as column guides. Rows are validated before they enter processed outputs.

Auction-house rows require price, date, and source URL. Fashionphile active listings are treated as lower-confidence ask comps unless marked sold. Chrono24 index rows are processed into `market_context.csv`, not direct comparable sales.

## Sotheby's Capture Workflow

Sotheby's does not expose a simple CSV export from auction result pages. The supported workaround is to capture visible result text yourself and let the local importer convert it into `sothebys_results.csv`.

1. Open a closed Sotheby's auction result page, such as a handbag or watch auction.
2. Use list view if possible, then copy the visible lot text for one result page at a time.
3. Paste that text into a file under `data/raw/captures/`, for example:

```text
data/raw/captures/sothebys_handbags_2026_06_page_1.txt
```

4. Run the capture importer:

```bash
python3 scripts/import_sothebys_capture.py data/raw/captures/sothebys_handbags_2026_06_page_1.txt \
  --auction-name "Handbags and Trunks: Including Property of An Important Private Collector" \
  --auction-url "https://www.sothebys.com/en/buy/auction/2026/handbags-and-accessories-3?locale=en&lotFilter=AllLots" \
  --sale-date 2026-06-23 \
  --venue "New York" \
  --brand-filter Hermes \
  --output data/raw/imports/sothebys_results.csv
```

For additional pages from the same auction, add `--append` so the importer keeps existing rows:

```bash
python3 scripts/import_sothebys_capture.py data/raw/captures/sothebys_handbags_2026_06_page_2.txt \
  --auction-name "Handbags and Trunks: Including Property of An Important Private Collector" \
  --auction-url "https://www.sothebys.com/en/buy/auction/2026/handbags-and-accessories-3?locale=en&lotFilter=AllLots" \
  --sale-date 2026-06-23 \
  --venue "New York" \
  --brand-filter Hermes \
  --output data/raw/imports/sothebys_results.csv \
  --append
```

5. Rebuild processed data:

```bash
python3 scripts/build_dataset.py
```

The importer treats Sotheby's realized prices as `realized_with_premium` because Sotheby's states that listed results include Sotheby's premiums unless otherwise noted. Keep the auction URL and sale date attached so every comp remains auditable.
