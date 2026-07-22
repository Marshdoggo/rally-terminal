from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import numpy as np
import pandas as pd

from alt_asset_explorer.custom_indices import calculate_index_metrics, normalize_weights
from alt_asset_explorer.total_return import _price_date_frame, normalize_exit_events

PortfolioWeightingMethod = Literal["equal_weight", "custom_weight"]
PortfolioRebalanceFrequency = Literal["none", "monthly", "quarterly", "annual"]
PortfolioUniversePolicy = Literal["include_exited", "current_survivors_only"]
PortfolioExitTreatment = Literal["hold_cash_until_rebalance"]
PortfolioMissingPricePolicy = Literal["carry_forward_observed_prices"]
PortfolioAssetEntryPolicy = Literal["enter_on_rebalance_when_eligible"]

PORTFOLIO_SERIES_COLUMNS = [
    "date",
    "portfolio_id",
    "portfolio_name",
    "index_level",
    "portfolio_value",
    "invested_asset_value",
    "cash_value",
    "period_return",
    "cumulative_return",
    "active_constituent_count",
    "eligible_constituent_count",
    "rebalance_flag",
    "weighting_method",
    "rebalance_frequency",
    "universe_policy",
    "exit_treatment",
    "missing_price_policy",
    "asset_entry_policy",
    "calculation_version",
]

PORTFOLIO_CONSTITUENT_COLUMNS = [
    "date",
    "portfolio_id",
    "asset_id",
    "ticker",
    "price",
    "units_held",
    "position_value",
    "portfolio_weight",
    "target_weight",
    "constituent_status",
]

CALCULATION_VERSION = "custom_portfolio_engine_v1"


@dataclass(frozen=True)
class PortfolioDefinition:
    """Reusable first-class Rally portfolio strategy definition."""

    name: str
    asset_ids: tuple[str, ...]
    weighting_method: PortfolioWeightingMethod = "equal_weight"
    custom_weights: dict[str, float] | None = None
    rebalance_frequency: PortfolioRebalanceFrequency = "quarterly"
    universe_policy: PortfolioUniversePolicy = "include_exited"
    exit_treatment: PortfolioExitTreatment = "hold_cash_until_rebalance"
    missing_price_policy: PortfolioMissingPricePolicy = "carry_forward_observed_prices"
    asset_entry_policy: PortfolioAssetEntryPolicy = "enter_on_rebalance_when_eligible"
    start_date: str | None = None
    end_date: str | None = None
    benchmark_id: str = "full_market_equal_weight"
    base_value: float = 100.0
    portfolio_id: str = "custom_portfolio"
    metadata: dict[str, str] = field(default_factory=dict)

    def target_weights(self) -> dict[str, float]:
        asset_ids = [str(asset_id) for asset_id in self.asset_ids]
        if self.weighting_method == "equal_weight":
            return normalize_weights(asset_ids)
        return normalize_weights(asset_ids, self.custom_weights)

    def methodology_metadata(self) -> dict[str, object]:
        return {
            "weighting_method": self.weighting_method,
            "rebalance_frequency": self.rebalance_frequency,
            "universe_policy": self.universe_policy,
            "exit_treatment": self.exit_treatment,
            "missing_price_policy": self.missing_price_policy,
            "asset_entry_policy": self.asset_entry_policy,
            "calculation_version": CALCULATION_VERSION,
        }


@dataclass(frozen=True)
class PortfolioSimulationResult:
    definition: PortfolioDefinition
    series: pd.DataFrame
    constituents: pd.DataFrame
    metrics: dict[str, float | int | str | None]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkComparisonResult:
    chart: pd.DataFrame
    metrics: pd.DataFrame


def _rebalance_dates(dates: pd.DatetimeIndex, frequency: PortfolioRebalanceFrequency) -> set[pd.Timestamp]:
    if len(dates) == 0:
        return set()
    normalized = pd.DatetimeIndex(pd.to_datetime(dates).normalize()).sort_values()
    if frequency == "none":
        return {normalized[0]}
    rule = {"monthly": "ME", "quarterly": "QE", "annual": "YE"}[frequency]
    scheduled = pd.date_range(normalized.min(), normalized.max(), freq=rule)
    out = {normalized[normalized >= target].min() for target in scheduled if (normalized >= target).any()}
    out.add(normalized[0])
    return {pd.Timestamp(item).normalize() for item in out}


def _selected_assets(assets: pd.DataFrame, definition: PortfolioDefinition, exits: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    warnings: list[str] = []
    if assets.empty or "asset_id" not in assets:
        return pd.DataFrame(), ("No asset master rows are available.",)
    selected_ids = [str(asset_id) for asset_id in definition.asset_ids]
    selected = assets.copy()
    selected["asset_id"] = selected["asset_id"].astype(str)
    selected = selected[selected["asset_id"].isin(selected_ids)].copy()
    missing = sorted(set(selected_ids) - set(selected["asset_id"]))
    if missing:
        warnings.append(f"Missing asset metadata for: {', '.join(missing)}")
    if definition.universe_policy == "current_survivors_only" and not exits.empty:
        exited_ids = set(exits.loc[exits["exit_status"].astype(str).ne("cancelled_exit") & exits["exit_effective_date"].notna(), "asset_id"].astype(str))
        selected = selected[~selected["asset_id"].isin(exited_ids)].copy()
        removed = sorted(set(selected_ids) & exited_ids)
        if removed:
            warnings.append(f"Excluded exited assets under current-survivors-only policy: {', '.join(removed)}")
    return selected, tuple(warnings)


def simulate_portfolio(definition: PortfolioDefinition, assets: pd.DataFrame, prices: pd.DataFrame, exits: pd.DataFrame | None = None) -> PortfolioSimulationResult:
    """Simulate a custom Rally portfolio with explicit methodology metadata.

    Prices are carried forward between valid observations. Rebalances occur on
    the first available observation date on or after scheduled period ends.
    Assets enter only when they have launched and have a valid carried-forward
    price on a rebalance date. Exits liquidate positions to cash; cash is
    redeployed only at later scheduled rebalances.
    """
    empty_series = pd.DataFrame(columns=PORTFOLIO_SERIES_COLUMNS)
    empty_constituents = pd.DataFrame(columns=PORTFOLIO_CONSTITUENT_COLUMNS)
    if definition.base_value <= 0:
        raise ValueError("base_value must be positive")
    if not definition.asset_ids:
        raise ValueError("PortfolioDefinition.asset_ids must not be empty")

    price_frame = _price_date_frame(prices)
    exit_frame = normalize_exit_events(assets, exits if exits is not None else pd.DataFrame(), prices)
    selected_assets, selection_warnings = _selected_assets(assets, definition, exit_frame)
    if selected_assets.empty:
        return PortfolioSimulationResult(definition, empty_series, empty_constituents, calculate_index_metrics(empty_series), selection_warnings or ("No selected assets are eligible.",))

    selected_ids = [str(asset_id) for asset_id in definition.asset_ids if str(asset_id) in set(selected_assets["asset_id"].astype(str))]
    target_weights = {asset_id: definition.target_weights()[asset_id] for asset_id in selected_ids if asset_id in definition.target_weights()}
    target_total = sum(target_weights.values())
    target_weights = {asset_id: weight / target_total for asset_id, weight in target_weights.items()} if target_total > 0 else {}
    if not target_weights:
        return PortfolioSimulationResult(definition, empty_series, empty_constituents, calculate_index_metrics(empty_series), selection_warnings or ("No target weights are available.",))

    p = price_frame[price_frame["asset_id"].astype(str).isin(target_weights)].copy()
    if p.empty:
        return PortfolioSimulationResult(definition, empty_series, empty_constituents, calculate_index_metrics(empty_series), selection_warnings or ("No valid price observations are available for the selected assets.",))
    p = p.sort_values(["date", "asset_id"])

    start = pd.to_datetime(definition.start_date, errors="coerce") if definition.start_date else p["date"].min()
    end = pd.to_datetime(definition.end_date, errors="coerce") if definition.end_date else p["date"].max()
    if pd.isna(start):
        start = p["date"].min()
    if pd.isna(end):
        end = p["date"].max()
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    dates = pd.DatetimeIndex(sorted({start, end, *pd.to_datetime(p["date"], errors="coerce").dropna().dt.normalize().tolist()}))
    dates = dates[(dates >= start) & (dates <= end)]
    if len(dates) == 0:
        return PortfolioSimulationResult(definition, empty_series, empty_constituents, calculate_index_metrics(empty_series), selection_warnings or ("No dates fall inside the requested simulation window.",))

    price_wide = p.pivot_table(index="date", columns="asset_id", values="last", aggfunc="last").sort_index().reindex(dates).ffill()
    offering_dates = pd.to_datetime(selected_assets.set_index("asset_id").get("offering_date"), errors="coerce").dt.normalize().to_dict() if "offering_date" in selected_assets else {}
    ticker_map = selected_assets.set_index("asset_id").get("ticker", pd.Series(dtype=object)).to_dict() if "ticker" in selected_assets else {}
    exit_by_asset = {str(row["asset_id"]): row for _, row in exit_frame[exit_frame["asset_id"].astype(str).isin(target_weights)].iterrows()} if not exit_frame.empty else {}
    rebalances = _rebalance_dates(dates, definition.rebalance_frequency)

    units: dict[str, float] = {}
    cash = float(definition.base_value)
    prev_value: float | None = None
    level = float(definition.base_value)
    series_rows: list[dict[str, object]] = []
    constituent_rows: list[dict[str, object]] = []

    for current_date in dates:
        current_date = pd.Timestamp(current_date).normalize()
        row_prices = price_wide.loc[current_date] if current_date in price_wide.index else pd.Series(dtype=float)
        price_map = {asset_id: float(row_prices.get(asset_id)) for asset_id in target_weights if pd.notna(row_prices.get(asset_id)) and float(row_prices.get(asset_id)) > 0}

        for asset_id in list(units):
            exit_row = exit_by_asset.get(asset_id)
            if exit_row is None:
                continue
            exit_date = exit_row.get("exit_effective_date")
            if pd.notna(exit_date) and current_date >= pd.Timestamp(exit_date).normalize() and str(exit_row.get("exit_status")) != "cancelled_exit":
                terminal_price = pd.to_numeric(exit_row.get("terminal_price"), errors="coerce")
                fallback_price = price_map.get(asset_id, 0.0)
                proceeds_price = float(terminal_price) if pd.notna(terminal_price) and float(terminal_price) > 0 else fallback_price
                cash += units.pop(asset_id) * proceeds_price

        invested_value = sum(units.get(asset_id, 0.0) * price_map.get(asset_id, 0.0) for asset_id in units)
        total_value = invested_value + cash
        is_rebalance = current_date in rebalances
        eligible = []
        for asset_id in target_weights:
            offering_date = offering_dates.get(asset_id)
            launched = pd.isna(offering_date) or pd.Timestamp(offering_date).normalize() <= current_date
            exit_row = exit_by_asset.get(asset_id)
            removed = exit_row is not None and pd.notna(exit_row.get("exit_effective_date")) and current_date >= pd.Timestamp(exit_row.get("exit_effective_date")).normalize() and str(exit_row.get("exit_status")) != "cancelled_exit"
            if launched and not removed and asset_id in price_map:
                eligible.append(asset_id)

        if is_rebalance:
            total_value = sum(units.get(asset_id, 0.0) * price_map.get(asset_id, 0.0) for asset_id in units) + cash
            new_units: dict[str, float] = {}
            used_capital = 0.0
            for asset_id in eligible:
                target_value = total_value * target_weights[asset_id]
                new_units[asset_id] = target_value / price_map[asset_id]
                used_capital += target_value
            units = new_units
            cash = max(total_value - used_capital, 0.0)
            invested_value = sum(units.get(asset_id, 0.0) * price_map.get(asset_id, 0.0) for asset_id in units)
            total_value = invested_value + cash

        if prev_value is None:
            period_return = 0.0
            level = float(definition.base_value)
        else:
            period_return = total_value / prev_value - 1 if prev_value else 0.0
            level *= 1 + period_return
        prev_value = total_value

        series_rows.append(
            {
                "date": current_date,
                "portfolio_id": definition.portfolio_id,
                "portfolio_name": definition.name,
                "index_level": level,
                "portfolio_value": total_value,
                "invested_asset_value": invested_value,
                "cash_value": cash,
                "period_return": period_return,
                "cumulative_return": level / definition.base_value - 1,
                "active_constituent_count": len(units),
                "eligible_constituent_count": len(eligible),
                "rebalance_flag": is_rebalance,
                **definition.methodology_metadata(),
            }
        )
        for asset_id in target_weights:
            units_held = units.get(asset_id, 0.0)
            price = price_map.get(asset_id, np.nan)
            position_value = units_held * price if pd.notna(price) else 0.0
            status = "held" if units_held > 0 else ("eligible_cash" if asset_id in eligible else "not_eligible")
            constituent_rows.append(
                {
                    "date": current_date,
                    "portfolio_id": definition.portfolio_id,
                    "asset_id": asset_id,
                    "ticker": ticker_map.get(asset_id, asset_id),
                    "price": price,
                    "units_held": units_held,
                    "position_value": position_value,
                    "portfolio_weight": position_value / total_value if total_value else 0.0,
                    "target_weight": target_weights[asset_id],
                    "constituent_status": status,
                }
            )

    series = pd.DataFrame(series_rows, columns=PORTFOLIO_SERIES_COLUMNS)
    if not series.empty:
        series["drawdown"] = series["index_level"] / series["index_level"].cummax() - 1
        series["calculated_at"] = datetime.now(timezone.utc).isoformat()
    constituents = pd.DataFrame(constituent_rows, columns=PORTFOLIO_CONSTITUENT_COLUMNS)
    metrics = calculate_index_metrics(series.rename(columns={"portfolio_value": "index_level"}) if "index_level" not in series else series)
    return PortfolioSimulationResult(definition, series, constituents, metrics, selection_warnings)


def normalize_growth_series(series: pd.DataFrame, *, label: str, date_column: str = "date", value_column: str = "index_level", base_value: float = 100.0) -> pd.DataFrame:
    if series.empty or not {date_column, value_column}.issubset(series.columns):
        return pd.DataFrame(columns=["date", "Strategy", "Growth of $100"])
    clean = series[[date_column, value_column]].copy()
    clean[date_column] = pd.to_datetime(clean[date_column], errors="coerce")
    clean[value_column] = pd.to_numeric(clean[value_column], errors="coerce")
    clean = clean.dropna().sort_values(date_column)
    clean = clean[clean[value_column] > 0]
    if clean.empty:
        return pd.DataFrame(columns=["date", "Strategy", "Growth of $100"])
    clean["Growth of $100"] = clean[value_column] / clean[value_column].iloc[0] * base_value
    clean["Strategy"] = label
    return clean.rename(columns={date_column: "date"})[["date", "Strategy", "Growth of $100"]]
