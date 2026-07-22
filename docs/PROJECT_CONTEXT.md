# Rally Terminal Project Context

Last audited: 2026-07-22
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
| Canonical asset master | 84 |
| Rally asset decision universe | 84 |
| Normalized manual assets | 84 |
| Normalized manual price observations | 960 |
| Processed price history | 904 |
| General Rally index rows | 428 |
| Quarterly Rally index rows | 304 |
| SEC series context | 0 |
| Rally exits | 0 |
| Comparable sales universe | 6 |
| Asset-to-comp matches | 0 |
| Research coverage rows | 84 |
| Asset universe diagnostics rows | 84 |

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

Production-facing dataset builds now exclude the legacy raw Rally asset and price seed CSVs by default. Those seed files remain available only as explicit fixtures/legacy diagnostics because their rows were illustrative bootstrap/demo records, not verified Rally Rd listings. The investable universe builder also no longer appends SEC-synthesized series rows unless a caller explicitly opts into SEC context. As a result, committed processed app artifacts now contain 84 verified normalized production asset rows, including the 41 Books category offering records and authored exit coverage rows, with corresponding Rally App/manual price observations; SEC-derived series remain filing research context rather than app-listed assets.


## Manual Exit Coverage Update (2026-07-20)

The normalized Rally inputs now include the exited `rally-faubourg` Hermès Faubourg handbag record with a confirmed May 30, 2023 buyout at $87.50 per share / $175,000 total value. Its authored quarterly observations run from the September 2020 offering through the May 2023 terminal buyout observation so exchange-history reconstruction and exit-aware total-return simulations can account for the asset instead of treating the dataset as survivor-only for this handbag. The buyout is an exit event and terminal payout observation, not a current Rally listing or definitive appraisal.

## Manual Exit Price Coverage Update (2026-07-20)

The normalized Rally price observations now include authored quarterly chart observations and terminal buyout observations for exited handbag assets `rally-faubourg2` and `rally-birkinblu`. `rally-faubourg2` runs from its January 2021 offering context through the January 6, 2025 buyout at $16.50 per share / $181,500 total value. `rally-birkinblu` runs from its November 2019 offering context through the April 10, 2025 buyout at $68.00 per share / $68,000 total value. These terminal rows are exit payout observations for reconstruction and total-return research, not current Rally listings or definitive appraisals.

## Manual Watch Exit Coverage Update (2026-07-20)

The normalized Rally inputs now include authored watch exit coverage for `rally-7orlex` (`#70RLEX`) and `rally-aproak` (`#APROAK`). `rally-7orlex` runs from its November 2019 offering context through the December 12, 2023 buyout at $30.00 per share / $30,000 total value. `rally-aproak` runs from its December 2019 offering context through the June 30, 2021 buyout at $110.00 per share / $110,000 total value. APROAK intentionally retains both the May 10, 2021 intra-quarter secondary chart observation and the June 30, 2021 terminal buyout in Q2 2021; canonical quarter-end research should use the realized buyout while preserving the May observation as historical evidence. These terminal rows are exit payout observations for reconstruction and total-return research, not current Rally listings or definitive appraisals.


## Manual Wine Exit Coverage Update (2026-07-20)

The normalized Rally inputs now include authored wine-and-whiskey exit coverage for `rally-17dujac` (`#17DUJAC`), modeled as the 2017 Domaine Dujac Wine Collection. The observation history runs from the March 2021 offering context through the May 13, 2025 realized buyout at approximately $10.923077 per share / $35,500 total value. This terminal row is an exit payout observation for reconstruction and total-return research, not a current Rally listing or definitive appraisal.

## Pending Buyout Offer Coverage Update (2026-07-20)

The normalized Rally inputs now include authored quarterly price observations for `rally-deaton`, the Deaton Triceratops Skull fossil asset, from its January 2021 offering context through the June 22, 2026 last close before a pending buyout vote. The asset is marked `exit_announced`, with pending offer metadata for a proposed $600,000 / $52.631579 per-share buyout and 54% yes vote snapshot. Because the offer has not been approved and completed, Deaton is not modeled as a realized exit, settled buyout, or terminal payout observation.

## Manual Books Price Coverage Update (2026-07-22)

The normalized Rally price observations now include manually transcribed quarterly chart coverage for existing Books asset `rally-alice` (`#ALICE`), Lewis Carroll — Alice's Adventures in Wonderland, First Edition. The history preserves the actual observed Rally dates from the September 2020 offering context through the June 25, 2026 Q2 observation at $2.00 per share; a later conversational approximately $1.50 note is intentionally excluded from the current historical build. The verbally supplied first 2021 observation (`2-02-21`) is stored in ISO form as February 2, 2021 and marked unverified/ambiguous in the row notes rather than silently treated as a higher-precision source. ALICE now has sufficient quarterly price history to participate in the Books quarterly index where the prototype methodology permits.


## Manual Books Price Coverage Update (SHKSPR4, 2026-07-22)

The normalized Rally price observations now include manually transcribed quarterly chart coverage for existing Books asset `rally-shkspr4` (`#SHKSPR4`), Shakespeare's Comedies, Histories, and Tragedies. The history preserves the actual observed Rally dates from the July 2020 offering context through the June 24, 2026 Q2 observation at $75.00 per share / $75,000 total value. Market caps are validated against the existing 1,000-share master record. The February 7, 2022 observation is normalized to the December 31, 2021 period as the nearest available after-quarter observation so the March 28, 2022 quote remains the Q1 2022 observation. SHKSPR4 now has sufficient quarterly price and market-cap history to participate in the Books equal-weight and market-cap-weighted historical index prototypes where the methodology permits.


## Manual Books Price Coverage Update (CHURCHILL, 2026-07-22)

The normalized Rally price observations now include manually transcribed quarterly chart coverage for existing Books asset `rally-churchill` (`#CHURCHILL`), Winston Churchill - The Second World War (Signed First Edition). The history preserves the actual observed Rally dates from the July 2020 offering context through the June 24, 2026 Q2 observation at $3.15 per share / $23,625 total value. Market caps are validated against the existing 7,500-share master record. A more recent conversational $3.90 trade note after the Q2 2026 cutoff is intentionally excluded from this quarterly historical build and reserved for future weekly-history coverage. CHURCHILL now has sufficient quarterly price and market-cap history to participate in the Books equal-weight and market-cap-weighted historical index prototypes where the methodology permits.


## Manual Books Price Coverage Update (HGWELLS, 2026-07-22)

The normalized Rally price observations now include manually transcribed quarterly chart coverage for existing Books asset `rally-hgwells` (`#HGWELLS`), H.G. Wells's The Time Machine, Inscribed First Edition. The history preserves the actual observed Rally dates from the June 2021 offering reference value through the June 29, 2026 Q2 observation at $2.30 per share / $17,250 total value. Market caps are validated against the existing 7,500-share master record. The November 1, 2021 observation is normalized to the September 30, 2021 period as the nearest available after-quarter observation. HGWELLS now has sufficient quarterly price and market-cap history to participate in the Books equal-weight and market-cap-weighted historical index prototypes where the methodology permits.



## Manual Books Price Coverage Update (LOTR, 2026-07-22)

The normalized Rally price observations now include manually transcribed quarterly chart coverage for existing Books asset `rally-lotr` (`#LOTR`), J.R.R. Tolkien's The Lord of the Rings Trilogy, First Edition. The history preserves actual observed Rally dates from the June 5, 2020 offering observation through the July 1, 2026 observation at $75.00 per share / $75,000 total value. Market caps are validated against the existing 1,000-share master record. The July 1, 2026 observation preserves its actual date while being assigned to the June 30, 2026 period by the current nearest-quarter research convention, producing an explicit after-period warning rather than rewriting the source date. LOTR now has sufficient quarterly price and market-cap history to participate in the Books equal-weight and market-cap-weighted historical index prototypes where the methodology permits.

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

## Universe Eligibility Architecture Update (2026-07-20)

Rally analytics now share `alt_asset_explorer.universe` for reusable source-data-driven eligibility and propagation diagnostics. The builder distinguishes canonical source presence, production eligibility, normalized status, active-tradable versus exit-aware scopes, price-history availability, market-cap-history availability, and dated entry eligibility. Index Explorer uses this layer for its Current Survivors Only and Include Exited Assets scopes, while its plotted `constituent_count` remains the actual number of assets with usable observations at each point in the calculation; the UI also surfaces the selected historical universe size so exited assets are visible without creating look-ahead-biased date counts.

Exit-aware total-return portfolios are now generated for both `include_exited` and `active_only` universe scopes, allowing the Home and Exchange Market Cap pages to compare survivor-only portfolios against lifecycle-aware simulations where exits realize proceeds and reinvest according to the selected rebalance methodology. The dataset build also emits `data/processed/asset_universe_diagnostics.csv` as a lightweight developer audit table showing each asset's category, normalized status, history rows, equal-weight eligibility, market-cap-weight eligibility, exit recognition, and named exclusion reason. This diagnostic is derived from canonical normalized assets and observations and is intended to prevent silent orphaning when new Rally assets or exited assets are entered.
