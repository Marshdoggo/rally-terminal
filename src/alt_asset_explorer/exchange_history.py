from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from alt_asset_explorer.paths import DATA_PROCESSED, ensure_dirs
from alt_asset_explorer.total_return import normalize_exit_events, rebuild_total_return_indexes

Frequency = Literal["native", "weekly", "monthly", "quarterly"]
CALCULATION_VERSION = "exchange_history_v2_exit_aware"
PRICE_EVENT_TYPES = {"chart_observation", "secondary_trade", "quote", "manual_observation", "unknown"}
TERMINAL_STATUSES = {"sold", "redeemed", "liquidated", "exited", "delisted", "buyout"}
FREQUENCY_RULES = {"weekly": "W-FRI", "monthly": "ME", "quarterly": "QE"}
ANNUALIZATION_FACTORS = {"weekly": 52, "monthly": 12, "quarterly": 4, "native": 4}


@dataclass(frozen=True)
class ExchangeHistoryConfig:
    """Centralized assumptions for exchange-history reconstruction."""

    staleness_days: int = 120
    reconciliation_tolerance: float = 1e-6
    exit_treatment: str = "remove_after_exit"
    base_index_level: float = 100.0


@dataclass(frozen=True)
class ExchangeHistoryResult:
    """Dashboard-ready exchange history outputs."""

    asset_history: pd.DataFrame
    category_history: pd.DataFrame
    market_cap_history: pd.DataFrame
    data_quality_report: pd.DataFrame
    reconciliation_report: pd.DataFrame
    validation_warnings: pd.DataFrame


def _empty_result() -> ExchangeHistoryResult:
    return ExchangeHistoryResult(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    )


def _price_date_frame(prices: pd.DataFrame) -> pd.DataFrame:
    source = prices.copy()
    if source.empty:
        return source
    if "date" not in source and "period_end" in source:
        source["date"] = source["period_end"]
    if "last" not in source and "price_per_share" in source:
        source["last"] = source["price_per_share"]
    source["date"] = pd.to_datetime(source["date"], errors="coerce")
    source["last"] = pd.to_numeric(source.get("last"), errors="coerce")
    source = source.dropna(subset=["asset_id", "date", "last"])
    if "event_type" not in source:
        source["event_type"] = "chart_observation"
    source = source[source["last"] > 0]
    source["price_source"] = np.where(source["event_type"].eq("offering_price"), "offering_price", "observed_price")
    source["is_direct_observation"] = ~source["event_type"].eq("offering_price")
    source["_priority"] = np.where(source["event_type"].eq("offering_price"), 0, 1)
    return source.sort_values(["date", "asset_id", "_priority"]).drop_duplicates(["date", "asset_id"], keep="last")


def _date_grid(assets: pd.DataFrame, observations: pd.DataFrame, frequency: Frequency) -> pd.DatetimeIndex:
    dates = []
    if "offering_date" in assets:
        dates.extend(pd.to_datetime(assets["offering_date"], errors="coerce").dropna().tolist())
    if not observations.empty:
        dates.extend(observations["date"].dropna().tolist())
    if not dates:
        return pd.DatetimeIndex([])
    start, end = min(dates).normalize(), max(dates).normalize()
    if frequency == "native":
        return pd.DatetimeIndex(sorted({pd.Timestamp(d).normalize() for d in dates if not pd.isna(d)}))
    interior = pd.date_range(start=start, end=end, freq=FREQUENCY_RULES[frequency])
    return pd.DatetimeIndex(sorted(set([start, end, *interior])))


def validate_exchange_inputs(assets: pd.DataFrame, prices: pd.DataFrame, exits: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return non-blocking data-quality warnings for exchange-history source inputs."""
    rows: list[dict[str, object]] = []
    if assets.empty:
        return pd.DataFrame([{"severity": "warning", "asset_id": None, "date": None, "warning": "empty_asset_master"}])
    a = assets.copy()
    a["offering_date"] = pd.to_datetime(a.get("offering_date"), errors="coerce")
    a["share_count"] = pd.to_numeric(a.get("share_count"), errors="coerce")
    a["offering_price_usd"] = pd.to_numeric(a.get("offering_price_usd"), errors="coerce")
    for _, row in a.iterrows():
        aid = row.get("asset_id")
        for col, warn in [("offering_date", "missing_offering_date"), ("share_count", "missing_shares_outstanding"), ("offering_price_usd", "missing_offering_price")]:
            if pd.isna(row.get(col)):
                rows.append({"severity": "warning", "asset_id": aid, "date": None, "warning": warn})
        if pd.notna(row.get("share_count")) and row.get("share_count") <= 0:
            rows.append({"severity": "error", "asset_id": aid, "date": None, "warning": "non_positive_share_count"})
        if pd.notna(row.get("offering_price_usd")) and row.get("offering_price_usd") <= 0:
            rows.append({"severity": "error", "asset_id": aid, "date": None, "warning": "non_positive_offering_price"})
    p = _price_date_frame(prices)
    if not p.empty:
        dup = p[p.duplicated(["asset_id", "date"], keep=False)]
        for _, row in dup.iterrows():
            rows.append({"severity": "warning", "asset_id": row["asset_id"], "date": row["date"].date().isoformat(), "warning": "duplicate_observation_date"})
        merged = p.merge(a[["asset_id", "offering_date"]], on="asset_id", how="left")
        bad = merged[merged["date"] < merged["offering_date"]]
        for _, row in bad.iterrows():
            rows.append({"severity": "warning", "asset_id": row["asset_id"], "date": row["date"].date().isoformat(), "warning": "price_before_offering_date"})
    if exits is not None and not exits.empty and "sale_date" in exits:
        e = exits.copy(); e["asset_id"] = e["asset_id"].astype(str); e["sale_date"] = pd.to_datetime(e["sale_date"], errors="coerce")
        for _, row in e.merge(a[["asset_id", "offering_date"]], on="asset_id", how="left").iterrows():
            if pd.notna(row.get("sale_date")) and pd.notna(row.get("offering_date")) and row["sale_date"] < row["offering_date"]:
                rows.append({"severity": "warning", "asset_id": row["asset_id"], "date": row["sale_date"].date().isoformat(), "warning": "exit_before_offering_date"})
    return pd.DataFrame(rows, columns=["severity", "asset_id", "date", "warning"])


def reconstruct_asset_history(assets: pd.DataFrame, prices: pd.DataFrame, exits: pd.DataFrame | None = None, *, frequency: Frequency = "native", config: ExchangeHistoryConfig | None = None) -> pd.DataFrame:
    """Reconstruct asset/date market caps without look-ahead price filling.

    Prices use same-day direct observations first, then the most recent prior
    valid observation. Offering price is inserted on the offering date when no
    direct observation is available. Assets are removed after terminal events.
    """
    config = config or ExchangeHistoryConfig()
    if assets.empty:
        return pd.DataFrame()
    a = assets.copy()
    a["asset_id"] = a["asset_id"].astype(str)
    a["offering_date"] = pd.to_datetime(a.get("offering_date"), errors="coerce").dt.normalize()
    a["share_count"] = pd.to_numeric(a.get("share_count"), errors="coerce")
    a["offering_price_usd"] = pd.to_numeric(a.get("offering_price_usd"), errors="coerce")
    a = a.dropna(subset=["asset_id", "offering_date", "share_count", "offering_price_usd"])
    a = a[(a["share_count"] > 0) & (a["offering_price_usd"] > 0)]
    if a.empty:
        return pd.DataFrame()
    obs = _price_date_frame(prices)
    offer_obs = a[["asset_id", "offering_date", "offering_price_usd"]].rename(columns={"offering_date": "date", "offering_price_usd": "last"})
    offer_obs["event_type"] = "offering_price"; offer_obs["price_source"] = "offering_price"; offer_obs["is_direct_observation"] = False; offer_obs["_priority"] = 0
    obs = pd.concat([obs, offer_obs], ignore_index=True, sort=False)
    obs = obs.sort_values(["date", "asset_id", "_priority"]).drop_duplicates(["date", "asset_id"], keep="last")
    grid_dates = _date_grid(a, obs, frequency)
    if grid_dates.empty:
        return pd.DataFrame()
    exit_dates = pd.Series(dtype="datetime64[ns]")
    if exits is not None and not exits.empty:
        e = normalize_exit_events(a, exits, prices)
        e = e[~e["exit_status"].eq("cancelled_exit")].copy()
        exit_dates = e.dropna(subset=["exit_effective_date"]).groupby("asset_id")["exit_effective_date"].min()
    elif "status" in a:
        terminal = a[a["status"].astype(str).str.lower().isin(TERMINAL_STATUSES)]
        if "last_quote_observed_at" in terminal:
            exit_dates = pd.to_datetime(terminal["last_quote_observed_at"], errors="coerce").dt.normalize()
            exit_dates.index = terminal["asset_id"]

    rows = []
    meta_cols = [c for c in ["asset_id", "ticker", "name", "category", "share_count", "offering_date", "offering_price_usd"] if c in a]
    for aid, meta in a[meta_cols].set_index("asset_id").iterrows():
        asset_obs = obs[obs["asset_id"].eq(aid)].sort_values("date")
        if asset_obs.empty:
            continue
        asset_grid = pd.DataFrame({"date": grid_dates})
        asset_grid = asset_grid[(asset_grid["date"] >= meta["offering_date"])]
        exit_date = exit_dates.get(aid) if not exit_dates.empty and aid in exit_dates.index else pd.NaT
        if pd.notna(exit_date):
            asset_grid = asset_grid[asset_grid["date"] <= exit_date]
        if asset_grid.empty:
            continue
        merged = pd.merge_asof(asset_grid, asset_obs[["date", "last", "price_source", "is_direct_observation"]], on="date", direction="backward")
        merged = merged.dropna(subset=["last"])
        merged["asset_id"] = aid; merged["ticker"] = meta.get("ticker"); merged["name"] = meta.get("name"); merged["category"] = meta.get("category") if pd.notna(meta.get("category")) else "unknown"
        merged["shares_outstanding"] = float(meta["share_count"]); merged["price"] = merged["last"].astype(float)
        merged["market_cap"] = merged["price"] * merged["shares_outstanding"]
        observed_index = pd.DatetimeIndex(asset_obs["date"])
        merged["last_observation_date"] = merged["date"].map(lambda d: observed_index[observed_index <= d].max())
        merged["observation_age_days"] = (merged["date"] - merged["last_observation_date"]).dt.days.fillna(0).astype(int)
        direct_dates = set(asset_obs[asset_obs["is_direct_observation"].fillna(False)]["date"])
        offering_dates = set(asset_obs[asset_obs["price_source"].eq("offering_price")]["date"])
        merged["is_direct_observation"] = merged["date"].isin(direct_dates)
        merged["price_source"] = np.select([merged["is_direct_observation"], merged["date"].isin(offering_dates)], ["observed_price", "offering_price"], default="carried_forward")
        merged["is_stale"] = merged["observation_age_days"] > config.staleness_days
        merged["is_active"] = True
        rows.append(merged.drop(columns=["last"]))
    if not rows:
        return pd.DataFrame()
    history = pd.concat(rows, ignore_index=True).sort_values(["date", "asset_id"])
    history["previous_market_cap"] = history.groupby("asset_id")["market_cap"].shift(1).fillna(0)
    history["previous_price"] = history.groupby("asset_id")["price"].shift(1)
    history["asset_return"] = history["price"] / history["previous_price"] - 1
    first = history.groupby("asset_id").cumcount().eq(0)
    history["new_issuance"] = np.where(first, history["market_cap"], 0.0)
    history["price_effect"] = np.where(first, 0.0, (history["price"] - history["previous_price"]) * history["shares_outstanding"])
    history["removed_capital"] = 0.0; history["other_adjustments"] = 0.0
    if exits is not None and not exits.empty:
        e = normalize_exit_events(a, exits, prices)
        e = e[~e["exit_status"].eq("cancelled_exit")].dropna(subset=["asset_id", "exit_effective_date"])
        for _, ex in e.iterrows():
            aid = str(ex["asset_id"]); eff = pd.Timestamp(ex["exit_effective_date"]).normalize()
            mask = history["asset_id"].astype(str).eq(aid)
            prior = history[mask & (history["date"] <= eff)].sort_values("date")
            if not prior.empty:
                idx = prior.index[-1]
                history.loc[idx, "removed_capital"] = float(prior.iloc[-1]["market_cap"])
                history.loc[idx, "market_cap"] = 0.0
                history.loc[idx, "is_active"] = False
                history.loc[idx, "is_exit_effective_date"] = True
                history.loc[idx, "terminal_price"] = ex.get("terminal_price")
                history.loc[idx, "terminal_price_source"] = ex.get("terminal_price_source")
    
    if "is_exit_effective_date" not in history:
        history["is_exit_effective_date"] = False
    history["is_exit_effective_date"] = history["is_exit_effective_date"].fillna(False)
    return history


def aggregate_exchange_history(asset_history: pd.DataFrame, *, frequency: Frequency = "native", config: ExchangeHistoryConfig | None = None) -> ExchangeHistoryResult:
    """Aggregate reconstructed asset history into category, total, coverage, and reconciliation outputs."""
    config = config or ExchangeHistoryConfig()
    if asset_history.empty:
        return _empty_result()
    h = asset_history.copy(); h["date"] = pd.to_datetime(h["date"])
    calc_at = datetime.now(timezone.utc).isoformat()
    grp = h.groupby("date", as_index=False)
    total = grp.agg(total_market_cap=("market_cap", "sum"), active_asset_count=("asset_id", "nunique"), direct_observation_asset_count=("is_direct_observation", "sum"), carried_forward_asset_count=("price_source", lambda s: int(s.eq("carried_forward").sum())), stale_asset_count=("is_stale", "sum"), median_observation_age_days=("observation_age_days", "median"), max_observation_age_days=("observation_age_days", "max"), direct_observation_market_cap=("market_cap", lambda s: float(s[h.loc[s.index, "is_direct_observation"]].sum())), carried_forward_market_cap=("market_cap", lambda s: float(s[h.loc[s.index, "price_source"].eq("carried_forward")].sum())), new_issuance=("new_issuance", "sum"), price_effect=("price_effect", "sum"), removed_capital=("removed_capital", "sum"), other_adjustments=("other_adjustments", "sum"))
    total["frequency"] = frequency
    total["direct_coverage_pct"] = total["direct_observation_market_cap"] / total["total_market_cap"].replace(0, np.nan)
    total["carried_forward_coverage_pct"] = total["carried_forward_market_cap"] / total["total_market_cap"].replace(0, np.nan)
    total["prior_market_cap"] = total["total_market_cap"].shift(1).fillna(0)
    total["net_external_flow"] = total["new_issuance"] - total["removed_capital"] + total["other_adjustments"]
    total["period_return"] = np.where(total["prior_market_cap"] > 0, (total["total_market_cap"] - total["net_external_flow"]) / total["prior_market_cap"] - 1, 0.0)
    total["return_index"] = config.base_index_level * (1 + total["period_return"].fillna(0)).cumprod()
    total["cumulative_invested_capital"] = total["net_external_flow"].cumsum()
    total["cumulative_flow_adjusted_pl"] = total["total_market_cap"] - total["cumulative_invested_capital"]
    total["drawdown"] = total["return_index"] / total["return_index"].cummax() - 1
    total["market_cap_weighted_index"] = total["return_index"]
    total["equal_weighted_period_return"] = h.groupby("date")["asset_return"].mean().reindex(total["date"]).fillna(0).to_numpy()
    total["equal_weighted_index"] = config.base_index_level * (1 + total["equal_weighted_period_return"].fillna(0)).cumprod()
    total["calculated_at"] = calc_at; total["calculation_version"] = CALCULATION_VERSION
    total["reconciliation_difference"] = total["total_market_cap"] - (total["prior_market_cap"] + total["price_effect"] + total["new_issuance"] - total["removed_capital"] + total["other_adjustments"])
    total["reconciles"] = total["reconciliation_difference"].abs() <= config.reconciliation_tolerance

    additions = h[h["new_issuance"] > 0].copy()
    if additions.empty:
        total["assets_added_count"] = 0
        total["assets_added_since_last_plot"] = "None"
    else:
        additions["added_asset_label"] = additions.apply(
            lambda row: f"{row.get('ticker') or row['asset_id']} — {row.get('name') or row['asset_id']} (${row['new_issuance']:,.0f})",
            axis=1,
        )
        added = additions.groupby("date").agg(
            assets_added_count=("asset_id", "nunique"),
            assets_added_since_last_plot=("added_asset_label", lambda labels: "; ".join(labels)),
        )
        total = total.merge(added, left_on="date", right_index=True, how="left")
        total["assets_added_count"] = total["assets_added_count"].fillna(0).astype(int)
        total["assets_added_since_last_plot"] = total["assets_added_since_last_plot"].fillna("None")

    cat = h.groupby(["date", "category"], as_index=False).agg(category_market_cap=("market_cap", "sum"), active_asset_count=("asset_id", "nunique"), direct_observation_market_cap=("market_cap", lambda s: float(s[h.loc[s.index, "is_direct_observation"]].sum())), carried_forward_market_cap=("market_cap", lambda s: float(s[h.loc[s.index, "price_source"].eq("carried_forward")].sum())), price_effect=("price_effect", "sum"), new_issuance=("new_issuance", "sum"), removed_capital=("removed_capital", "sum"), pl_contribution=("price_effect", "sum"))
    cat = cat.merge(total[["date", "total_market_cap"]], on="date", how="left")
    cat["category_weight"] = cat["category_market_cap"] / cat["total_market_cap"].replace(0, np.nan)
    cat["prior_category_market_cap"] = cat.groupby("category")["category_market_cap"].shift(1).fillna(0)
    cat["period_return"] = np.where(cat["prior_category_market_cap"] > 0, (cat["category_market_cap"] - cat["new_issuance"] + cat["removed_capital"]) / cat["prior_category_market_cap"] - 1, 0.0)
    cat["return_index"] = cat.groupby("category")["period_return"].transform(lambda s: config.base_index_level * (1 + s.fillna(0)).cumprod())
    cat["frequency"] = frequency; cat["calculated_at"] = calc_at; cat["calculation_version"] = CALCULATION_VERSION
    quality = total[["date", "active_asset_count", "direct_observation_asset_count", "carried_forward_asset_count", "stale_asset_count", "median_observation_age_days", "max_observation_age_days", "direct_coverage_pct", "carried_forward_coverage_pct"]].copy()
    recon = total[["date", "prior_market_cap", "price_effect", "new_issuance", "removed_capital", "other_adjustments", "total_market_cap", "reconciliation_difference", "reconciles"]].copy()
    return ExchangeHistoryResult(h, cat, total, quality, recon, pd.DataFrame())


def rebuild_exchange_history(assets: pd.DataFrame | None = None, prices: pd.DataFrame | None = None, exits: pd.DataFrame | None = None, *, start_date: object | None = None, end_date: object | None = None, frequency: Frequency = "native", asset_ids: list[str] | None = None, force: bool = False, output_dir: Path | None = None, config: ExchangeHistoryConfig | None = None, persist: bool = True) -> ExchangeHistoryResult:
    """Build and optionally persist exchange market-cap analytics.

    `start_date`, `end_date`, and `asset_ids` bound the rebuild inputs; aggregate
    returns are recalculated deterministically for the resulting date range.
    """
    output_dir = output_dir or DATA_PROCESSED
    if assets is None:
        assets = pd.read_csv(DATA_PROCESSED / "canonical_asset_master.csv") if (DATA_PROCESSED / "canonical_asset_master.csv").exists() else pd.DataFrame()
    if prices is None:
        prices = pd.read_csv(DATA_PROCESSED / "price_history.csv") if (DATA_PROCESSED / "price_history.csv").exists() else pd.DataFrame()
    if exits is None:
        exits = pd.read_csv(DATA_PROCESSED / "rally_exits.csv") if (DATA_PROCESSED / "rally_exits.csv").exists() else pd.DataFrame()
    warnings = validate_exchange_inputs(assets, prices, exits)
    if asset_ids:
        wanted = {str(x) for x in asset_ids}; assets = assets[assets["asset_id"].astype(str).isin(wanted)]; prices = prices[prices["asset_id"].astype(str).isin(wanted)]
    asset_history = reconstruct_asset_history(assets, prices, exits, frequency=frequency, config=config)
    if not asset_history.empty:
        if start_date is not None:
            asset_history = asset_history[asset_history["date"] >= pd.to_datetime(start_date)]
        if end_date is not None:
            asset_history = asset_history[asset_history["date"] <= pd.to_datetime(end_date)]
    result = aggregate_exchange_history(asset_history, frequency=frequency, config=config)
    result = ExchangeHistoryResult(result.asset_history, result.category_history, result.market_cap_history, result.data_quality_report, result.reconciliation_report, warnings)
    if persist:
        ensure_dirs(); output_dir.mkdir(parents=True, exist_ok=True)
        for name, frame in [("exchange_asset_history", result.asset_history), ("exchange_category_history", result.category_history), ("exchange_market_cap_history", result.market_cap_history), ("exchange_data_quality_report", result.data_quality_report), ("exchange_reconciliation_report", result.reconciliation_report), ("exchange_validation_warnings", result.validation_warnings)]:
            frame.to_csv(output_dir / f"{name}.csv", index=False)
        # Keep survivorship-bias-free investment indexes in the same rebuild pipeline.
        rebuild_total_return_indexes(assets, prices, exits, frequency="monthly", rebalance="monthly", output_dir=output_dir)
    return result


def performance_summary(market_cap_history: pd.DataFrame, *, frequency: Frequency = "native") -> dict[str, float | None]:
    """Summarize latest exchange performance metrics for KPI cards."""
    if market_cap_history.empty:
        return {}
    df = market_cap_history.copy(); returns = pd.to_numeric(df.get("period_return"), errors="coerce").dropna()
    latest = df.iloc[-1]; factor = ANNUALIZATION_FACTORS.get(frequency, 4)
    ann_return = None; ann_vol = None
    if len(returns) > 1:
        total_return = float(latest["return_index"] / df.iloc[0]["return_index"] - 1)
        years = max(len(returns) / factor, 1 / factor)
        ann_return = (1 + total_return) ** (1 / years) - 1
        ann_vol = float(returns.std(ddof=0) * np.sqrt(factor))
    return {"since_inception_return": float(latest["return_index"] / df.iloc[0]["return_index"] - 1), "annualized_return": ann_return, "annualized_volatility": ann_vol, "max_drawdown": float(df["drawdown"].min()), "current_drawdown": float(latest["drawdown"])}
