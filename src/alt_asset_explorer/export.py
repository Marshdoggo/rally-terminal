from __future__ import annotations

from datetime import date

import pandas as pd

MME_COLUMNS = [
    "date",
    "ticker",
    "name",
    "universe",
    "category",
    "price",
    "return_1d",
    "return_7d",
    "return_30d",
    "volatility",
    "sharpe",
    "sortino",
    "max_drawdown",
    "source_quality",
]

MME_UNIVERSE_COLUMNS = [
    "ticker",
    "name",
    "universe",
    "category",
    "metric_1",
    "metric_2",
    "metric_3",
    "score",
    "last_updated",
]

NEWSLETTER_COLUMNS = [
    "ticker",
    "name",
    "category",
    "subcategory",
    "status",
    "metric",
    "value",
    "source_url",
    "notes",
    "last_updated",
]


def _source_quality(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def build_universe_export(
    assets: pd.DataFrame,
    price_history: pd.DataFrame,
    liquidity: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> pd.DataFrame:
    as_of = as_of or date.today()
    prices = price_history.copy()
    prices["date"] = pd.to_datetime(prices["date"]).dt.date
    rows: list[dict] = []
    for _, asset in assets.iterrows():
        asset_prices = prices[prices["asset_id"] == asset["asset_id"]].sort_values("date")
        if asset_prices.empty:
            continue
        latest = asset_prices.iloc[-1]
        returns = asset_prices.set_index(pd.to_datetime(asset_prices["date"]))["last"].pct_change()
        def window_return(days: int):
            cutoff = pd.Timestamp(latest["date"]) - pd.Timedelta(days=days)
            history = asset_prices[pd.to_datetime(asset_prices["date"]) <= cutoff]
            if history.empty:
                return None
            return float(latest["last"] / history.iloc[-1]["last"] - 1)

        vol = float(returns.dropna().std(ddof=0) * (252 ** 0.5)) if not returns.dropna().empty else 0.0
        mean = float(returns.dropna().mean() * 252) if not returns.dropna().empty else 0.0
        downside = returns[returns < 0].dropna()
        sortino = mean / float(downside.std(ddof=0) * (252 ** 0.5)) if len(downside) > 1 else None
        sharpe = mean / vol if vol else None
        liq_row = liquidity[liquidity["asset_id"] == asset["asset_id"]]
        max_drawdown = float(liq_row.iloc[0]["max_drawdown"]) if not liq_row.empty else None
        rows.append(
            {
                "date": as_of.isoformat(),
                "ticker": asset["ticker"],
                "name": asset["name"],
                "universe": "collectibles",
                "category": asset["category"],
                "price": latest["last"],
                "return_1d": window_return(1),
                "return_7d": window_return(7),
                "return_30d": window_return(30),
                "volatility": vol,
                "sharpe": sharpe,
                "sortino": sortino,
                "max_drawdown": max_drawdown,
                "source_quality": _source_quality(float(asset.get("source_confidence", 0.5))),
            }
        )
    return pd.DataFrame(rows, columns=MME_COLUMNS)


def build_mme_universe_export(decision_universe: pd.DataFrame, *, as_of: date | None = None) -> pd.DataFrame:
    as_of = as_of or date.today()
    rows = []
    for _, row in decision_universe.iterrows():
        rows.append(
            {
                "ticker": row.get("ticker"),
                "name": row.get("name"),
                "universe": "alternative_assets",
                "category": row.get("category"),
                "metric_1": row.get("discount_to_secondary_nav"),
                "metric_2": row.get("nav_confidence"),
                "metric_3": row.get("liquidity_score"),
                "score": row.get("mispricing_score"),
                "last_updated": as_of.isoformat(),
            }
        )
    return pd.DataFrame(rows, columns=MME_UNIVERSE_COLUMNS)


def _row_value(row: pd.Series, name: str):
    value = row.get(name)
    return None if pd.isna(value) else value


def _newsletter_row(row: pd.Series, metric: str, value, notes: str, as_of: date) -> dict:
    return {
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "category": row.get("category"),
        "subcategory": row.get("subcategory"),
        "status": row.get("status"),
        "metric": metric,
        "value": value,
        "source_url": _row_value(row, "sec_filing_url"),
        "notes": notes,
        "last_updated": as_of.isoformat(),
    }


def build_newsletter_exports(decision_universe: pd.DataFrame, *, as_of: date | None = None) -> dict[str, pd.DataFrame]:
    as_of = as_of or date.today()
    if decision_universe.empty:
        empty = pd.DataFrame(columns=NEWSLETTER_COLUMNS)
        return {
            "newsletter_market_movers": empty,
            "newsletter_notable_discounts": empty,
            "newsletter_recent_exits": empty,
            "newsletter_weak_data": empty,
        }

    df = decision_universe.copy()
    market_movers = df[df["current_market_cap_usd"].notna()].copy()
    market_movers["abs_premium_to_offering"] = pd.to_numeric(market_movers.get("premium_to_offering"), errors="coerce").abs()
    market_rows = [
        _newsletter_row(row, "premium_to_offering", row.get("premium_to_offering"), "Live Rally market cap compared with SEC offering cap.", as_of)
        for _, row in market_movers.sort_values("abs_premium_to_offering", ascending=False).head(25).iterrows()
    ]

    discounts = df[
        (df["status"].astype(str) == "trading")
        & pd.to_numeric(df.get("discount_to_secondary_nav"), errors="coerce").notna()
        & (pd.to_numeric(df.get("discount_to_secondary_nav"), errors="coerce") < 0)
    ].copy()
    discount_rows = [
        _newsletter_row(row, "discount_to_secondary_nav", row.get("discount_to_secondary_nav"), "Negative values indicate current market cap below estimated secondary NAV.", as_of)
        for _, row in discounts.sort_values("discount_to_secondary_nav").head(25).iterrows()
    ]

    exits = df[df["exit_market_cap_usd"].notna()].copy()
    exits["exit_return_vs_offering"] = pd.to_numeric(exits["exit_market_cap_usd"], errors="coerce") / pd.to_numeric(exits["offering_market_cap_usd"], errors="coerce") - 1
    exit_rows = [
        _newsletter_row(row, "exit_return_vs_offering", row.get("exit_return_vs_offering"), f"Exit date: {row.get('exit_date')}", as_of)
        for _, row in exits.sort_values("exit_date", ascending=False).head(25).iterrows()
    ]

    weak = df[
        df["current_market_cap_usd"].isna()
        | df["offering_market_cap_usd"].isna()
        | (pd.to_numeric(df.get("comp_count"), errors="coerce").fillna(0) == 0)
        | (pd.to_numeric(df.get("nav_confidence"), errors="coerce").fillna(0) < 0.25)
    ].copy()
    weak_rows = [
        _newsletter_row(row, "data_completeness", row.get("nav_confidence"), "Missing live price, offering cap, comps, or robust NAV confidence.", as_of)
        for _, row in weak.sort_values(["category", "ticker"]).head(50).iterrows()
    ]

    return {
        "newsletter_market_movers": pd.DataFrame(market_rows, columns=NEWSLETTER_COLUMNS),
        "newsletter_notable_discounts": pd.DataFrame(discount_rows, columns=NEWSLETTER_COLUMNS),
        "newsletter_recent_exits": pd.DataFrame(exit_rows, columns=NEWSLETTER_COLUMNS),
        "newsletter_weak_data": pd.DataFrame(weak_rows, columns=NEWSLETTER_COLUMNS),
    }
