from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd


def build_ai_context(
    assets: pd.DataFrame,
    navs: pd.DataFrame,
    liquidity: pd.DataFrame,
    scores: pd.DataFrame,
    exits: pd.DataFrame | None = None,
    *,
    as_of: date | None = None,
) -> dict:
    as_of = as_of or date.today()
    combined = assets.merge(navs, on="asset_id", how="left").merge(liquidity, on="asset_id", how="left").merge(scores, on=["asset_id", "ticker"], how="left")
    warnings = []
    for _, row in combined.iterrows():
        if bool(row.get("stale_mark_flag")):
            warnings.append(f"{row['ticker']} has a stale mark based on recent trading history.")
        if pd.notna(row.get("premium_discount_pct")) and abs(float(row["premium_discount_pct"])) > 0.25:
            warnings.append(f"{row['ticker']} has a large NAV premium/discount; verify comparable quality.")
    context = {
        "as_of": as_of.isoformat(),
        "purpose": "Deterministic research context only; not investment advice.",
        "caveats": [
            "Rally shares are securities backed by collectible entities, not direct ownership of the physical item.",
            "Offering economics, sourcing spreads, expenses, and liquidity can affect investor returns.",
            "Liquidity may be thin or periodic; stale marks are dangerous.",
            "Comparable sales may not match exact condition, provenance, size, year, or rarity.",
            "Scores are research rankings, not buy/sell recommendations.",
        ],
        "assets": json.loads(combined.where(pd.notna(combined), None).to_json(orient="records", date_format="iso")),
        "recent_exits": [] if exits is None or exits.empty else json.loads(exits.where(pd.notna(exits), None).to_json(orient="records", date_format="iso")),
        "warnings": warnings,
    }
    return context


def write_ai_context(context: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(context, indent=2, sort_keys=True), encoding="utf-8")
