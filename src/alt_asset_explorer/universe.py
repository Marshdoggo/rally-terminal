from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import pandas as pd

from alt_asset_explorer.current_universe import is_production_asset, normalize_asset_status

WeightingMethod = Literal["equal", "market_cap", "equal_weight", "market_cap_weight"]

ACTIVE_STATUSES = {"active_tradable"}
EXIT_AWARE_STATUSES = {"active_tradable", "trading_paused", "exit_announced", "pending_settlement", "exited"}


@dataclass(frozen=True)
class AssetUniverseConfig:
    """Eligibility controls for source-data driven analytical universes."""

    include_exited: bool = False
    categories: tuple[str, ...] | None = None
    as_of_date: object | None = None
    require_price_history: bool = True
    weighting_method: WeightingMethod | None = None


def _asset_id_set(values: Iterable[object]) -> set[str]:
    return {str(value) for value in values if pd.notna(value) and str(value).strip()}


def _price_frame(price_history: pd.DataFrame | None) -> pd.DataFrame:
    if price_history is None or price_history.empty:
        return pd.DataFrame(columns=["asset_id", "date", "last", "market_cap_usd"])
    prices = price_history.copy()
    if "date" not in prices and "period_end" in prices:
        prices["date"] = prices["period_end"]
    if "last" not in prices and "price_per_share" in prices:
        prices["last"] = prices["price_per_share"]
    if "market_cap_usd" not in prices and "market_cap" in prices:
        prices["market_cap_usd"] = prices["market_cap"]
    if "market_cap_usd" not in prices:
        prices["market_cap_usd"] = pd.NA
    prices["asset_id"] = prices.get("asset_id", pd.Series(dtype=object)).astype(str)
    prices["date"] = pd.to_datetime(prices.get("date"), errors="coerce")
    prices["last"] = pd.to_numeric(prices.get("last"), errors="coerce")
    prices["market_cap_usd"] = pd.to_numeric(prices.get("market_cap_usd"), errors="coerce")
    prices = prices.dropna(subset=["asset_id", "date", "last"])
    return prices[prices["last"] > 0]


def build_asset_universe(
    assets: pd.DataFrame,
    price_history: pd.DataFrame | None = None,
    *,
    as_of_date: object | None = None,
    categories: Iterable[str] | None = None,
    include_exited: bool = False,
    require_price_history: bool = True,
    weighting_method: WeightingMethod | None = None,
) -> pd.DataFrame:
    """Build a reusable Rally asset universe from canonical source data.

    The returned frame distinguishes source presence, production eligibility,
    status eligibility, price-history availability, market-cap availability, and
    final inclusion.  It does not invent static constituent lists; downstream
    calculations still decide date-level participation from actual observations.
    """
    columns = [
        "asset_id", "ticker", "name", "category", "status", "canonical_status",
        "is_production_asset", "is_currently_tradable", "is_exited_or_exit_related",
        "has_price_history", "history_row_count", "first_observation_date", "last_observation_date",
        "has_market_cap_history", "entered_by_as_of_date", "is_universe_eligible", "exclusion_reason",
    ]
    if assets is None or assets.empty or "asset_id" not in assets:
        return pd.DataFrame(columns=columns)

    out = assets.copy()
    out["asset_id"] = out["asset_id"].astype(str)
    if "category" not in out:
        out["category"] = pd.NA
    if "status" not in out:
        out["status"] = pd.NA
    out["canonical_status"] = out["status"].map(normalize_asset_status)
    out["is_production_asset"] = out.apply(is_production_asset, axis=1)
    out["is_currently_tradable"] = out["canonical_status"].isin(ACTIVE_STATUSES)
    out["is_exited_or_exit_related"] = out["canonical_status"].isin({"exit_announced", "pending_settlement", "exited"})

    wanted_categories = {str(category) for category in categories} if categories is not None else None
    if wanted_categories is not None:
        out = out[out["category"].astype(str).isin(wanted_categories)].copy()

    prices = _price_frame(price_history)
    if as_of_date is not None and not prices.empty:
        prices = prices[prices["date"] <= pd.to_datetime(as_of_date)]
    if not prices.empty:
        history = prices.groupby("asset_id", as_index=False).agg(
            history_row_count=("date", "count"),
            first_observation_date=("date", "min"),
            last_observation_date=("date", "max"),
            has_market_cap_history=("market_cap_usd", lambda s: bool(pd.to_numeric(s, errors="coerce").gt(0).any())),
        )
        out = out.merge(history, on="asset_id", how="left")
    else:
        out["history_row_count"] = pd.NA
        out["first_observation_date"] = pd.NaT
        out["last_observation_date"] = pd.NaT
        out["has_market_cap_history"] = False
    out["history_row_count"] = pd.to_numeric(out["history_row_count"], errors="coerce").fillna(0).astype(int)
    out["has_price_history"] = out["history_row_count"].gt(0)
    out["has_market_cap_history"] = out["has_market_cap_history"].astype("boolean").fillna(False).astype(bool)

    as_of_ts = pd.to_datetime(as_of_date) if as_of_date is not None else None
    if as_of_ts is not None and "offering_date" in out:
        entered = pd.to_datetime(out["offering_date"], errors="coerce") <= as_of_ts
        out["entered_by_as_of_date"] = entered.fillna(False)
    else:
        out["entered_by_as_of_date"] = True

    status_allowed = out["canonical_status"].isin(EXIT_AWARE_STATUSES if include_exited else ACTIVE_STATUSES)
    if weighting_method in {"market_cap", "market_cap_weight"}:
        method_ready = out["has_market_cap_history"]
    else:
        method_ready = out["has_price_history"] | ~require_price_history
    included = out["is_production_asset"] & status_allowed & out["entered_by_as_of_date"] & method_ready
    if require_price_history:
        included &= out["has_price_history"]
    out["is_universe_eligible"] = included

    reasons: list[str] = []
    for _, row in out.iterrows():
        parts: list[str] = []
        if not row["is_production_asset"]:
            parts.append("not_production_asset")
        if not status_allowed.loc[row.name]:
            parts.append("status_excluded_active_only" if not include_exited else "status_not_supported")
        if not bool(row["entered_by_as_of_date"]):
            parts.append("not_entered_by_as_of_date")
        if require_price_history and not bool(row["has_price_history"]):
            parts.append("missing_price_history")
        if weighting_method in {"market_cap", "market_cap_weight"} and not bool(row["has_market_cap_history"]):
            parts.append("missing_market_cap_history")
        reasons.append("included" if not parts else "|".join(parts))
    out["exclusion_reason"] = reasons
    return out[[column for column in columns if column in out]].sort_values("asset_id").reset_index(drop=True)


def eligible_asset_ids(universe: pd.DataFrame) -> list[str]:
    if universe.empty or "is_universe_eligible" not in universe:
        return []
    return sorted(_asset_id_set(universe.loc[universe["is_universe_eligible"], "asset_id"]))


def build_asset_universe_diagnostics(
    assets: pd.DataFrame,
    price_history: pd.DataFrame | None = None,
    exits: pd.DataFrame | None = None,
    *,
    include_exited: bool = True,
) -> pd.DataFrame:
    """Return a compact developer diagnostic for source-data propagation."""
    universe = build_asset_universe(assets, price_history, include_exited=include_exited, require_price_history=False)
    price_universe = build_asset_universe(assets, price_history, include_exited=include_exited, require_price_history=True, weighting_method="equal")
    cap_universe = build_asset_universe(assets, price_history, include_exited=include_exited, require_price_history=True, weighting_method="market_cap")
    if universe.empty:
        return universe
    diag = universe.copy()
    price_ready = price_universe.set_index("asset_id")["is_universe_eligible"] if not price_universe.empty else pd.Series(dtype=bool)
    cap_ready = cap_universe.set_index("asset_id")["is_universe_eligible"] if not cap_universe.empty else pd.Series(dtype=bool)
    diag["quarterly_eligible"] = diag["asset_id"].map(price_ready).fillna(False).astype(bool)
    diag["equal_weight_eligible"] = diag["quarterly_eligible"]
    diag["market_cap_weight_eligible"] = diag["asset_id"].map(cap_ready).fillna(False).astype(bool)
    exit_ids = _asset_id_set(exits["asset_id"]) if exits is not None and not exits.empty and "asset_id" in exits else set()
    diag["exit_recognized"] = diag["asset_id"].isin(exit_ids) | diag["canonical_status"].isin({"exited", "pending_settlement"})
    return diag
