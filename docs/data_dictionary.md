# Data Dictionary

## Normalized Comparable Sales

`comp_id, category, subcategory, asset_id, source, source_url, date, price_usd, currency, condition, exactness_score, source_confidence, notes`

- `exactness_score`: 0-1 estimate of match quality by model, year, condition, provenance, size, grade, rarity, and other category factors.
- `source_confidence`: 0-1 confidence in source reliability and reproducibility.
- `price_usd`: normalized USD price. Currency conversion hooks are intentionally deferred.

## MME Export

`date,ticker,name,universe,category,price,return_1d,return_7d,return_30d,volatility,sharpe,sortino,max_drawdown,source_quality`

`universe` is always `collectibles` for this standalone export boundary.

## Caveats

Scores are research features only. Rally interests are securities backed by collectible entities, not direct ownership of the physical item. Thin liquidity, stale marks, offering expenses, sourcing spreads, and imperfect comps can materially affect observed returns.
