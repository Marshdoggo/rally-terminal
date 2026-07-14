from __future__ import annotations

from datetime import date

import pandas as pd

from alt_asset_explorer.schemas import LiquidityMetrics


def compute_liquidity_metrics(
    assets: pd.DataFrame,
    price_history: pd.DataFrame,
    *,
    as_of: date | None = None,
    stale_days: int = 14,
) -> pd.DataFrame:
    as_of = as_of or date.today()
    rows: list[dict] = []
    prices = price_history.copy()
    prices["date"] = pd.to_datetime(prices["date"]).dt.date

    for _, asset in assets.iterrows():
        asset_prices = prices[prices["asset_id"] == asset["asset_id"]].sort_values("date")
        if asset_prices.empty:
            continue
        latest = asset_prices.iloc[-1]
        spread = None
        if pd.notna(latest.get("bid")) and pd.notna(latest.get("ask")):
            mid = (float(latest["bid"]) + float(latest["ask"])) / 2
            spread = (float(latest["ask"]) - float(latest["bid"])) / mid if mid else None
        market_cap = float(latest["market_cap_usd"]) if pd.notna(latest.get("market_cap_usd")) else None
        turnover = float(asset_prices["volume"].sum()) / float(asset["shares"])
        trade_days = asset_prices[asset_prices["volume"] > 0]
        last_trade_date = trade_days["date"].max() if not trade_days.empty else asset_prices["date"].min()
        returns = asset_prices["last"].pct_change().dropna()
        realized_vol = float(returns.std(ddof=0) * (252 ** 0.5)) if not returns.empty else 0.0
        cumulative_max = asset_prices["last"].cummax()
        drawdown = (asset_prices["last"] / cumulative_max - 1).min()
        return_since_offering = None
        if pd.notna(asset.get("offering_price")):
            return_since_offering = float(latest["last"]) / float(asset["offering_price"]) - 1
        rows.append(
            LiquidityMetrics(
                asset_id=asset["asset_id"],
                bid_ask_spread_pct=spread,
                turnover=turnover if market_cap is None else turnover,
                days_since_last_trade=(as_of - last_trade_date).days,
                days_with_zero_trades=int((asset_prices["volume"] == 0).sum()),
                realized_volatility=max(realized_vol, 0),
                max_drawdown=float(drawdown),
                return_since_offering=return_since_offering,
                stale_mark_flag=(as_of - last_trade_date).days > stale_days,
            ).model_dump()
        )
    return pd.DataFrame(rows)
