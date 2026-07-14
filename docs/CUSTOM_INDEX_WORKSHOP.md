# Custom Index Workshop

## User workflow

Open **Asset Price History**, switch the mode to **Custom Index Workshop**, and
search for one or more assets. The basket recalculates immediately when an asset
is added or removed. New baskets start equal-weighted. **Custom Weight** exposes
percentage inputs plus explicit **Normalize to 100%** and **Reset to Equal
Weight** actions. A custom calculation is shown only when allocations resolve to
100% within 0.01 percentage point.

Name the basket, optionally describe it, and choose **Save Custom Index**. The
saved definition becomes available from **Explore index** in Index Explorer,
where it is identified as custom and displayed with its composition, chart,
analytics, contribution table, methodology, creator, and benchmark overlays.
Both the workshop and explorer can export the saved definition as JSON.

## Calculation methodology

Custom indexes are constant-weight normalized composites with a starting value
of 100. This is explicit in `rebalance_policy` and is not a buy-and-hold share
portfolio whose weights drift.

For constituent `i` on common start date `s`:

```text
normalized_i(t) = price_i(t) / price_i(s) * 100
custom_index(t) = sum(weight_i * normalized_i(t))
```

Weights are positive, unlevered, long-only, and sum to one. Equal-weight baskets
assign `1 / n` to each constituent. Custom allocations are normalized only when
the user requests it; invalid totals remain visible and block calculation/save.

### Price alignment

The workshop uses the same audited quarterly observation source as the existing
Index Explorer. The effective start is the latest inception among selected
constituents. The calculation then retains only quarter-ends on which every
constituent has a positive, valid observation. Missing observations are not
forward-filled or interpolated. The UI discloses the effective start/end dates
and warns when incomplete common dates are excluded. A basket with no common
valid date cannot be calculated or saved.

This stricter common-calendar policy is appropriate for a user-specified fixed
basket. Existing broad category indexes retain their established period-return
method, which can use the eligible overlapping assets in each period.

## Metrics

Quarterly returns are derived from index levels. The scorecard reports total
return, CAGR (only for histories of at least one year), annualized volatility,
zero-risk-free-rate Sharpe ratio, maximum drawdown, and risk band. The engine
also returns Sortino ratio, current drawdown, best/worst quarter, and observation
count for future views. Volatility is annualized by `sqrt(4)`. Sharpe and Sortino
are `N/A` when their denominator or sample is insufficient. Risk bands reuse the
existing sector thresholds: Low below 15%, Medium below 30%, otherwise High.

## Contribution analysis

Full-window contribution is:

```text
asset return = ending price / starting price - 1
weighted contribution = starting weight * asset return
contribution points = 100 * weighted contribution
```

Constituent contribution points must reconcile to the custom index point move
within `1e-6`; the engine raises an error if they do not. Positive and negative
values are naturally ranked by contribution points. Share of total move is
omitted when the total move is effectively zero.

## Schema and architecture

`CustomIndexDefinition` is a strict Pydantic schema containing a stable UUID-
suffixed ID, display name, optional description, timestamps, schema version,
index type, weighting method, base value, date settings, creator, rebalance
policy, constituents with stable asset IDs/display metadata/weights, and an
optional analytics snapshot.

Definitions are persisted instead of rendered chart output. Source observations
remain authoritative, so an index can be reproduced, audited, compared on a new
window, or recalculated when corrected observations arrive. The calculation and
storage layers have no Streamlit dependency and can later serve an API, report
job, leaderboard, or database-backed community product.

## Persistence

The `CustomIndexStorage` interface separates persistence from UI code.
`JsonDirectoryCustomIndexStorage` is the working local adapter and
`CombinedCustomIndexRegistry` merges:

- `data/custom_indices/curated/`: reviewed, version-controlled seed definitions;
- `data/custom_indices/local/`: local user saves, ignored by version control.

Writes validate the schema, unique ID, unique case-insensitive name, constituent
uniqueness, and weight total. A temporary file is atomically renamed into place.
Corrupt or stale-schema JSON records are skipped rather than crashing the app.

To add a curated index, create it in the workshop, download or copy its JSON
definition, validate it with the tests, move it to `data/custom_indices/curated/`,
and commit it.

### Streamlit Cloud limitation

The local adapter is not durable shared storage on Streamlit Community Cloud.
Files may disappear on restart/redeploy and are not a multi-user database. A
production deployment should implement the same storage interface over
PostgreSQL, Supabase, or another durable service, with authenticated creators,
transactions, moderation state, and server-side authorization. No credentials
or privileged GitHub token are used by this MVP.

## Running and testing

```bash
pytest -q
streamlit run app/Home.py
```

Calculation and persistence tests use deterministic in-memory fixtures and
temporary directories; they do not call external APIs.
