from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

AttributionSource = Literal["period_contributions", "portfolio_holdings"]

CONTRIBUTION_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ContributionResult:
    target_name: str
    target_type: str
    start_date: pd.Timestamp | None
    end_date: pd.Timestamp | None
    starting_value: float | None
    ending_value: float | None
    total_change: float | None
    total_return: float | None
    unit_label: str
    constituent_contributions: pd.DataFrame
    contribution_series: pd.DataFrame
    cash_contribution: float = 0.0
    rebalance_effect: float = 0.0
    entry_exit_effect: float = 0.0
    residual: float = 0.0
    reconciliation_metadata: dict[str, float | bool | str | None] = field(default_factory=dict)
    methodology: dict[str, str | float | int | None] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def reconciles(self) -> bool:
        return bool(self.reconciliation_metadata.get("reconciles", False))


EMPTY_CONSTITUENT_COLUMNS = [
    "asset_id", "ticker", "name", "category", "start_weight", "end_weight", "average_weight",
    "asset_return", "contribution", "contribution_share", "gross_positive_share",
    "gross_negative_share", "absolute_contribution_share", "status", "exit_indicator",
]
SERIES_COLUMNS = ["date", "asset_id", "contribution", "cumulative_contribution"]


def _empty_result(target_name: str, target_type: str, unit_label: str, warning: str) -> ContributionResult:
    return ContributionResult(
        target_name=target_name,
        target_type=target_type,
        start_date=None,
        end_date=None,
        starting_value=None,
        ending_value=None,
        total_change=None,
        total_return=None,
        unit_label=unit_label,
        constituent_contributions=pd.DataFrame(columns=EMPTY_CONSTITUENT_COLUMNS),
        contribution_series=pd.DataFrame(columns=SERIES_COLUMNS),
        warnings=(warning,),
    )


def _metadata_frame(assets: pd.DataFrame | None) -> pd.DataFrame:
    if assets is None or assets.empty or "asset_id" not in assets:
        return pd.DataFrame(columns=["asset_id", "ticker", "name", "category", "status", "exit_indicator"])
    cols = [c for c in ["asset_id", "ticker", "name", "asset_name", "category", "status", "canonical_state"] if c in assets]
    out = assets[cols].copy().drop_duplicates("asset_id")
    if "name" not in out and "asset_name" in out:
        out = out.rename(columns={"asset_name": "name"})
    if "status" not in out and "canonical_state" in out:
        out = out.rename(columns={"canonical_state": "status"})
    for col in ["ticker", "name", "category", "status"]:
        if col not in out:
            out[col] = None
    out["exit_indicator"] = out["status"].astype("string").str.contains("exit|sold|redeem|liquidat|buyout", case=False, na=False)
    return out[["asset_id", "ticker", "name", "category", "status", "exit_indicator"]]


def _finalize(
    *,
    target_name: str,
    target_type: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    starting_value: float,
    ending_value: float,
    unit_label: str,
    contributions: pd.DataFrame,
    contribution_series: pd.DataFrame,
    assets: pd.DataFrame | None,
    cash_contribution: float = 0.0,
    rebalance_effect: float = 0.0,
    entry_exit_effect: float = 0.0,
    methodology: dict[str, str | float | int | None] | None = None,
    tolerance: float = CONTRIBUTION_TOLERANCE,
) -> ContributionResult:
    total_change = ending_value - starting_value
    c = contributions.copy() if not contributions.empty else pd.DataFrame(columns=["asset_id", "contribution"])
    if "contribution" not in c and "contribution_points" in c:
        c = c.rename(columns={"contribution_points": "contribution"})
    c["contribution"] = pd.to_numeric(c.get("contribution", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    if "asset_id" in c:
        c["asset_id"] = c["asset_id"].astype(str)
    gross_pos = float(c.loc[c["contribution"] > 0, "contribution"].sum())
    gross_neg_abs = abs(float(c.loc[c["contribution"] < 0, "contribution"].sum()))
    gross_abs = float(c["contribution"].abs().sum())
    if "contribution_share" not in c:
        c["contribution_share"] = c["contribution"] / total_change if not math.isclose(total_change, 0.0, abs_tol=tolerance) else float("nan")
    c["gross_positive_share"] = c["contribution"].where(c["contribution"] > 0, 0) / gross_pos if gross_pos else float("nan")
    c["gross_negative_share"] = c["contribution"].abs().where(c["contribution"] < 0, 0) / gross_neg_abs if gross_neg_abs else float("nan")
    c["absolute_contribution_share"] = c["contribution"].abs() / gross_abs if gross_abs else float("nan")
    c = c.merge(_metadata_frame(assets), on="asset_id", how="left", suffixes=("", "_meta")) if "asset_id" in c else c
    for col in EMPTY_CONSTITUENT_COLUMNS:
        if col not in c:
            c[col] = None
    c = c[EMPTY_CONSTITUENT_COLUMNS].sort_values("contribution", ascending=False).reset_index(drop=True)
    explained = float(c["contribution"].sum()) + cash_contribution + rebalance_effect + entry_exit_effect
    residual = total_change - explained
    reconciles = math.isclose(explained + residual, total_change, abs_tol=tolerance)
    meta = {"asset_contribution_sum": float(c["contribution"].sum()), "explicit_effects": cash_contribution + rebalance_effect + entry_exit_effect, "residual": residual, "total_change": total_change, "tolerance": tolerance, "reconciles": reconciles}
    return ContributionResult(target_name, target_type, start_date, end_date, starting_value, ending_value, total_change, ending_value / starting_value - 1 if starting_value else None, unit_label, c, contribution_series, cash_contribution, rebalance_effect, entry_exit_effect, residual, meta, methodology or {})


def attribution_from_index_result(index_result, assets: pd.DataFrame | None = None, *, target_name: str, target_type: str = "Index", start_date=None, end_date=None, unit_label: str = "index points", methodology: dict[str, str | float | int | None] | None = None) -> ContributionResult:
    series = index_result.series.copy()
    if series.empty or index_result.contributions.empty:
        return _empty_result(target_name, target_type, unit_label, "Attribution requires at least two observations.")
    series["date"] = pd.to_datetime(series["date"], errors="coerce")
    series = series.dropna(subset=["date", "index_level"]).sort_values("date")
    if start_date is not None:
        series = series[series["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        series = series[series["date"] <= pd.Timestamp(end_date)]
    if len(series) < 2:
        return _empty_result(target_name, target_type, unit_label, "Selected window has insufficient index history.")
    lo, hi = series.iloc[0]["date"], series.iloc[-1]["date"]
    contrib = index_result.contributions.copy()
    contrib["date"] = pd.to_datetime(contrib["date"], errors="coerce")
    contrib = contrib[(contrib["date"] > lo) & (contrib["date"] <= hi)]
    summary = contrib.groupby("asset_id", as_index=False).agg(contribution=("contribution_points", "sum"), asset_return=("asset_return", lambda s: (s + 1).prod() - 1), average_weight=("weight", "mean"), start_weight=("weight", "first"), end_weight=("weight", "last"))
    cseries = contrib.rename(columns={"contribution_points": "contribution"})[["date", "asset_id", "contribution"]]
    cseries["cumulative_contribution"] = cseries.sort_values("date").groupby("asset_id")["contribution"].cumsum()
    return _finalize(target_name=target_name, target_type=target_type, start_date=lo, end_date=hi, starting_value=float(series.iloc[0]["index_level"]), ending_value=float(series.iloc[-1]["index_level"]), unit_label=unit_label, contributions=summary, contribution_series=cseries, assets=assets, methodology=methodology)


def attribution_from_portfolio_result(portfolio_result, assets: pd.DataFrame | None = None, *, target_name: str | None = None, start_date=None, end_date=None, unit_label: str = "growth-of-$100 dollars") -> ContributionResult:
    series = portfolio_result.series.copy()
    const = portfolio_result.constituents.copy()
    if series.empty or const.empty:
        return _empty_result(target_name or portfolio_result.definition.name, "Custom Portfolio", unit_label, "Portfolio attribution requires simulated holdings.")
    series["date"] = pd.to_datetime(series["date"], errors="coerce").dt.normalize(); const["date"] = pd.to_datetime(const["date"], errors="coerce").dt.normalize()
    series = series.dropna(subset=["date", "index_level"]).sort_values("date")
    if start_date is not None: series = series[series["date"] >= pd.Timestamp(start_date).normalize()]
    if end_date is not None: series = series[series["date"] <= pd.Timestamp(end_date).normalize()]
    if len(series) < 2:
        return _empty_result(target_name or portfolio_result.definition.name, "Custom Portfolio", unit_label, "Selected window has insufficient portfolio history.")
    dates = set(series["date"]); const = const[const["date"].isin(dates)].sort_values(["date", "asset_id"])
    wide = const.pivot_table(index="date", columns="asset_id", values="position_value", aggfunc="sum").reindex(series["date"]).fillna(0.0)
    deltas = wide.diff().iloc[1:]
    summary = pd.DataFrame({"asset_id": deltas.sum().index.astype(str), "contribution": deltas.sum().values})
    start_values = wide.iloc[0]; end_values = wide.iloc[-1]; avg_weights = wide.div(series.set_index("date")["portfolio_value"], axis=0).mean()
    summary["start_weight"] = summary["asset_id"].map((start_values / float(series.iloc[0]["portfolio_value"])).to_dict())
    summary["end_weight"] = summary["asset_id"].map((end_values / float(series.iloc[-1]["portfolio_value"])).to_dict())
    summary["average_weight"] = summary["asset_id"].map(avg_weights.to_dict())
    summary["asset_return"] = summary["asset_id"].map(((end_values / start_values.replace(0, pd.NA)) - 1).to_dict())
    cseries = deltas.reset_index().melt(id_vars="date", var_name="asset_id", value_name="contribution")
    cseries["cumulative_contribution"] = cseries.groupby("asset_id")["contribution"].cumsum()
    cash = float(pd.to_numeric(series["cash_value"], errors="coerce").iloc[-1] - pd.to_numeric(series["cash_value"], errors="coerce").iloc[0]) if "cash_value" in series else 0.0
    methodology = vars(portfolio_result.methodology) if hasattr(portfolio_result.methodology, "__dataclass_fields__") else {}
    return _finalize(target_name=target_name or portfolio_result.definition.name, target_type="Custom Portfolio", start_date=series.iloc[0]["date"], end_date=series.iloc[-1]["date"], starting_value=float(series.iloc[0]["portfolio_value"]), ending_value=float(series.iloc[-1]["portfolio_value"]), unit_label=unit_label, contributions=summary, contribution_series=cseries, assets=assets, cash_contribution=cash, methodology=methodology)


def concentration_metrics(contributions: pd.DataFrame) -> dict[str, float | int]:
    c = pd.to_numeric(contributions.get("contribution", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    pos = c[c > 0].sort_values(ascending=False); neg = c[c < 0].abs().sort_values(ascending=False); ab = c.abs().sort_values(ascending=False)
    def share(s: pd.Series, n: int) -> float:
        total = float(s.sum())
        return float(s.head(n).sum() / total) if total else float("nan")
    return {"positive_top_1": share(pos, 1), "positive_top_3": share(pos, 3), "positive_top_5": share(pos, 5), "negative_top_1": share(neg, 1), "negative_top_3": share(neg, 3), "negative_top_5": share(neg, 5), "absolute_top_1": share(ab, 1), "absolute_top_3": share(ab, 3), "absolute_top_5": share(ab, 5)}


def breadth_metrics(contributions: pd.DataFrame, *, tolerance: float = CONTRIBUTION_TOLERANCE) -> dict[str, float | int]:
    c = pd.to_numeric(contributions.get("contribution", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    pos = int((c > tolerance).sum()); neg = int((c < -tolerance).sum()); flat = int(len(c) - pos - neg)
    return {"positive_count": pos, "negative_count": neg, "flat_count": flat, "total_count": int(len(c)), "percent_positive": pos / len(c) if len(c) else float("nan")}
