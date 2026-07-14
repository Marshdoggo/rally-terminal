from __future__ import annotations

from datetime import date

import pandas as pd

from alt_asset_explorer.schemas import NavEstimate

CONDITION_ADJUSTMENTS = {
    "mint": 1.05,
    "excellent": 1.02,
    "very_good": 0.98,
    "good": 0.93,
    "fair": 0.85,
}


def _recency_weight(comp_date: date, as_of: date) -> float:
    age_days = max((as_of - comp_date).days, 0)
    return max(0.20, 1 / (1 + age_days / 365))


def estimate_navs(
    assets: pd.DataFrame,
    comps: pd.DataFrame,
    *,
    as_of: date | None = None,
    category_modifiers: dict[str, float] | None = None,
) -> pd.DataFrame:
    as_of = as_of or date.today()
    category_modifiers = category_modifiers or {}
    rows: list[dict] = []
    if comps.empty:
        return pd.DataFrame(columns=NavEstimate.model_fields.keys())

    comps = comps.copy()
    comps["date"] = pd.to_datetime(comps["date"]).dt.date

    for _, asset in assets.iterrows():
        asset_comps = comps[comps["asset_id"] == asset["asset_id"]].copy()
        if asset_comps.empty:
            continue
        weights = []
        adjusted_prices = []
        for _, comp in asset_comps.iterrows():
            condition_key = str(comp.get("condition") or "").lower().replace(" ", "_")
            condition_adj = CONDITION_ADJUSTMENTS.get(condition_key, 1.0)
            category_adj = category_modifiers.get(str(asset["category"]), 1.0)
            price = float(comp["price_usd"]) * condition_adj * category_adj
            weight = (
                _recency_weight(comp["date"], as_of)
                * float(comp["exactness_score"])
                * float(comp["source_confidence"])
            )
            adjusted_prices.append(price)
            weights.append(weight)

        weighted = pd.Series(adjusted_prices)
        weight_series = pd.Series(weights)
        estimate = float((weighted * weight_series).sum() / weight_series.sum())
        dispersion = float(weighted.std(ddof=0) / estimate) if len(weighted) > 1 and estimate else 0.20
        confidence = max(0.05, min(0.95, float(weight_series.mean()) * (1 - min(dispersion, 0.8) / 2)))
        low = estimate * (1 - max(0.08, dispersion))
        high = estimate * (1 + max(0.08, dispersion))
        market_cap = asset.get("market_cap_usd")
        premium_discount = None
        discount_to_secondary = None
        if pd.notna(market_cap) and estimate:
            premium_discount = (float(market_cap) - estimate) / estimate
            discount_to_secondary = (estimate - float(market_cap)) / estimate
        newest = max(asset_comps["date"])
        stale = (as_of - newest).days > 180
        notes = [
            f"{len(asset_comps)} weighted comparable sales",
            f"newest comp {newest.isoformat()}",
        ]
        if stale:
            notes.append("stale-data warning: newest comp is older than 180 days")
        rows.append(
            NavEstimate(
                asset_id=asset["asset_id"],
                estimated_nav_usd=estimate,
                nav_low_usd=max(low, 0.01),
                nav_high_usd=max(high, low, 0.01),
                nav_confidence=confidence,
                premium_discount_pct=premium_discount,
                discount_to_secondary_nav=discount_to_secondary,
                valuation_notes="; ".join(notes),
            ).model_dump()
        )
    return pd.DataFrame(rows, columns=NavEstimate.model_fields.keys())
