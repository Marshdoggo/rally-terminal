from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from alt_asset_explorer.custom_indices import calculate_index_metrics, normalize_weights
from alt_asset_explorer.total_return import TotalReturnConfig, _price_date_frame, normalize_exit_events, scheduled_rebalance_dates
from alt_asset_explorer.universe import build_asset_universe, eligible_asset_ids

WeightingMethod = Literal["equal_weight", "custom_weight"]
RebalanceFrequency = Literal["none", "monthly", "quarterly", "annual"]
UniversePolicy = Literal["current_survivors_only", "include_exited"]
EntryPolicy = Literal["enter_when_available"]
MissingPricePolicy = Literal["carry_forward"]
ExitPolicy = Literal["remove_at_exit"]
CashPolicy = Literal["scheduled_rebalance"]


@dataclass(frozen=True)
class PortfolioMethodology:
    weighting_method: WeightingMethod = "equal_weight"
    rebalance_frequency: RebalanceFrequency = "quarterly"
    universe_policy: UniversePolicy = "include_exited"
    entry_policy: EntryPolicy = "enter_when_available"
    missing_price_policy: MissingPricePolicy = "carry_forward"
    exit_policy: ExitPolicy = "remove_at_exit"
    cash_policy: CashPolicy = "scheduled_rebalance"
    reinvestment_policy: CashPolicy = "scheduled_rebalance"


@dataclass(frozen=True)
class PortfolioDefinition:
    name: str
    asset_ids: tuple[str, ...]
    methodology: PortfolioMethodology = field(default_factory=PortfolioMethodology)
    custom_weights: dict[str, float] | None = None
    base_value: float = 100.0
    start_date: object | None = None
    end_date: object | None = None
    benchmark_category: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("portfolio name cannot be blank")
        if not self.asset_ids or len(self.asset_ids) != len(set(self.asset_ids)):
            raise ValueError("asset_ids must be a non-empty unique tuple")
        if self.methodology.weighting_method == "custom_weight":
            normalize_weights(list(self.asset_ids), self.custom_weights)


@dataclass(frozen=True)
class PortfolioSimulationResult:
    definition: PortfolioDefinition
    series: pd.DataFrame
    constituents: pd.DataFrame
    metrics: dict[str, float | int | str | None]
    methodology: PortfolioMethodology
    warnings: tuple[str, ...] = ()


def _annual_rebalance_dates(dates: pd.DatetimeIndex) -> set[pd.Timestamp]:
    if len(dates) == 0:
        return set()
    scheduled = pd.date_range(dates.min(), dates.max(), freq="YE")
    out = {dates[dates >= d].min() for d in scheduled if (dates >= d).any()}
    out.add(dates.min())
    return {pd.Timestamp(d).normalize() for d in out}


def _rebalance_dates(dates: pd.DatetimeIndex, frequency: RebalanceFrequency) -> set[pd.Timestamp]:
    if len(dates) == 0:
        return set()
    if frequency == "none":
        return {pd.Timestamp(dates.min()).normalize()}
    if frequency == "annual":
        return _annual_rebalance_dates(dates)
    return scheduled_rebalance_dates(dates, "monthly" if frequency == "monthly" else "quarterly")


def _date_grid(assets: pd.DataFrame, prices: pd.DataFrame, exits: pd.DataFrame, start_date: object | None, end_date: object | None) -> pd.DatetimeIndex:
    dates = []
    for frame, cols in [(assets, ["offering_date"]), (prices, ["date"]), (exits, ["exit_effective_date", "settlement_date"] )]:
        for col in cols:
            if col in frame:
                dates.extend(pd.to_datetime(frame[col], errors="coerce").dropna().tolist())
    if not dates:
        return pd.DatetimeIndex([])
    idx = pd.DatetimeIndex(sorted({pd.Timestamp(d).normalize() for d in dates}))
    if start_date is not None:
        idx = idx[idx >= pd.Timestamp(start_date).normalize()]
    if end_date is not None:
        idx = idx[idx <= pd.Timestamp(end_date).normalize()]
    return idx


def simulate_portfolio(definition: PortfolioDefinition, assets: pd.DataFrame, prices: pd.DataFrame, exits: pd.DataFrame | None = None) -> PortfolioSimulationResult:
    methodology = definition.methodology
    cols = ["date", "index_level", "period_return", "cumulative_return", "portfolio_value", "cash_value", "active_constituent_count", "rebalance_flag"]
    empty = pd.DataFrame(columns=cols)
    required = {"asset_id", "offering_date", "share_count", "offering_price_usd"}
    if assets.empty or not required.issubset(assets.columns):
        return PortfolioSimulationResult(definition, empty, pd.DataFrame(), calculate_index_metrics(empty), methodology, ("Missing asset master fields.",))
    a = assets.copy()
    a["asset_id"] = a["asset_id"].astype(str)
    a = a[a["asset_id"].isin(definition.asset_ids)].copy()
    a["offering_date"] = pd.to_datetime(a["offering_date"], errors="coerce").dt.normalize()
    a["share_count"] = pd.to_numeric(a["share_count"], errors="coerce")
    a["offering_price_usd"] = pd.to_numeric(a["offering_price_usd"], errors="coerce")
    a = a.dropna(subset=["asset_id", "offering_date", "share_count", "offering_price_usd"])
    a = a[(a["share_count"] > 0) & (a["offering_price_usd"] > 0)]
    include_exited = methodology.universe_policy == "include_exited"
    p0 = _price_date_frame(prices)
    universe = build_asset_universe(a, p0, include_exited=include_exited, require_price_history=False)
    allowed = set(eligible_asset_ids(universe)) if not universe.empty else set()
    a = a[a["asset_id"].isin(allowed)].copy()
    warnings = []
    missing = sorted(set(definition.asset_ids) - set(a["asset_id"]))
    if missing:
        warnings.append("Excluded unavailable or ineligible assets: " + ", ".join(missing))
    if a.empty:
        return PortfolioSimulationResult(definition, empty, pd.DataFrame(), calculate_index_metrics(empty), methodology, tuple(warnings or ["No eligible portfolio assets."]))
    p = p0[p0["asset_id"].astype(str).isin(set(a["asset_id"]))].copy()
    offer = a[["asset_id", "offering_date", "offering_price_usd"]].rename(columns={"offering_date": "date", "offering_price_usd": "last"})
    offer["event_type"] = "offering_price"; offer["_priority"] = 0
    p = pd.concat([p, offer], ignore_index=True, sort=False).sort_values(["date", "asset_id", "_priority"]).drop_duplicates(["date", "asset_id"], keep="last")
    e = normalize_exit_events(a, exits if exits is not None else pd.DataFrame(), prices)
    dates = _date_grid(a, p, e, definition.start_date, definition.end_date)
    if len(dates) == 0:
        return PortfolioSimulationResult(definition, empty, pd.DataFrame(), calculate_index_metrics(empty), methodology, tuple(warnings or ["No dates in selected window."]))
    price_wide = p.pivot_table(index="date", columns="asset_id", values="last", aggfunc="last").sort_index().reindex(dates).ffill()
    rebalances = _rebalance_dates(dates, methodology.rebalance_frequency)
    asset_ids = tuple(a["asset_id"].astype(str))
    custom_weights = normalize_weights(list(definition.asset_ids), definition.custom_weights) if methodology.weighting_method == "custom_weight" else None
    share_map = a.set_index("asset_id")["share_count"].astype(float).to_dict()
    offer_map = a.set_index("asset_id")["offering_date"].to_dict()
    exit_by_asset = {str(r["asset_id"]): r for _, r in e.iterrows()} if not e.empty else {}
    units: dict[str, float] = {}; cash = float(definition.base_value); prev_value = None; level = float(definition.base_value)
    rows = []; const_rows = []
    for d in dates:
        d = pd.Timestamp(d).normalize()
        for aid, ex in list(exit_by_asset.items()):
            if aid in units and pd.notna(ex["exit_effective_date"]) and d >= ex["exit_effective_date"] and ex["exit_status"] != "cancelled_exit":
                cash += units.pop(aid) * float(ex["terminal_price"] if pd.notna(ex["terminal_price"]) else 0.0)
        prices_on_date = price_wide.loc[d]
        price_map = {aid: float(prices_on_date.get(aid)) for aid in asset_ids if pd.notna(prices_on_date.get(aid))}
        total_value = cash + sum(units.get(aid, 0) * price_map.get(aid, 0) for aid in units)
        is_rebal = d in rebalances
        if is_rebal:
            eligible = []
            for aid in asset_ids:
                removed = aid in exit_by_asset and pd.notna(exit_by_asset[aid]["exit_effective_date"]) and d >= exit_by_asset[aid]["exit_effective_date"] and exit_by_asset[aid]["exit_status"] != "cancelled_exit"
                if offer_map[aid] <= d and aid in price_map and not removed:
                    eligible.append(aid)
            if eligible:
                if custom_weights:
                    raw = {aid: custom_weights.get(aid, 0.0) for aid in eligible}
                    weights = normalize_weights(eligible, raw)
                else:
                    weights = {aid: 1 / len(eligible) for aid in eligible}
                units = {aid: total_value * weights[aid] / price_map[aid] for aid in eligible}
                cash = 0.0
                total_value = sum(units[aid] * price_map[aid] for aid in units)
        period_return = 0.0 if prev_value is None else (total_value / prev_value - 1 if prev_value else 0.0)
        if prev_value is None:
            level = float(definition.base_value)
        else:
            level *= 1 + period_return
        prev_value = total_value
        rows.append({"date": d, "index_level": level, "period_return": period_return, "cumulative_return": level / definition.base_value - 1, "portfolio_value": total_value, "cash_value": cash, "active_constituent_count": len(units), "rebalance_flag": is_rebal, "weighting_method": methodology.weighting_method, "rebalance_frequency": methodology.rebalance_frequency, "universe_scope": methodology.universe_policy})
        for aid, u in units.items():
            value = u * price_map.get(aid, 0)
            const_rows.append({"date": d, "asset_id": aid, "units_held": u, "price": price_map.get(aid), "position_value": value, "portfolio_weight": value / total_value if total_value else 0})
    series = pd.DataFrame(rows)
    if not series.empty:
        series["drawdown"] = series["index_level"] / series["index_level"].cummax() - 1
    metrics = calculate_index_metrics(series.rename(columns={}), periods_per_year=4)
    return PortfolioSimulationResult(definition, series, pd.DataFrame(const_rows), metrics, methodology, tuple(warnings))


def simulate_index_investment(index_series: pd.DataFrame, *, starting_value: float = 100.0) -> pd.DataFrame:
    if index_series.empty or not {"date", "index_level"}.issubset(index_series.columns):
        return pd.DataFrame(columns=["date", "growth_value", "period_return"])
    out = index_series[["date", "index_level"]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["index_level"] = pd.to_numeric(out["index_level"], errors="coerce")
    out = out.dropna().sort_values("date")
    if out.empty or not math.isfinite(float(out.iloc[0]["index_level"])) or float(out.iloc[0]["index_level"]) <= 0:
        return pd.DataFrame(columns=["date", "growth_value", "period_return"])
    out["growth_value"] = out["index_level"] / float(out.iloc[0]["index_level"]) * starting_value
    out["period_return"] = out["growth_value"].pct_change().fillna(0.0)
    return out[["date", "growth_value", "period_return"]]
