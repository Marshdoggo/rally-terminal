from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from alt_asset_explorer.indices import build_index_from_selection
from alt_asset_explorer.universe import build_asset_universe, eligible_asset_ids


SECTOR_PERFORMANCE_COLUMNS = [
    "category",
    "since_inception",
    "last_year",
    "annualized_volatility",
    "volatility_band",
    "constituent_count",
    "researched_asset_count",
    "target_asset_count",
    "coverage_pct",
    "coverage_status",
]


def completed_categories(coverage: pd.DataFrame, assets: pd.DataFrame) -> list[str]:
    """Categories whose currently trading research targets all have observations."""
    if coverage.empty or assets.empty or "category" not in coverage:
        return []
    targets = coverage.copy()
    if {"asset_id", "status"}.issubset(assets.columns):
        statuses = assets[["asset_id", "status"]].drop_duplicates("asset_id")
        targets = targets.merge(statuses, on="asset_id", how="left", suffixes=("", "_asset"))
        targets = targets[targets["status"].astype(str).str.lower().eq("trading")]
    if targets.empty:
        return []
    observed = pd.to_numeric(targets.get("observation_count"), errors="coerce").fillna(0).gt(0)
    targets = targets.assign(_researched=observed)
    completion = targets.groupby("category")["_researched"].agg(["all", "size"])
    return sorted(completion[(completion["all"]) & (completion["size"] > 0)].index.astype(str).tolist())


def calculate_sector_performance(
    observations: pd.DataFrame,
    assets: pd.DataFrame,
    categories: Iterable[str],
    *,
    weighting_method: str = "equal",
    current_trading_only: bool = True,
    coverage: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calculate sector statistics as soon as a category has usable observations.

    Coverage is reported independently from calculation eligibility so a sector
    can appear while research is still in progress instead of waiting for every
    target asset to be completed.
    """
    if observations.empty or assets.empty:
        return pd.DataFrame(columns=SECTOR_PERFORMANCE_COLUMNS)
    rows: list[dict[str, object]] = []
    for category in categories:
        if "status" in assets:
            category_universe = build_asset_universe(
                assets,
                observations,
                categories=[str(category)],
                include_exited=not current_trading_only,
                require_price_history=True,
                weighting_method=weighting_method,
            )
            category_assets = category_universe[category_universe["is_universe_eligible"]].copy()
            ids = eligible_asset_ids(category_universe)
            target_universe = build_asset_universe(
                assets,
                observations,
                categories=[str(category)],
                include_exited=not current_trading_only,
                require_price_history=False,
            )
            target_ids = set(eligible_asset_ids(target_universe))
        else:
            category_assets = assets[assets["category"].astype(str).eq(str(category))].copy()
            ids = category_assets["asset_id"].astype(str).tolist()
            target_ids = set(ids)
        if coverage is not None and not coverage.empty and {"asset_id", "category"}.issubset(coverage.columns):
            coverage_targets = coverage[coverage["category"].astype(str).eq(str(category))].copy()
            if current_trading_only and "status" in assets:
                coverage_targets = coverage_targets[coverage_targets["asset_id"].astype(str).isin(target_ids)]
            target_ids = set(coverage_targets["asset_id"].astype(str))
        category_observations = observations[observations["asset_id"].astype(str).isin(target_ids)]
        researched_asset_count = int(category_observations["asset_id"].astype(str).nunique())
        target_asset_count = len(target_ids)
        coverage_pct = researched_asset_count / target_asset_count if target_asset_count else None
        result = build_index_from_selection(
            observations,
            asset_ids=ids,
            weighting_method=weighting_method,
            index_id=f"sector_{category}_{weighting_method}",
            index_name=str(category),
            category=str(category),
        )
        series = result.series.copy()
        if series.empty:
            continue
        series["date"] = pd.to_datetime(series["date"], errors="coerce")
        series = series.dropna(subset=["date", "index_level"]).sort_values("date")
        if series.empty:
            continue
        first_level = float(series.iloc[0]["index_level"])
        last_level = float(series.iloc[-1]["index_level"])
        since_inception = last_level / first_level - 1 if first_level else None
        year_cutoff = series.iloc[-1]["date"] - pd.DateOffset(years=1)
        prior = series[series["date"] <= year_cutoff]
        year_base = float(prior.iloc[-1]["index_level"]) if not prior.empty else None
        last_year = last_level / year_base - 1 if year_base else None
        returns = pd.to_numeric(series["return_1d"], errors="coerce").dropna()
        if returns.empty:
            continue
        volatility = float(returns.std(ddof=1) * (4**0.5)) if len(returns) > 1 else None
        if volatility is None or pd.isna(volatility):
            band = "Unavailable"
        elif volatility < 0.15:
            band = "Low"
        elif volatility < 0.30:
            band = "Medium"
        else:
            band = "High"
        rows.append(
            {
                "category": str(category),
                "since_inception": since_inception,
                "last_year": last_year,
                "annualized_volatility": volatility,
                "volatility_band": band,
                "constituent_count": int(series.iloc[-1]["constituent_count"]),
                "researched_asset_count": researched_asset_count,
                "target_asset_count": target_asset_count,
                "coverage_pct": coverage_pct,
                "coverage_status": "Complete" if coverage_pct is not None and coverage_pct >= 1 else "Building",
            }
        )
    return pd.DataFrame(rows, columns=SECTOR_PERFORMANCE_COLUMNS).sort_values("since_inception", ascending=False)
