from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from alt_asset_explorer.total_return import _price_date_frame


ASSET_RETURN_COLUMNS = ["asset_id", "return_1q", "return_1y", "return_full_history"]


@dataclass(frozen=True)
class AssetReturnWindow:
    """Trailing return window measured from an as-of observation date."""

    column: str
    offset: pd.DateOffset


TRAILING_RETURN_WINDOWS = (
    AssetReturnWindow("return_1q", pd.DateOffset(months=3)),
    AssetReturnWindow("return_1y", pd.DateOffset(years=1)),
)


def _period_return_at_or_before(asset_prices: pd.DataFrame, *, latest_date: pd.Timestamp, latest_price: float, offset: pd.DateOffset) -> float | None:
    """Return from the latest valid observation on or before the lookback date.

    Rally observations are sparse and mostly quarterly. To avoid interpolation or
    looking ahead, trailing windows use the most recent valid observable price on
    or before ``latest_date - offset``. If the asset had no valid observation by
    then, the return is unavailable.
    """
    anchor_date = latest_date - offset
    candidates = asset_prices[asset_prices["date"] <= anchor_date]
    if candidates.empty:
        return None
    anchor_price = pd.to_numeric(candidates.iloc[-1]["last"], errors="coerce")
    if pd.isna(anchor_price) or float(anchor_price) <= 0:
        return None
    return float(latest_price / float(anchor_price) - 1)


def build_asset_return_summary(price_history: pd.DataFrame) -> pd.DataFrame:
    """Calculate asset-level trailing and full-history returns from canonical prices.

    The input is normalized with the same price-cleaning convention used by the
    exit-aware total-return engine: valid positive prices, event-priority
    de-duplication by asset/date, and terminal buyout/sale rows preferred over
    ordinary observations on the same date.
    """
    empty = pd.DataFrame(columns=ASSET_RETURN_COLUMNS)
    if price_history.empty or not {"asset_id"}.issubset(price_history.columns):
        return empty

    prices = _price_date_frame(price_history)
    if prices.empty:
        return empty
    prices = prices.sort_values(["asset_id", "date"])

    rows: list[dict[str, object]] = []
    for asset_id, asset_prices in prices.groupby("asset_id", sort=False):
        asset_prices = asset_prices.sort_values("date").reset_index(drop=True)
        latest = asset_prices.iloc[-1]
        first = asset_prices.iloc[0]
        latest_price = float(latest["last"])
        latest_date = pd.Timestamp(latest["date"])
        row: dict[str, object] = {"asset_id": str(asset_id)}
        for window in TRAILING_RETURN_WINDOWS:
            row[window.column] = _period_return_at_or_before(
                asset_prices,
                latest_date=latest_date,
                latest_price=latest_price,
                offset=window.offset,
            )
        first_price = pd.to_numeric(first["last"], errors="coerce")
        row["return_full_history"] = float(latest_price / float(first_price) - 1) if pd.notna(first_price) and float(first_price) > 0 and len(asset_prices) >= 2 else None
        rows.append(row)

    return pd.DataFrame(rows, columns=ASSET_RETURN_COLUMNS)
