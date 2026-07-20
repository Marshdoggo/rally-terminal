from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import pandas as pd

from alt_asset_explorer.manual_imports import PRICE_EVENT_TYPES


RALLY_INDEX_COLUMNS = [
    "index_id",
    "index_name",
    "date",
    "index_level",
    "return_1d",
    "constituent_count",
    "weighting_method",
    "category",
    "data_quality_notes",
    "max_staleness_days",
]

QUARTERLY_INDEX_EVENT_TYPES = PRICE_EVENT_TYPES | {"offering_price", "buyout", "asset_sale", "distribution"}

WeightingMethod = Literal["equal", "market_cap"]


@dataclass(frozen=True)
class IndexBuildResult:
    """A generated index and the period-level attribution behind it."""

    series: pd.DataFrame
    contributions: pd.DataFrame


CONTRIBUTION_COLUMNS = [
    "date",
    "asset_id",
    "asset_return",
    "weight",
    "contribution_return",
    "contribution_points",
]


def _index_rows(
    daily: pd.DataFrame,
    *,
    index_id: str,
    index_name: str,
    weighting_method: str,
    category: str,
    data_quality_notes: str,
) -> list[dict]:
    result = build_index_from_selection(
        daily,
        weighting_method=weighting_method,
        index_id=index_id,
        index_name=index_name,
        category=category,
        data_quality_notes=data_quality_notes,
    )
    return result.series.to_dict("records")


def build_index_from_selection(
    observations: pd.DataFrame,
    *,
    asset_ids: Iterable[str] | None = None,
    weighting_method: WeightingMethod = "equal",
    index_id: str = "custom_index",
    index_name: str = "Custom Rally Index",
    category: str = "custom",
    start_date: object | None = None,
    end_date: object | None = None,
    base_level: float = 100.0,
    data_quality_notes: str = "Generated from the selected observed Rally price history.",
) -> IndexBuildResult:
    """Build an index from an arbitrary constituent selection.

    This is the core index API. Category indices are simply selections supplied
    by callers; the calculation itself has no category assumptions. Missing
    prices are not filled, and market-cap weights use the prior observation.
    """
    if weighting_method not in {"equal", "market_cap"}:
        raise ValueError("weighting_method must be 'equal' or 'market_cap'")

    empty_series = pd.DataFrame(columns=RALLY_INDEX_COLUMNS)
    empty_contributions = pd.DataFrame(columns=CONTRIBUTION_COLUMNS)
    if observations.empty or not {"asset_id", "date", "last"}.issubset(observations.columns):
        return IndexBuildResult(empty_series, empty_contributions)

    selected = observations.copy()
    selected["asset_id"] = selected["asset_id"].astype(str)
    if asset_ids is not None:
        wanted = {str(asset_id) for asset_id in asset_ids}
        selected = selected[selected["asset_id"].isin(wanted)]
    selected["date"] = pd.to_datetime(selected["date"], errors="coerce").dt.date
    selected["last"] = pd.to_numeric(selected["last"], errors="coerce")
    if "market_cap_usd" not in selected:
        selected["market_cap_usd"] = None
    selected["market_cap_usd"] = pd.to_numeric(selected["market_cap_usd"], errors="coerce")

    parsed_start = pd.to_datetime(start_date, errors="coerce") if start_date is not None else None
    parsed_end = pd.to_datetime(end_date, errors="coerce") if end_date is not None else None
    if parsed_start is not None and not pd.isna(parsed_start):
        selected = selected[selected["date"] >= parsed_start.date()]
    if parsed_end is not None and not pd.isna(parsed_end):
        selected = selected[selected["date"] <= parsed_end.date()]

    selected = selected.dropna(subset=["asset_id", "date", "last"])
    selected = selected[selected["last"] > 0]
    selected = selected.sort_values(["date", "asset_id"]).drop_duplicates(["date", "asset_id"], keep="last")
    if selected.empty:
        return IndexBuildResult(empty_series, empty_contributions)

    rows: list[dict[str, object]] = []
    attribution: list[dict[str, object]] = []
    level = float(base_level)
    previous_prices: pd.Series | None = None
    previous_market_caps = pd.Series(dtype=float)

    for obs_date, day in selected.groupby("date", sort=True):
        eligible = day.dropna(subset=["last"])
        if weighting_method == "market_cap":
            eligible = eligible.dropna(subset=["market_cap_usd"])
            eligible = eligible[eligible["market_cap_usd"] > 0]
        if eligible.empty:
            continue

        prices = eligible.set_index("asset_id")["last"].astype(float)
        period_return: float | None = None
        previous_level = level
        if previous_prices is not None:
            joined = pd.concat([previous_prices.rename("previous"), prices.rename("current")], axis=1).dropna()
            if not joined.empty:
                returns = joined["current"] / joined["previous"] - 1
                if weighting_method == "equal":
                    weights = pd.Series(1.0 / len(returns), index=returns.index)
                else:
                    current_caps = eligible.set_index("asset_id")["market_cap_usd"].astype(float)
                    weight_source = previous_market_caps.reindex(joined.index).fillna(current_caps.reindex(joined.index))
                    weight_source = weight_source[weight_source > 0].dropna()
                    returns = returns.reindex(weight_source.index)
                    weights = weight_source / weight_source.sum() if not weight_source.empty else pd.Series(dtype=float)
                if not weights.empty:
                    contribution_returns = returns * weights
                    period_return = float(contribution_returns.sum())
                    level *= 1 + period_return
                    for asset_id, contribution_return in contribution_returns.items():
                        attribution.append(
                            {
                                "date": obs_date.isoformat(),
                                "asset_id": asset_id,
                                "asset_return": float(returns.loc[asset_id]),
                                "weight": float(weights.loc[asset_id]),
                                "contribution_return": float(contribution_return),
                                "contribution_points": float(previous_level * contribution_return),
                            }
                        )

        rows.append(
            {
                "index_id": index_id,
                "index_name": index_name,
                "date": obs_date.isoformat(),
                "index_level": round(level, 6),
                "return_1d": period_return,
                "constituent_count": int(len(prices)),
                "weighting_method": weighting_method,
                "category": category,
                "data_quality_notes": data_quality_notes,
                "max_staleness_days": 0,
            }
        )
        previous_prices = prices
        previous_market_caps = eligible.set_index("asset_id")["market_cap_usd"].astype(float)

    return IndexBuildResult(
        pd.DataFrame(rows, columns=RALLY_INDEX_COLUMNS),
        pd.DataFrame(attribution, columns=CONTRIBUTION_COLUMNS),
    )


def summarize_contributions(contributions: pd.DataFrame, assets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aggregate period attribution into constituent contributions in index points."""
    columns = ["asset_id", "contribution_points", "contribution_return", "name", "ticker", "category"]
    if contributions.empty:
        return pd.DataFrame(columns=columns)
    summary = (
        contributions.groupby("asset_id", as_index=False)
        .agg(contribution_points=("contribution_points", "sum"), contribution_return=("contribution_return", "sum"))
        .sort_values("contribution_points", ascending=False)
    )
    if assets is not None and not assets.empty and "asset_id" in assets:
        metadata = assets[[column for column in ["asset_id", "name", "asset_name", "ticker", "category"] if column in assets]].copy()
        if "name" not in metadata and "asset_name" in metadata:
            metadata = metadata.rename(columns={"asset_name": "name"})
        metadata = metadata.drop_duplicates("asset_id")
        summary = summary.merge(metadata, on="asset_id", how="left")
    for column in ["name", "ticker", "category"]:
        if column not in summary:
            summary[column] = None
    return summary[columns]


def build_rally_indices(price_history: pd.DataFrame) -> pd.DataFrame:
    """Build prototype Rally index series from observed quote history.

    Missing prices are not imputed. Market-cap-weighted rows exclude assets
    without market cap on that observation date.
    """
    if price_history.empty or not {"asset_id", "date", "last"}.issubset(price_history.columns):
        return pd.DataFrame(columns=RALLY_INDEX_COLUMNS)

    daily = price_history.copy()
    if "event_type" in daily:
        daily = daily[daily["event_type"].isna() | daily["event_type"].astype(str).isin(PRICE_EVENT_TYPES)]
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce").dt.date
    daily["last"] = pd.to_numeric(daily["last"], errors="coerce")
    if "market_cap_usd" not in daily:
        daily["market_cap_usd"] = None
    daily["market_cap_usd"] = pd.to_numeric(daily["market_cap_usd"], errors="coerce")
    daily = daily.dropna(subset=["asset_id", "date", "last"])
    daily = daily[daily["last"] > 0]
    if daily.empty:
        return pd.DataFrame(columns=RALLY_INDEX_COLUMNS)
    daily = daily.sort_values(["date", "asset_id"]).drop_duplicates(subset=["date", "asset_id"], keep="last")

    notes = "Prototype index from local manual/imported Rally price snapshots; limited price-history coverage."
    rows = [
        *_index_rows(
            daily,
            index_id="rally_market_equal_weight",
            index_name="Equal-Weighted Rally Market Index",
            weighting_method="equal",
            category="all",
            data_quality_notes=notes,
        ),
        *_index_rows(
            daily,
            index_id="rally_market_market_cap_weight",
            index_name="Market-Cap-Weighted Rally Market Index",
            weighting_method="market_cap",
            category="all",
            data_quality_notes=notes,
        ),
    ]
    return pd.DataFrame(rows, columns=RALLY_INDEX_COLUMNS)


def _quarterly_source(price_history: pd.DataFrame, assets: pd.DataFrame | None = None) -> pd.DataFrame:
    if price_history.empty:
        return pd.DataFrame(columns=["asset_id", "date", "last", "market_cap_usd", "category"])
    source = price_history.copy()
    if "frequency" in source:
        frequency = source["frequency"].astype("string").str.strip().str.lower()
        source = source[frequency.isna() | frequency.eq("") | frequency.eq("quarterly")]
    if "period_end" not in source or source.empty:
        return pd.DataFrame(columns=["asset_id", "date", "last", "market_cap_usd", "category"])
    if "event_type" in source:
        source = source[source["event_type"].isna() | source["event_type"].astype(str).isin(QUARTERLY_INDEX_EVENT_TYPES)]
    source["date"] = pd.to_datetime(source["period_end"], errors="coerce").dt.date
    source["last"] = pd.to_numeric(source["last"] if "last" in source else source.get("price_per_share"), errors="coerce")
    if "market_cap_usd" not in source:
        source["market_cap_usd"] = source.get("market_cap")
    source["market_cap_usd"] = pd.to_numeric(source["market_cap_usd"], errors="coerce")
    if assets is not None and not assets.empty and {"asset_id", "category"}.issubset(assets.columns):
        source = source.merge(assets[["asset_id", "category"]].drop_duplicates("asset_id"), on="asset_id", how="left")
    elif "category" not in source:
        source["category"] = "all"
    source = source.dropna(subset=["asset_id", "date", "last"])
    source = source[source["last"] > 0]
    if "event_type" in source:
        source["_event_priority"] = source["event_type"].astype(str).map({"offering_price": 0, **{event: 1 for event in PRICE_EVENT_TYPES}, "buyout": 2, "asset_sale": 2, "distribution": 2}).fillna(1)
    else:
        source["_event_priority"] = 1
    return (
        source.sort_values(["date", "asset_id", "_event_priority"])
        .drop_duplicates(subset=["date", "asset_id"], keep="last")
        .drop(columns=["_event_priority"], errors="ignore")
    )


def prepare_quarterly_observations(price_history: pd.DataFrame, assets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return cleaned quarter-end observations for interactive index building."""
    return _quarterly_source(price_history, assets)


def build_quarterly_rally_indices(price_history: pd.DataFrame, assets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build quarterly historical index prototypes from quarter-end manual observations.

    The index period is `period_end`; the source observation date remains
    preserved in the normalized observations and is not replaced here.
    """
    quarterly = _quarterly_source(price_history, assets)
    if quarterly.empty:
        return pd.DataFrame(columns=RALLY_INDEX_COLUMNS)

    notes = (
        "Quarterly Historical Index Prototype from manually transcribed Rally observations; "
        "period_end is the calendar quarter, observed_at may be earlier, and no interpolation is used."
    )
    rows: list[dict] = []
    groups: list[tuple[str, str, pd.DataFrame]] = [("all", "Rally Market", quarterly)]
    if "category" in quarterly:
        for category, category_frame in quarterly.dropna(subset=["category"]).groupby("category", sort=True):
            groups.append((str(category), f"Rally {str(category).replace('_', ' ').title()}", category_frame))

    for category, label, frame in groups:
        suffix = category.lower().replace(" ", "_")
        rows.extend(
            _index_rows(
                frame,
                index_id=f"rally_quarterly_{suffix}_equal_weight",
                index_name=f"{label} Equal-Weighted Quarterly Historical Index Prototype",
                weighting_method="equal",
                category=category,
                data_quality_notes=notes,
            )
        )
        rows.extend(
            _index_rows(
                frame,
                index_id=f"rally_quarterly_{suffix}_market_cap_weight",
                index_name=f"{label} Market-Cap-Weighted Quarterly Historical Index Prototype",
                weighting_method="market_cap",
                category=category,
                data_quality_notes=notes,
            )
        )
    return pd.DataFrame(rows, columns=RALLY_INDEX_COLUMNS)
