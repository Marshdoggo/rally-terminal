# Manual Import Format

Templates live in `data/manual_imports/templates/`. They contain headers only; production template files intentionally contain no fictional rows.

Fictional documentation-only example asset row:

```csv
asset_id,ticker,asset_name,category,subcategory,status,shares_outstanding,offering_date,offering_price_per_share,offering_market_cap,first_trade_date,exit_date,exit_price_per_share,exit_value_total,exit_type,source_reference,verified_at,notes
example-fictional-asset,FAKE,"Fictional Example Collectible",other,example,trading,1000,2026-01-01,10.00,10000,2026-01-15,,,,,fictional documentation example,2026-07-11T12:00:00Z,Do not import this row.
```

Fictional documentation-only example price row:

```csv
asset_id,period_end,observed_at,price_per_share,market_cap,event_type,source_type,source_reference,collected_at,researcher,precision_status,notes
example-fictional-asset,2026-03-31,2026-03-28,11.00,11000,executed_trade,manual_research,fictional documentation example,2026-07-11T12:05:00Z,researcher@example.com,exact,Do not import this row.
```

## Asset Master Fields

- `asset_id`: Stable project identifier. Required and unique. Do not change it because a name changes.
- `ticker`: Rally ticker where available.
- `asset_name`: Human-readable Rally asset name. Required.
- `category`: Required category.
- `subcategory`: Optional finer category.
- `status`: One of `announced`, `offering`, `funded`, `holding_period`, `trading`, `accepting_orders`, `suspended`, `asset_sale_pending`, `liquidated`, `delisted`, `unknown`.
- `shares_outstanding`: Positive number when supplied.
- `offering_date`: ISO date for the primary offering when known.
- `offering_price_per_share`: Nonnegative number when supplied.
- `offering_market_cap`: Nonnegative number when supplied.
- `first_trade_date`: ISO date, `YYYY-MM-DD`, when known.
- `exit_date`: ISO date for verified exit/liquidation/delisting when known.
- `exit_price_per_share`: Final per-share exit/distribution amount only when verified.
- `exit_value_total`: Headline sale or exit value when supplied. This is not treated as shareholder proceeds.
- `exit_type`: One of `asset_sale`, `liquidation`, `buyout`, `distribution`, `delisting`, `unknown`.
- `source_reference`: URL, filing reference, capture name, or researcher note. Required.
- `verified_at`: ISO date or datetime for when the row was verified. Required.
- `notes`: Optional free text.

When shares, offering price, and offering market cap are all present, the importer records `implied_offering_market_cap` and warns on material differences.

## Price Observation Fields

- `asset_id`: Must exist in normalized `assets.csv`.
- `period_end`: Calendar quarter end represented by the row: March 31, June 30, September 30, or December 31.
- `observed_at`: ISO date or datetime for the actual Rally observation. Values after `period_end` are accepted with an `observed_at_after_period_end` warning so the source data remains visible and auditable.
- `price_per_share`: Positive number for price events. Leave blank for distributions if no price was observed.
- `market_cap`: Positive number when supplied.
- `volume`: Nonnegative number when supplied.
- `event_type`: One of `executed_trade`, `daily_close`, `chart_observation`, `offering_price`, `distribution`, `asset_sale`, `unknown`.
- `source_type`: One of `rally_app`, `rally_app_chart`, `rally_website`, `sec_filing`, `manual_research`, `other`.
- `source_reference`: Required source pointer.
- `collected_at`: Required ISO collection date or datetime.
- `researcher`: Optional researcher identifier.
- `precision_status`: One of `exact`, `rounded`, `chart_estimate`, `unverified`.
- `notes`: Optional free text.

## Event And Precision Notes

- Offering price: primary issuance price, not a secondary-market return observation.
- Executed trade: completed secondary-market transaction.
- Daily close: end-of-day secondary-market price.
- Chart observation: value read from a chart; usually `chart_estimate` unless a tooltip gives an exact value.
- Bid: price someone is willing to pay; not an executed trade.
- Ask: price someone is willing to sell for; not an executed trade.
- Distribution: cash or other distribution; excluded from ordinary price returns.
- Asset sale: sale/liquidation event; excluded from ordinary price returns.
- Exact value: copied from a precise field or tooltip.
- Chart estimate: visually estimated from a chart and not exact.
