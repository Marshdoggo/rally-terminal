from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SCHEMA_VERSION = 1
WeightingMethod = Literal["equal", "custom"]


class CustomIndexConstituent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=300)
    ticker: str | None = Field(default=None, max_length=80)
    weight: float = Field(gt=0, le=1)


class CustomIndexDefinition(BaseModel):
    """Canonical, portable definition of a user-built Rally index."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^custom_[a-z0-9][a-z0-9_-]{5,90}$")
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    created_at: datetime
    updated_at: datetime
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    index_type: Literal["custom"] = "custom"
    weighting_method: WeightingMethod
    constituents: list[CustomIndexConstituent] = Field(min_length=1, max_length=100)
    base_value: float = Field(default=100.0, gt=0)
    start_date: str | None = None
    end_date: str | None = None
    creator: str = Field(default="anonymous", min_length=1, max_length=100)
    rebalance_policy: Literal["constant_weight_normalized_composite"] = "constant_weight_normalized_composite"
    analytics_snapshot: dict[str, float | int | str | None] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("name cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_basket(self) -> "CustomIndexDefinition":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version}")
        asset_ids = [item.asset_id for item in self.constituents]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("constituent asset IDs must be unique")
        if not math.isclose(sum(item.weight for item in self.constituents), 1.0, abs_tol=1e-6):
            raise ValueError("constituent weights must sum to 100%")
        return self


def new_custom_index_definition(
    *,
    name: str,
    description: str | None,
    constituents: list[dict[str, object]],
    weighting_method: WeightingMethod,
    base_value: float = 100.0,
    start_date: str | None = None,
    end_date: str | None = None,
    creator: str = "anonymous",
    analytics_snapshot: dict[str, float | int | str | None] | None = None,
) -> CustomIndexDefinition:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:45] or "index"
    now = datetime.now(timezone.utc)
    return CustomIndexDefinition(
        id=f"custom_{slug}_{uuid4().hex[:10]}",
        name=name,
        description=description or None,
        created_at=now,
        updated_at=now,
        weighting_method=weighting_method,
        constituents=constituents,
        base_value=base_value,
        start_date=start_date,
        end_date=end_date,
        creator=creator,
        analytics_snapshot=analytics_snapshot,
    )


@dataclass(frozen=True)
class CustomIndexBuildResult:
    series: pd.DataFrame
    contributions: pd.DataFrame
    aligned_prices: pd.DataFrame
    effective_start_date: str | None
    effective_end_date: str | None
    warnings: tuple[str, ...] = ()


def normalize_weights(asset_ids: list[str], weights: dict[str, float] | None = None) -> dict[str, float]:
    """Return positive weights summing to one, or equal weights when omitted."""
    if not asset_ids or len(asset_ids) != len(set(asset_ids)):
        raise ValueError("asset_ids must be a non-empty unique list")
    if weights is None:
        return {asset_id: 1.0 / len(asset_ids) for asset_id in asset_ids}
    if set(weights) != set(asset_ids):
        raise ValueError("weights must contain exactly the selected asset IDs")
    numeric = {asset_id: float(weights[asset_id]) for asset_id in asset_ids}
    if any(not math.isfinite(value) or value <= 0 for value in numeric.values()):
        raise ValueError("weights must be positive finite values")
    total = sum(numeric.values())
    if total <= 0:
        raise ValueError("weights must have a positive total")
    return {asset_id: value / total for asset_id, value in numeric.items()}


def build_custom_index(
    observations: pd.DataFrame,
    *,
    asset_ids: list[str],
    weights: dict[str, float] | None = None,
    base_value: float = 100.0,
    start_date: object | None = None,
    end_date: object | None = None,
) -> CustomIndexBuildResult:
    """Build a constant-weight normalized composite on common observed dates.

    No observations are fabricated or forward-filled. The usable calendar is
    the intersection of valid dates for every constituent, beginning at the
    latest constituent inception. Each constituent is normalized to the base
    value on that effective start date.
    """
    columns = ["date", "index_level", "return_period", "constituent_count"]
    contribution_columns = [
        "asset_id", "starting_weight", "asset_return", "contribution_return",
        "contribution_points", "share_of_total_move",
    ]
    empty = CustomIndexBuildResult(
        pd.DataFrame(columns=columns), pd.DataFrame(columns=contribution_columns),
        pd.DataFrame(), None, None,
    )
    if base_value <= 0:
        raise ValueError("base_value must be positive")
    resolved_weights = normalize_weights(asset_ids, weights)
    required = {"asset_id", "date", "last"}
    if observations.empty or not required.issubset(observations.columns):
        return empty

    data = observations.loc[observations["asset_id"].astype(str).isin(asset_ids), ["asset_id", "date", "last"]].copy()
    data["asset_id"] = data["asset_id"].astype(str)
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.tz_localize(None)
    data["last"] = pd.to_numeric(data["last"], errors="coerce")
    data = data.dropna(subset=["date", "last"])
    data = data[data["last"] > 0]
    if start_date is not None:
        data = data[data["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        data = data[data["date"] <= pd.Timestamp(end_date)]
    data = data.sort_values(["date", "asset_id"]).drop_duplicates(["date", "asset_id"], keep="last")
    missing = sorted(set(asset_ids) - set(data["asset_id"]))
    if missing:
        return CustomIndexBuildResult(
            empty.series, empty.contributions, empty.aligned_prices, None, None,
            (f"No valid price history for: {', '.join(missing)}",),
        )

    pivot = data.pivot(index="date", columns="asset_id", values="last").reindex(columns=asset_ids)
    latest_inception = max(data.groupby("asset_id")["date"].min())
    pivot = pivot.loc[pivot.index >= latest_inception].dropna(how="any")
    if pivot.empty:
        return CustomIndexBuildResult(
            empty.series, empty.contributions, pivot, None, None,
            ("The selected assets have no common observed dates. Try a different basket.",),
        )

    normalized = pivot.divide(pivot.iloc[0]).multiply(base_value)
    weight_series = pd.Series(resolved_weights).reindex(asset_ids)
    levels = normalized.mul(weight_series, axis=1).sum(axis=1)
    series = pd.DataFrame(
        {
            "date": levels.index,
            "index_level": levels.values,
            "return_period": levels.pct_change().values,
            "constituent_count": len(asset_ids),
        }
    )
    asset_returns = pivot.iloc[-1].divide(pivot.iloc[0]).subtract(1)
    contribution_returns = asset_returns.mul(weight_series)
    contribution_points = contribution_returns.mul(base_value)
    total_move = float(levels.iloc[-1] - levels.iloc[0])
    contributions = pd.DataFrame(
        {
            "asset_id": asset_ids,
            "starting_weight": weight_series.values,
            "asset_return": asset_returns.reindex(asset_ids).values,
            "contribution_return": contribution_returns.reindex(asset_ids).values,
            "contribution_points": contribution_points.reindex(asset_ids).values,
        }
    )
    contributions["share_of_total_move"] = (
        contributions["contribution_points"] / total_move if not math.isclose(total_move, 0.0, abs_tol=1e-12) else float("nan")
    )
    if not math.isclose(float(contributions["contribution_points"].sum()), total_move, abs_tol=1e-6):
        raise ArithmeticError("constituent contributions do not reconcile to the index move")

    warnings: list[str] = []
    total_candidate_dates = pivot.index.union(data["date"].unique()).size
    if len(pivot) < total_candidate_dates:
        warnings.append("Dates missing any constituent were excluded; prices were not forward-filled.")
    return CustomIndexBuildResult(
        series=series,
        contributions=contributions.sort_values("contribution_points", ascending=False).reset_index(drop=True),
        aligned_prices=pivot,
        effective_start_date=pivot.index[0].date().isoformat(),
        effective_end_date=pivot.index[-1].date().isoformat(),
        warnings=tuple(warnings),
    )


def calculate_index_metrics(series: pd.DataFrame, *, periods_per_year: int = 4) -> dict[str, float | int | str | None]:
    """Calculate compact portfolio analytics from index levels."""
    metrics: dict[str, float | int | str | None] = {
        "total_return": None, "cagr": None, "annualized_volatility": None,
        "sharpe_ratio": None, "sortino_ratio": None, "maximum_drawdown": None,
        "current_drawdown": None, "best_period": None, "worst_period": None,
        "observation_count": 0, "risk_band": "Unavailable",
    }
    if series.empty or not {"date", "index_level"}.issubset(series.columns):
        return metrics
    clean = series[["date", "index_level"]].copy()
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce")
    clean["index_level"] = pd.to_numeric(clean["index_level"], errors="coerce")
    clean = clean.dropna().sort_values("date")
    metrics["observation_count"] = len(clean)
    if clean.empty:
        return metrics
    levels = clean["index_level"]
    returns = levels.pct_change().dropna()
    metrics["total_return"] = float(levels.iloc[-1] / levels.iloc[0] - 1) if levels.iloc[0] else None
    running_max = levels.cummax()
    drawdowns = levels.divide(running_max).subtract(1)
    metrics["maximum_drawdown"] = float(drawdowns.min())
    metrics["current_drawdown"] = float(drawdowns.iloc[-1])
    if not returns.empty:
        metrics["best_period"] = float(returns.max())
        metrics["worst_period"] = float(returns.min())
    if len(returns) >= 2:
        volatility = float(returns.std(ddof=1) * math.sqrt(periods_per_year))
        metrics["annualized_volatility"] = volatility
        mean_annual = float(returns.mean() * periods_per_year)
        metrics["sharpe_ratio"] = mean_annual / volatility if volatility > 0 else None
        downside = returns[returns < 0]
        downside_deviation = float(downside.std(ddof=1) * math.sqrt(periods_per_year)) if len(downside) >= 2 else None
        metrics["sortino_ratio"] = mean_annual / downside_deviation if downside_deviation and downside_deviation > 0 else None
        metrics["risk_band"] = "Low" if volatility < 0.15 else "Medium" if volatility < 0.30 else "High"
    elapsed_years = (clean["date"].iloc[-1] - clean["date"].iloc[0]).days / 365.25
    if elapsed_years >= 1 and levels.iloc[0] > 0 and levels.iloc[-1] > 0:
        metrics["cagr"] = float((levels.iloc[-1] / levels.iloc[0]) ** (1 / elapsed_years) - 1)
    return metrics
