# Roadmap

## Current Milestone

- Manual Rally seed ingestion.
- Manual comparable-sale normalization.
- Weighted NAV estimates with confidence intervals and stale-data warnings.
- Liquidity, performance, scoring, AI context, and MME-compatible CSV export.
- Streamlit dashboard pages for the first research workflows.

## Next Milestones

- Add permitted downloadable or API-backed category connectors.
- Expand SEC parser fixtures with real cached Rally/RSE filings.
- Add currency normalization and category-specific condition adjustment tables.
- Add authenticated or user-provided exports for secondary-market sources where terms permit.
- Keep integration with Market Metric Explorer at the CSV/JSON boundary until the data contract is stable.

## Data Acquisition Plan

1. Rally primary data should come from reproducible sources first: SEC EDGAR filings for offering economics, Rally/RSE issuer pages or user-provided exports for current market snapshots, and manually reviewed CSV fallbacks when automated access is unavailable or not permitted.
2. Secondary-market comps should be connector-backed by category, with every observation carrying source, URL, sale date, price, condition, exactness score, and source confidence.
3. The valuation layer should continue to compare Rally market cap against a weighted secondary-market NAV, but each connector needs category-specific normalization before its data affects scores.
4. The dashboard should treat live or scraped data as provisional until it is cached, validated against the schema, and visible in the source coverage views.
