# Index Methodology

## Interactive Index Architecture

`build_index_from_selection` is the canonical index engine. It accepts an
arbitrary set of `asset_id` values, a weighting method, and an optional date
window. Categories are metadata-driven selections made by the caller; they are
not embedded in the calculation. The precomputed market and category exports
use this same engine.

The engine returns two related tables:

- the normalized index series, including level, period return, and constituent count;
- period-level constituent attribution, including starting weight, asset return,
  contribution return, and contribution in index points.

Contribution points are calculated as the prior index level multiplied by the
constituent's weighted period return. Consequently, summed constituent
contributions reconcile to the index-level point move over the selected window.
This output can support market commentary without reverse-engineering chart data.

Observation preparation is separate from calculation. Quarterly data currently
flows through `prepare_quarterly_observations`; future daily, weekly, and OHLC
preparers can feed the same selection engine. Rolling returns, drawdowns,
correlations, factor attribution, and other analytics should consume the returned
series or attribution tables rather than add special cases to index construction.

## Quarterly Historical Indices

The quarterly historical index prototype uses manually transcribed Rally observations. It is not daily price history and should not be interpreted as representing daily price action.

For each asset and calendar quarter, researchers record the last visible valid Rally trading value on or before the quarter-end date. The index period is `period_end`, while the actual Rally observation date remains `observed_at`.

If a manually supplied row uses an `observed_at` after `period_end`, the importer preserves the row but emits an `observed_at_after_period_end` warning. These rows are accepted for research visibility, remain auditable in the normalized observation table, and should be corrected when a valid on-or-before-quarter-end observation is later found.

Valid quarter ends are March 31, June 30, September 30, and December 31.

The persisted dataset produces:

- Equal-weighted Rally market index
- Market-cap-weighted Rally market index
- Equal-weighted category indices
- Market-cap-weighted category indices

All valid index series normalize inception to 100. Market-cap-weighted series use prior-quarter market-cap weights when available. Assets without verified shares or market cap can remain eligible for equal-weighted series but are excluded from market-cap-weighted series.

No interpolation is performed between quarterly observations.

## Custom Index Workshop

Saved custom indexes use the same prepared quarterly observations but a stricter
constant-weight normalized-composite method. They begin at the latest common
valid constituent date, keep only dates observed for every constituent, and do
not fill missing prices. Manual weights are positive, long-only, unlevered, and
sum to 100%. See [CUSTOM_INDEX_WORKSHOP.md](CUSTOM_INDEX_WORKSHOP.md) for schema,
metrics, contribution, persistence, and production deployment details.

## Exited Assets

Exited assets remain part of historical constituent membership for periods in which they were eligible for Rally secondary trading. Ordinary secondary-price observations stop after a verified exit date.

For the current price-return index:

- Preserve the last secondary-market observation.
- Preserve exit announcement and exit provenance when supplied.
- Preserve exit date, final sale value, and later shareholder distribution fields separately.
- Do not calculate an exit return from unverified proceeds.
- Do not treat headline asset sale value as shareholder proceeds.
- Emit a warning when an exit is known but final shareholder proceeds are unavailable.

## Future Total-Return Index Placeholder

A future total-return index may incorporate verified cash distributions and final shareholder proceeds. That work requires separate provenance for distribution per share and should not reuse headline asset sale value as if it were investor proceeds.
