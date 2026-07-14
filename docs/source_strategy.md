# Source Strategy

This project should make the Rally-versus-secondary-market comparison explicit and auditable. The goal is not to scrape every marketplace indiscriminately; it is to build reliable, source-aware observations that can survive research review.

## Rally Data

Preferred sources:

- SEC EDGAR filings for issuer, series, offering price, share count, acquisition costs, expenses, exits, and corporate actions.
- Rally or RSE account exports, downloaded reports, or manually provided snapshots for current bid, ask, last trade, volume, and trading-window information.
- Manual seed CSVs only as a fallback or fixture source.

Needed fields:

- `asset_id`, `ticker`, `series_name`, `category`, `subcategory`
- `offering_date`, `offering_price`, `shares`, `market_cap_usd`, `last_price_usd`
- bid, ask, volume, observation date, source URL, source confidence
- status flags for active, halted, exited, or stale assets

## Secondary Market Data

Connector candidates by category:

- Handbags: auction results and resale-market exports from Sotheby's, Christie's, Fashionphile, Rebag, The RealReal, and manually reviewed dealer comps.
- Watches: auction results and dealer/marketplace exports from Phillips, Sotheby's, Christie's, Chrono24-style exports where permitted, and brand/reference-specific market reports.
- Cars: auction results from Bring a Trailer-style exports where permitted, RM Sotheby's, Gooding, Bonhams, and marque-specific public sale records.
- Cards and memorabilia: graded auction sales from Goldin, Heritage, PWCC/Fanatics-style exports where permitted, eBay Terapeak/user exports, and PSA/SGC grade metadata.
- Art, wine, fossils, natural history, and other categories: start with manual templates plus auction-house result exports until a permitted API or bulk data source is available.

Each connector should output normalized `ComparableSale` records and keep raw cached files separately. Data that cannot be reproduced or linked should receive lower `source_confidence`.

## Build Order

1. Add a connector contract: `fetch_raw`, `load_cached`, `normalize`, and `validate` for sources that allow automated or user-provided downloads.
2. Expand Rally SEC ingestion with cached real filings and tests for offerings, expenses, exits, and series matching.
3. Add category-specific exactness rules: model/reference/year, grade, size, material, provenance, condition, and sale venue quality.
4. Add currency conversion and sale-fee normalization before non-USD or hammer-price data affects NAV.
5. Add dashboard source coverage and stale-data warnings for both Rally snapshots and secondary comps.
6. Only then enable scheduled refreshes or one-click imports.

## Valuation Signal

The core comparison is:

`discount_to_secondary_nav = (secondary_nav_usd - rally_market_cap_usd) / secondary_nav_usd`

Positive values imply Rally is marked below the current weighted secondary-market estimate. That is a research signal, not a recommendation, and it should always be read with liquidity, confidence, and stale-data flags.
