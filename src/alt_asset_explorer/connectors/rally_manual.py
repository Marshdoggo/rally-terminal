from __future__ import annotations

from pathlib import Path

import pandas as pd

from alt_asset_explorer.paths import DATA_RAW
from alt_asset_explorer.paths import DATA_NORMALIZED
from alt_asset_explorer.manual_imports import PRICE_EVENT_TYPES
from alt_asset_explorer.schemas import Asset, ComparableSale, PriceObservation, RallySnapshot


def _none_if_na(value):
    return None if pd.isna(value) else value


def _validated_frame(path: Path, model: type) -> pd.DataFrame:
    df = pd.read_csv(path)
    records = [model(**row.dropna().to_dict()).model_dump() for _, row in df.iterrows()]
    return pd.DataFrame(records)


def load_assets(path: Path | None = None) -> pd.DataFrame:
    seed = _validated_frame(path or DATA_RAW / "rally_assets_seed.csv", Asset)
    imports = load_rally_asset_imports()
    manual = load_normalized_manual_assets()
    frames = [seed]
    if not imports.empty:
        frames.append(imports)
    if not manual.empty:
        frames.append(manual)
    if len(frames) == 1:
        return seed
    if path is None:
        combined = pd.concat(frames, ignore_index=True)
        return combined.drop_duplicates(subset=["asset_id"], keep="last")
    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["asset_id"], keep="last")


def load_rally_asset_imports(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_RAW / "imports" / "rally_assets.csv"
    if not path.exists():
        return pd.DataFrame(columns=Asset.model_fields.keys())
    return _validated_frame(path, Asset)


def load_normalized_manual_assets(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_NORMALIZED / "assets.csv"
    if not path.exists():
        return pd.DataFrame(columns=Asset.model_fields.keys())
    raw = pd.read_csv(path)
    rows: list[dict] = []
    for _, row in raw.iterrows():
        shares = pd.to_numeric(row.get("shares_outstanding"), errors="coerce")
        offering_price = pd.to_numeric(row.get("offering_price_per_share"), errors="coerce")
        offering_cap = pd.to_numeric(row.get("offering_market_cap"), errors="coerce")
        rows.append(
            {
                "asset_id": row.get("asset_id"),
                "ticker": row.get("ticker"),
                "name": row.get("asset_name"),
                "category": row.get("category"),
                "subcategory": row.get("subcategory") or "uncategorized",
                "issuer_cik": None,
                "series_name": None,
                "offering_date": row.get("offering_date") or row.get("first_trade_date"),
                "offering_price": float(offering_price) if pd.notna(offering_price) else None,
                "shares": int(shares) if pd.notna(shares) else None,
                "market_cap_usd": None,
                "last_price_usd": None,
                "source_url": row.get("rally_url") or row.get("source_reference"),
                "source_confidence": 1.0,
                "rarity_score": 0.5,
                "status": row.get("status") or "unknown",
                "notes": row.get("notes") or row.get("source_reference"),
                "exit_date": row.get("exit_date"),
                "exit_price_per_share": row.get("exit_price_per_share"),
                "exit_value_total": row.get("exit_value_total"),
                "exit_type": row.get("exit_type"),
            }
        )
    return pd.DataFrame(rows)


def load_comps(path: Path | None = None) -> pd.DataFrame:
    return _validated_frame(path or DATA_RAW / "comps_seed.csv", ComparableSale)


def load_price_history(path: Path | None = None) -> pd.DataFrame:
    seed = _validated_frame(path or DATA_RAW / "price_history_seed.csv", PriceObservation)
    snapshots = load_rally_snapshot_imports()
    manual = load_normalized_price_observations()
    frames = [seed]
    if not snapshots.empty:
        frames.append(snapshots)
    if not manual.empty:
        frames.append(manual)
    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["date", "asset_id", "source"], keep="last")


def load_rally_snapshot_imports(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_RAW / "imports" / "rally_snapshots.csv"
    if not path.exists():
        return pd.DataFrame(columns=PriceObservation.model_fields.keys())
    snapshots = _validated_frame(path, RallySnapshot)
    rows: list[dict] = []
    for _, row in snapshots.iterrows():
        rows.append(
            PriceObservation(
                date=row["date"],
                asset_id=row["asset_id"],
                bid=_none_if_na(row.get("bid")),
                ask=_none_if_na(row.get("ask")),
                last=row["price"],
                volume=row.get("volume", 0),
                market_cap_usd=_none_if_na(row.get("market_cap_usd")),
                source=row["source"],
            ).model_dump()
        )
    return pd.DataFrame(rows)


def load_normalized_price_observations(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_NORMALIZED / "price_observations.csv"
    if not path.exists():
        return pd.DataFrame(columns=PriceObservation.model_fields.keys())
    raw = pd.read_csv(path)
    if raw.empty:
        return pd.DataFrame(columns=PriceObservation.model_fields.keys())
    raw = raw[raw["event_type"].astype(str).isin(PRICE_EVENT_TYPES)].copy()
    raw = raw[raw["price_per_share"].notna()]
    rows: list[dict] = []
    for _, row in raw.iterrows():
        observed = pd.to_datetime(row.get("observed_at"), errors="coerce")
        price = pd.to_numeric(row.get("price_per_share"), errors="coerce")
        market_cap = pd.to_numeric(row.get("market_cap"), errors="coerce")
        volume = pd.to_numeric(row.get("volume"), errors="coerce")
        if pd.isna(observed) or pd.isna(price) or price <= 0:
            continue
        rows.append(
            {
                "date": observed.date(),
                "asset_id": row.get("asset_id"),
                "bid": None,
                "ask": None,
                "last": float(price),
                "volume": float(volume) if pd.notna(volume) else 0,
                "market_cap_usd": float(market_cap) if pd.notna(market_cap) else None,
                "source": f"manual:{row.get('event_type')}:{row.get('precision_status')}:{row.get('source_type')}",
                "event_type": row.get("event_type"),
                "precision_status": row.get("precision_status"),
                "source_reference": row.get("source_reference"),
                "observed_at": row.get("observed_at"),
                "period_end": row.get("period_end"),
                "frequency": row.get("frequency"),
            }
        )
    return pd.DataFrame(rows)


def load_quarterly_index_observations(path: Path | None = None) -> pd.DataFrame:
    """Load manual quarterly observations for index prototypes.

    Offering prices are retained here only as inception/base observations for
    quarterly prototypes. They remain excluded from ordinary secondary-market
    price history via `load_normalized_price_observations`.
    """
    path = path or DATA_NORMALIZED / "price_observations.csv"
    if not path.exists():
        return pd.DataFrame(columns=PriceObservation.model_fields.keys())
    raw = pd.read_csv(path)
    if raw.empty:
        return pd.DataFrame(columns=PriceObservation.model_fields.keys())
    allowed_events = PRICE_EVENT_TYPES | {"offering_price"}
    raw = raw[raw["event_type"].astype(str).isin(allowed_events)].copy()
    raw = raw[raw["price_per_share"].notna()]
    rows: list[dict] = []
    for _, row in raw.iterrows():
        observed = pd.to_datetime(row.get("observed_at"), errors="coerce")
        period_end = pd.to_datetime(row.get("period_end"), errors="coerce")
        price = pd.to_numeric(row.get("price_per_share"), errors="coerce")
        market_cap = pd.to_numeric(row.get("market_cap"), errors="coerce")
        volume = pd.to_numeric(row.get("volume"), errors="coerce")
        if pd.isna(observed) or pd.isna(period_end) or pd.isna(price) or price <= 0:
            continue
        rows.append(
            {
                "date": observed.date(),
                "asset_id": row.get("asset_id"),
                "bid": None,
                "ask": None,
                "last": float(price),
                "volume": float(volume) if pd.notna(volume) else 0,
                "market_cap_usd": float(market_cap) if pd.notna(market_cap) else None,
                "source": f"manual:{row.get('event_type')}:{row.get('precision_status')}:{row.get('source_type')}",
                "event_type": row.get("event_type"),
                "precision_status": row.get("precision_status"),
                "source_reference": row.get("source_reference"),
                "observed_at": row.get("observed_at"),
                "period_end": row.get("period_end"),
                "frequency": row.get("frequency"),
            }
        )
    return pd.DataFrame(rows)
