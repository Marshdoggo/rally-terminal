# Exchange Market Cap & Performance

## Feature overview

The Exchange Market Cap & Performance feature reconstructs the historical represented size, return, category mix, and data quality of the Rally exchange coverage in this repository. It is an analytical reconstruction from committed local artifacts, not a live Rally market feed.

## Required source fields

Source data comes from committed processed artifacts:

- `data/processed/canonical_asset_master.csv`: `asset_id`, `ticker`, `name`, `category`, `status`, `share_count`, `offering_date`, `offering_price_usd`.
- `data/processed/price_history.csv`: `asset_id`, `date`, `last`, `market_cap_usd`, `event_type`, `observed_at`, `period_end`, `frequency`.
- `data/processed/rally_exits.csv`: `asset_id`, `sale_date`, `sale_price` when available.

## Data flow

```text
Master Asset Registry
        +
Historical Price Observations
        +
Offering / Exit Events
        ↓
Asset-Level Historical Reconstruction
        ↓
Category Aggregation
        ↓
Exchange Aggregation
        ↓
Returns, P/L, Decomposition, Coverage
        ↓
Streamlit Dashboard and CSV Exports
```

## Calculation methodology

- **Asset market cap** = selected price × shares outstanding.
- **Price selection** uses direct same-date observations first. Reporting dates between observations use the most recent prior valid observation. Future observations are never used.
- **Offering dates** add an offering-price observation when no same-date secondary observation exists.
- **Active universe** begins at the asset offering date and removes assets after linked terminal exits when exit dates are available.
- **New issuance** is the first reconstructed market cap for an asset entering the exchange series.
- **Price effect** is period price change × shares outstanding for assets already present in the prior period.
- **Removed capital** is reserved for terminal-event removals. Current committed exit linkage is sparse, so most removals are zero until asset-level exit dates are linked.
- **Other adjustments** captures explicit reconciliation adjustments. The v1 pipeline keeps this zero unless future share-count adjustments or corrections are modeled.
- **Flow-adjusted return** is `(ending market cap - net external flow) / prior market cap - 1` where net external flow is new issuance minus removed capital plus adjustments.
- **Market-cap-weighted index** chains the flow-adjusted exchange return from 100.
- **Equal-weighted index** averages active asset returns for each reporting date and chains from 100.
- **Category decomposition** dynamically groups by the canonical category field and reconciles category market caps to total exchange market cap.
- **Coverage** distinguishes direct observations, carried-forward prices, observation age, stale assets, and direct/carried market-cap coverage.

## Rebuild commands

```bash
python3 scripts/rebuild_exchange_history.py --frequency native
python3 scripts/rebuild_exchange_history.py --frequency weekly
python3 scripts/build_dataset.py
```

The full dataset build writes the exchange outputs automatically. The standalone rebuild command is useful after manual edits when a full rebuild is not necessary.

## Manual entries and invalidation

Manual import scripts update normalized and processed source artifacts. After edits to offering date, share count, offering price, category, historical price, status, or exit data, run the standalone exchange rebuild or the full dataset build. The dashboard shows a rebuild control when exchange artifacts are missing.

## Outputs

The rebuild writes:

- `data/processed/exchange_asset_history.csv`
- `data/processed/exchange_category_history.csv`
- `data/processed/exchange_market_cap_history.csv`
- `data/processed/exchange_data_quality_report.csv`
- `data/processed/exchange_reconciliation_report.csv`
- `data/processed/exchange_validation_warnings.csv`

## Troubleshooting reconciliation errors

1. Inspect `exchange_reconciliation_report.csv` for non-zero `reconciliation_difference` rows.
2. Check assets entering that date for missing or changed share counts.
3. Check duplicate or conflicting price observations in `exchange_validation_warnings.csv`.
4. Verify exit dates and terminal values if removed capital is expected.

## Adding a category

Add or edit the asset's canonical `category` through the manual asset workflow, then rebuild. Categories are discovered dynamically; no code change is required.

## Changing thresholds

`ExchangeHistoryConfig` in `src/alt_asset_explorer/exchange_history.py` centralizes staleness days, reconciliation tolerance, exit treatment, and base index level. The Streamlit page also has display controls for maximum visible price age and optional small-category grouping.

## Running tests

```bash
pytest -q
pytest tests/test_exchange_history.py -q
```
