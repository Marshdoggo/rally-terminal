# Rally Terminal Project Context

Last audited: 2026-07-19  
Verification baseline: Python 3.11, Streamlit 1.51.0, pandas 2.3.3, lxml 6.1.1

## Purpose And Product State

Rally Terminal is a Python and Streamlit research application for fractionalized collectible assets. It combines manually researched Rally asset and quarterly-price observations, SEC offering and exit context, secondary-market comparable sales, prototype indices, liquidity and valuation research, and deterministic report/export outputs. It is research software, not a trading system or appraisal service.

The homepage is the primary product surface. It includes research coverage, sector performance, built-in and saved index exploration, constituent attribution, single-asset price history, a custom-index workshop, and a filterable Rally market table. Additional pages cover Rally assets, category research, comparable sales, exits, liquidity, report context, exports, and broader asset-universe diagnostics.

## Architecture And Entry Points

- `app/Home.py` is the Streamlit entrypoint; `app/pages/` contains the multipage views.
- `src/alt_asset_explorer/` contains schemas, connectors, normalization, research, index, valuation, scoring, export, and storage logic.
- `scripts/build_dataset.py` builds processed application artifacts from repository data.
- `scripts/process_manual_research.py` validates and imports manual asset and price research before rebuilding the dataset.
- `scripts/build_research_coverage.py` creates asset-level coverage reports.
- `scripts/fetch_sec_data.py` refreshes the local SEC cache when an appropriate SEC user agent is configured.
- `scripts/write_report.py --date today` writes a deterministic Markdown market report.
- `scripts/rebuild_exchange_history.py` rebuilds exchange market-cap, category, return, decomposition, coverage, and reconciliation artifacts.

The application has no API server or database. Runtime storage is CSV/JSON on the local filesystem. Streamlit pages read committed artifacts from `data/processed/`, `data/normalized/`, `data/reports/`, and reviewed definitions in `data/custom_indices/curated/`.

## Data Flow And Provenance

1. Manual Rally research is validated into normalized asset and price-observation tables. Invalid rows are quarantined and import runs are recorded.
2. Verified normalized/manual imports provide production Rally assets and observations; legacy seed CSVs are fixture/demo bootstrap files and are excluded from production-facing dataset builds by default.
3. Cached SEC filings are parsed into offering-series and exit-event context. SEC-synthesized identifiers are research identifiers, not official Rally IDs.
4. The pipeline builds a canonical asset master and broader decision universe with provenance and quality warnings.
5. Comparable matching, experimental NAV/fair-value estimates, liquidity metrics, scoring, indices, diagnostics, and exports are derived from those normalized inputs.
6. The deployed app reads committed derived snapshots. It does not fetch SEC data or rebuild datasets during startup.

Current generated snapshot after removing legacy demo/SEC-synthesized rows from production-facing app artifacts:

| Artifact | Rows |
| --- | ---: |
| Canonical asset master | 81 |
| Rally asset decision universe | 81 |
| Normalized manual assets | 81 |
| Normalized manual price observations | 788 |
| Processed price history | 744 |
| General Rally index rows | 380 |
| Quarterly Rally index rows | 250 |
| SEC series context | 0 |
| Rally exits | 0 |
| Comparable sales universe | 6 |
| Asset-to-comp matches | 0 |
| Research coverage rows | 81 |

Counts describe the committed research snapshot and are not live market coverage.

## Implemented Capabilities

- Canonical asset and decision-universe construction with provenance and data-quality flags.
- Validated manual research imports with dry runs, archives, quarantine outputs, conflict handling, and run records.
- SEC filing cache/parser for offering-series and exit context.
- Secondary comparable normalization, similarity matching, and experimental NAV estimates.
- Equal-weighted, market-cap-weighted, quarterly descriptive price-index prototypes, exit-aware total-return portfolios, and user-defined index calculations with contribution analysis, cash/pending-settlement accounting, and risk metrics.
- Exchange Market Cap & Performance reconstruction with asset-level carry-forward audit fields, assets-added hover diagnostics for issuance-driven jumps, tradable market-cap exit removals, category decomposition, exit-aware total-return indexes, reconciliation reports, and CSV exports.
- Local and curated custom-index registries. Local JSON persistence is development-only; cloud saving is disabled through `RALLY_CUSTOM_INDEX_READ_ONLY=true`.
- Market-table filters, coverage diagnostics, category performance, liquidity metrics, deterministic AI/report context, and MME/newsletter exports.

## Important Semantics And Constraints

- A current listed asset requires Rally portfolio-capture provenance and a latest secondary quote. SEC-only rows are not presented as live listings by default.
- Offering price, distributions, and asset-sale events are not ordinary secondary-price returns.
- Missing observations are not imputed in interactive indices. Effective dates and constituent coverage therefore matter.
- Bid, ask, and spread fields remain mostly unavailable.
- Fair-value fields are experimental comparable-sales estimates and must retain that label.
- Category inference and SEC identity matching remain heuristic. Asset linkage must be reviewed before being treated as canonical.
- The deployed filesystem is not durable shared storage. Curated definitions belong in Git; user persistence requires a future database-backed adapter.

## Known Risks And Technical Debt

- Sparse and category-skewed comparable-sales coverage limits valuation confidence.
- Manual/captured trading observations can become stale and are not an official Rally market feed.
- Regex and table-based SEC parsing can over-extract or duplicate series-like rows.
- Historical exchange state is reconstructed from current committed asset, price, and exit artifacts rather than an append-only database, creating revision-history limitations; first-class exit-aware total-return artifacts now reduce survivorship bias when exit records are linked.
- Processed CSV schemas are coupled to Streamlit views and lack a versioned migration boundary.
- Pandas emits five forward-compatibility warnings in the current test suite around concatenation with empty/all-null values.
- There is no production health endpoint, telemetry, durable user storage, or automated data-refresh service.

## Near-Term Priorities

1. Validate the private GitHub and Streamlit deployment without exposing excluded research inputs.
2. Reconcile manual Rally identities and offering facts against SEC context.
3. Add an asset-detail foundation keyed by canonical `asset_id`.
4. Introduce provider boundaries and append-only quote storage before claiming live-market behavior.
5. Formalize valuation-result and factor-contribution interfaces before expanding category models.
6. Add durable custom-index persistence only when multi-user sharing becomes a product requirement.

## Books Category Expansion (2026-07-19)

The normalized Rally asset master now includes 41 user-provided Books category records for rare and signed first-edition books. These rows are committed as Rally App manual asset records with offering dates, share counts, offering prices, and offering market caps. They do not currently add secondary-market price observations, so current-tradable universe calculations continue to require valid current or recent secondary quotes before treating these assets as current tradable market capitalization.

## Production Asset Cleanup (2026-07-19)

Production-facing dataset builds now exclude the legacy raw Rally asset and price seed CSVs by default. Those seed files remain available only as explicit fixtures/legacy diagnostics because their rows were illustrative bootstrap/demo records, not verified Rally Rd listings. The investable universe builder also no longer appends SEC-synthesized series rows unless a caller explicitly opts into SEC context. As a result, committed processed app artifacts now contain the 81 verified normalized Rally App asset rows, including the 41 Books category offering records, and their corresponding Rally App price observations; SEC-derived series remain filing research context rather than app-listed assets.


## Manual Exit Coverage Update (2026-07-20)

The normalized Rally inputs now include the exited `rally-faubourg` Hermès Faubourg handbag record with a confirmed May 30, 2023 buyout at $87.50 per share / $175,000 total value. Its authored quarterly observations run from the September 2020 offering through the May 2023 terminal buyout observation so exchange-history reconstruction and exit-aware total-return simulations can account for the asset instead of treating the dataset as survivor-only for this handbag. The buyout is an exit event and terminal payout observation, not a current Rally listing or definitive appraisal.

## Manual Exit Price Coverage Update (2026-07-20)

The normalized Rally price observations now include authored quarterly chart observations and terminal buyout observations for exited handbag assets `rally-faubourg2` and `rally-birkinblu`. `rally-faubourg2` runs from its January 2021 offering context through the January 6, 2025 buyout at $16.50 per share / $181,500 total value. `rally-birkinblu` runs from its November 2019 offering context through the April 10, 2025 buyout at $68.00 per share / $68,000 total value. These terminal rows are exit payout observations for reconstruction and total-return research, not current Rally listings or definitive appraisals.

## Development And Verification

```bash
python3 scripts/build_dataset.py
python3 scripts/build_research_coverage.py
pytest -q
streamlit run app/Home.py
```

Run Streamlit from the repository root so local and Community Cloud path behavior match. Deployment uses Python 3.11, `requirements.txt`, branch `main`, and entrypoint `app/Home.py`.

## Current-Universe And Index Reconciliation Update (2026-07-18)

The current-tradable universe is now defined centrally in `alt_asset_explorer.current_universe` and is the shared source for same-name homepage and Exchange Market Cap KPI cards. A current tradable asset is a production Rally asset with canonical `active_tradable` status, positive shares, a valid current price, no offering-only valuation, and an observation age no greater than the canonical 120-day staleness threshold. Stale carried-forward observations remain in exchange-history diagnostics and represented-value analysis, but they are not labeled tradable market capitalization.

Canonical asset-state normalization maps legacy labels such as `trading`, `active`, and `accepting_orders` to `active_tradable`; terminal labels such as `sold`, `redeemed`, `liquidated`, `exited`, `delisted`, and `buyout` to `exited`; and other offering, paused, pending-settlement, cancelled, withdrawn, or unknown states to explicit canonical states. Production-facing Rally assets should use `platform = Rally` and `record_environment = production` when those fields exist. Fixture, demo, sample, mock, placeholder, synthetic, and test rows are excluded from production current-universe calculations.

Current-price methodology is intentionally conservative for tradable market cap:

1. Use the latest valid Rally/current secondary quote when available.
2. Use latest valid historical secondary-market observation on or before the as-of date when it is within the staleness threshold.
3. Carry forward a prior observation only while it remains within the staleness threshold and flag it as carried forward.
4. Treat offering price as production context, not current tradable value, unless a methodology explicitly opts in.
5. Prefer missing current valuation over silently substituting stale, future-dated, or offering-only values.

The latest reconciliation artifact explains the previous homepage-vs-exchange discrepancy row by row. The legacy homepage counted 37 imported/manual listed rows with a summed decision-universe market cap near $1.57M. The Exchange Market Cap page displayed the latest reconstructed represented exchange-history value for 43 rows, approximately $28.8M, because it included stale carried-forward values and terminal/stale large fossil and handbag records. In the committed snapshot, the canonical current-tradable universe contains 28 assets and approximately $1.571M of tradable market cap as of 2026-07-01. The largest excluded represented-value rows are `rally-steg` and `rally-baro`, whose stale carried-forward fossil values account for most of the historical represented-value gap.

Reconciliation artifacts:

- `data/processed/current_universe_reconciliation.csv` — row-level inclusion, status, price, share, and reason-code audit for each asset in either legacy current source.
- `data/processed/current_market_cap_difference_contributors.csv` — ranked market-cap gap contributors.
- `data/processed/current_universe_summary.csv` — canonical current-tradable summary consumed by Streamlit.
- `data/processed/index_engine_reconciliation.csv` — side-by-side legacy quarterly Index Explorer prototype versus monthly exit-aware total-return engine on common dates.

Index methodology remains intentionally split between descriptive quarterly observed-row price-index prototypes and the newer exit-aware total-return portfolio engine. The reconciliation artifact documents that the legacy Index Explorer prototype is based on quarterly observation rows without imputation and dynamically changing observed constituents, whereas the total-return engine uses point-in-time eligibility, offering-price entry, scheduled rebalancing, carry-forward portfolio prices, explicit cash/pending-settlement handling, and exit awareness. The canonical app build now generates quarterly, monthly, and weekly total-return variants, with quarterly presented first as the default benchmark because authored Rally observations are quarterly-oriented. Production pages should avoid presenting legacy quarterly prototypes as the same economic quantity as the exit-aware “What $100 Became” total-return indexes unless the chart is explicitly labeled as a diagnostic/prototype comparison.

Data flow:

```text
Raw Rally Sources
    +
Manual Verified Records
    +
Historical Prices
    +
Exit Events
        ↓
Canonical Asset Identity
        ↓
Production / Fixture Classification
        ↓
Canonical Status as of Date
        ↓
Canonical Current Price
        ↓
Current Tradable Universe
        ↓
Shared Summary Metrics
        ↓
Homepage + Exchange Market Cap Page
```

## Canonical Market Data Cleanup (2026-07-19)

Rally market analytics now have an explicit canonical path for the migrated Home and Exchange Market Cap surfaces: `data/normalized/assets.csv` and `data/normalized/price_observations.csv` are the two principal authored CSV inputs, loaded through `alt_asset_explorer.canonical_market`. Current tradable universe, exchange market-cap history, category decomposition, exit-aware total-return indexes, and exit analytics are calculated deterministically in memory and cached by Streamlit through semantic loaders in `app/app_data.py`.

Large redundant generated CSVs including current-universe snapshots, exchange history snapshots, total-return portfolio/constituent histories, exit analytics, and index-engine reconciliation are no longer tracked as source-of-truth artifacts. They are ignored if generated locally. Legacy processed snapshots remain for pages that have not been migrated, but they are classified as derived/report artifacts rather than authoritative Rally market inputs.

The architecture inventory and directory policy are documented in `docs/DATA_ARCHITECTURE_INVENTORY.md`.


## Methodology Transparency Update (2026-07-19)

The app now labels the survivor-biased Index Explorer universe as **Current Survivors Only** rather than **Currently Trading Only**. This label is meant to communicate that current trading status is applied retroactively and should be read as a descriptive survivor diagnostic, not a point-in-time investable benchmark.

Total-return portfolio variants are generated for quarterly, monthly, and weekly scheduled rebalancing. Quarterly is the preferred default benchmark for the current dataset because normalized Rally price observations are quarterly-oriented. Offering prices remain investable entry prices for total-return methodology; exits still convert held units into cash or pending settlement and reinvest on the next scheduled rebalance.
