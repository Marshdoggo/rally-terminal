# Rally Terminal Project Context

Last audited: 2026-07-14  
Verification baseline: Python 3.11, Streamlit 1.51.0, pandas 2.3.3, lxml 6.1.1, 91 tests passing

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
2. Manual seeds and permitted source imports provide Rally assets, observations, and comparable sales.
3. Cached SEC filings are parsed into offering-series and exit-event context. SEC-synthesized identifiers are research identifiers, not official Rally IDs.
4. The pipeline builds a canonical asset master and broader decision universe with provenance and quality warnings.
5. Comparable matching, experimental NAV/fair-value estimates, liquidity metrics, scoring, indices, diagnostics, and exports are derived from those normalized inputs.
6. The deployed app reads committed derived snapshots. It does not fetch SEC data or rebuild datasets during startup.

Current generated snapshot:

| Artifact | Rows |
| --- | ---: |
| Canonical asset master | 550 |
| Rally asset decision universe | 550 |
| Normalized manual assets | 40 |
| Normalized manual price observations | 536 |
| Processed price history | 527 |
| General Rally index rows | 322 |
| Quarterly Rally index rows | 248 |
| SEC series context | 1,565 |
| Rally exits | 190 |
| Comparable sales universe | 67 |
| Asset-to-comp matches | 194 |
| Research coverage rows | 40 |

Counts describe the committed research snapshot and are not live market coverage.

## Implemented Capabilities

- Canonical asset and decision-universe construction with provenance and data-quality flags.
- Validated manual research imports with dry runs, archives, quarantine outputs, conflict handling, and run records.
- SEC filing cache/parser for offering-series and exit context.
- Secondary comparable normalization, similarity matching, and experimental NAV estimates.
- Equal-weighted, market-cap-weighted, quarterly, and user-defined index calculations with contribution analysis and risk metrics.
- Exchange Market Cap & Performance reconstruction with asset-level carry-forward audit fields, category decomposition, flow-adjusted return indexes, reconciliation reports, and CSV exports.
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
- Historical exchange state is reconstructed from current committed asset, price, and exit artifacts rather than an append-only database, creating potential survivorship-bias and revision-history limitations.
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

## Development And Verification

```bash
python3 scripts/build_dataset.py
python3 scripts/build_research_coverage.py
pytest -q
streamlit run app/Home.py
```

Run Streamlit from the repository root so local and Community Cloud path behavior match. Deployment uses Python 3.11, `requirements.txt`, branch `main`, and entrypoint `app/Home.py`.
