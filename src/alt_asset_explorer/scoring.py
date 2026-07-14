from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from alt_asset_explorer.paths import CONFIG

DEFAULT_WEIGHTS = {
    "valuation_score": 0.30,
    "liquidity_score": 0.20,
    "category_momentum_score": 0.15,
    "rarity_score": 0.15,
    "data_quality_score": 0.10,
    "exit_probability_score": 0.10,
}


def load_scoring_config(path: Path | None = None) -> dict:
    path = path or CONFIG / "scoring.yml"
    if not path.exists():
        return {"weights": DEFAULT_WEIGHTS, "category_modifiers": {}}
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    config.setdefault("weights", DEFAULT_WEIGHTS)
    config.setdefault("category_modifiers", {})
    return config


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def compute_scores(assets: pd.DataFrame, navs: pd.DataFrame, liquidity: pd.DataFrame) -> pd.DataFrame:
    df = assets.merge(navs, on="asset_id", how="left").merge(liquidity, on="asset_id", how="left")
    weights = load_scoring_config()["weights"]
    rows: list[dict] = []
    for _, row in df.iterrows():
        pd_pct = row.get("premium_discount_pct")
        valuation_score = 0.5 if pd.isna(pd_pct) else _clip(0.5 - float(pd_pct))
        spread = row.get("bid_ask_spread_pct")
        stale_penalty = 0.25 if bool(row.get("stale_mark_flag")) else 0.0
        liquidity_score = _clip(1 - (float(spread) if pd.notna(spread) else 0.30) - stale_penalty)
        category_momentum_score = 0.55
        rarity_score = _clip(row.get("rarity_score", 0.5))
        data_quality_score = _clip((row.get("source_confidence", 0.5) + row.get("nav_confidence", 0.5)) / 2)
        exit_probability_score = _clip(0.45 + rarity_score * 0.20 + liquidity_score * 0.10)
        score = (
            valuation_score * weights["valuation_score"]
            + liquidity_score * weights["liquidity_score"]
            + category_momentum_score * weights["category_momentum_score"]
            + rarity_score * weights["rarity_score"]
            + data_quality_score * weights["data_quality_score"]
            + exit_probability_score * weights["exit_probability_score"]
        )
        rows.append(
            {
                "asset_id": row["asset_id"],
                "ticker": row["ticker"],
                "investment_score": round(score * 100, 2),
                "valuation_score": round(valuation_score * 100, 2),
                "liquidity_score": round(liquidity_score * 100, 2),
                "category_momentum_score": round(category_momentum_score * 100, 2),
                "rarity_score": round(rarity_score * 100, 2),
                "data_quality_score": round(data_quality_score * 100, 2),
                "exit_probability_score": round(exit_probability_score * 100, 2),
            }
        )
    return pd.DataFrame(rows)
