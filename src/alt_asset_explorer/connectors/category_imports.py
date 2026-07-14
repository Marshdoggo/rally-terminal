from __future__ import annotations

from pathlib import Path

import pandas as pd

from alt_asset_explorer.connectors.base import CsvConnector
from alt_asset_explorer.normalization import COMPS_COLUMNS, normalize_comps
from alt_asset_explorer.paths import DATA_RAW
from alt_asset_explorer.schemas import ComparableSale, MarketIndexObservation

IMPORT_DIR = DATA_RAW / "imports"


def _norm_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def handbag_exactness(row: pd.Series) -> float:
    score = 0.35
    for field, weight in (
        ("brand", 0.15),
        ("model", 0.20),
        ("size", 0.10),
        ("material", 0.08),
        ("condition", 0.07),
        ("color", 0.03),
        ("provenance", 0.02),
    ):
        if _norm_text(row.get(field)):
            score += weight
    return _bounded(score)


def watch_exactness(row: pd.Series) -> float:
    score = 0.35
    for field, weight in (
        ("brand", 0.12),
        ("reference", 0.25),
        ("year", 0.08),
        ("configuration", 0.08),
        ("condition", 0.07),
        ("box_papers", 0.03),
        ("venue_quality", 0.02),
    ):
        if _norm_text(row.get(field)):
            score += weight
    return _bounded(score)


def _source_confidence(row: pd.Series) -> float:
    if pd.notna(row.get("source_confidence")):
        return _bounded(float(row["source_confidence"]))
    source_url = _norm_text(row.get("source_url"))
    venue_quality = _norm_text(row.get("venue_quality"))
    source = _norm_text(row.get("source"))
    if source_url and venue_quality in {"high", "auction", "verified"}:
        return 0.85
    if source_url or source:
        return 0.70
    return 0.45


def _first_value(row: pd.Series, *names: str):
    for name in names:
        value = row.get(name)
        if pd.notna(value) and str(value).strip():
            return value
    return None


def _price_value(row: pd.Series) -> float | None:
    return _first_value(row, "realized_price_usd", "price_usd", "sale_price", "list_price_usd", "ask_price_usd", "price")


def _estimate_value(row: pd.Series, *names: str) -> float | None:
    value = _first_value(row, *names)
    return float(value) if value is not None else None


def _int_value(row: pd.Series, *names: str) -> int | None:
    value = _first_value(row, *names)
    if value is None:
        return None
    parsed = pd.to_numeric(value, errors="coerce")
    return int(parsed) if pd.notna(parsed) else None


def _string_value(row: pd.Series, *names: str) -> str | None:
    value = _first_value(row, *names)
    return str(value) if value is not None else None


def _infer_category(row: pd.Series, default: str | None = None) -> str:
    category = _norm_text(row.get("category"))
    if category:
        if "watch" in category:
            return "watches"
        if "handbag" in category or "fashion" in category or "bag" in category:
            return "handbags"
        return category
    text = " ".join(_norm_text(row.get(name)) for name in ("title", "brand", "model", "department", "auction_name"))
    if any(token in text for token in ("rolex", "patek", "audemars", "daytona", "watch", "watches")):
        return "watches"
    if any(token in text for token in ("hermes", "hermès", "birkin", "kelly", "chanel", "handbag", "bag")):
        return "handbags"
    return default or "other"


def _auction_exactness(row: pd.Series, category: str) -> float:
    return watch_exactness(row) if category == "watches" else handbag_exactness(row) if category == "handbags" else 0.50


def normalize_auction_results(raw: pd.DataFrame, *, source_name: str) -> pd.DataFrame:
    rows: list[dict] = []
    for idx, row in raw.iterrows():
        price = _price_value(row)
        date_value = _first_value(row, "date", "sale_date", "auction_date")
        source_url = _first_value(row, "source_url", "lot_url", "url")
        if price is None or date_value is None or source_url is None:
            raise ValueError(f"{source_name} row {idx + 1} requires price, date, and source URL")
        category = _infer_category(row)
        record = {
            "comp_id": _string_value(row, "comp_id") or f"{source_name.lower()}-result-{idx + 1:05d}",
            "category": category,
            "subcategory": _first_value(row, "subcategory", "model", "reference", "title") or "uncategorized",
            "asset_id": row.get("asset_id"),
            "source": source_name,
            "source_url": source_url,
            "date": date_value,
            "price_usd": price,
            "currency": row.get("currency") or "USD",
            "condition": row.get("condition"),
            "exactness_score": row.get("exactness_score") if pd.notna(row.get("exactness_score")) else _auction_exactness(row, category),
            "source_confidence": min(_source_confidence(row), 0.90),
            "price_type": row.get("price_type") or "realized_with_premium",
            "source_access": row.get("source_access") or "user_export",
            "venue": _first_value(row, "venue", "location"),
            "auction_name": row.get("auction_name"),
            "lot_id": _string_value(row, "lot_id", "lot_number"),
            "brand": _string_value(row, "brand"),
            "model": _string_value(row, "model"),
            "reference": _string_value(row, "reference"),
            "size": _string_value(row, "size"),
            "material": _string_value(row, "material"),
            "color": _string_value(row, "color"),
            "hardware": _string_value(row, "hardware"),
            "year": _int_value(row, "year"),
            "title": _string_value(row, "title"),
            "auction_url": _string_value(row, "auction_url"),
            "lot_url": _string_value(row, "lot_url", "source_url", "url"),
            "raw_text_path": _string_value(row, "raw_text_path"),
            "confidence_score": row.get("confidence_score"),
            "estimate_low_usd": _estimate_value(row, "estimate_low_usd", "estimate_low"),
            "estimate_high_usd": _estimate_value(row, "estimate_high_usd", "estimate_high"),
            "buyer_premium_included": row.get("buyer_premium_included"),
            "notes": row.get("notes") or row.get("title"),
        }
        rows.append(ComparableSale(**pd.Series(record).dropna().to_dict()).model_dump())
    if not rows:
        return pd.DataFrame(columns=COMPS_COLUMNS)
    return normalize_comps(pd.DataFrame(rows))


def normalize_fashionphile_listings(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for idx, row in raw.iterrows():
        price = _price_value(row)
        date_value = _first_value(row, "date", "listing_date", "capture_date")
        source_url = _first_value(row, "source_url", "listing_url", "url")
        if price is None or date_value is None or source_url is None:
            raise ValueError(f"Fashionphile row {idx + 1} requires price, date, and source URL")
        sold_flag = _norm_text(row.get("status")) in {"sold", "closed", "sale"}
        record = {
            "comp_id": _string_value(row, "comp_id") or f"fashionphile-listing-{idx + 1:05d}",
            "category": "handbags",
            "subcategory": _first_value(row, "subcategory", "model") or "uncategorized",
            "asset_id": row.get("asset_id"),
            "source": "Fashionphile",
            "source_url": source_url,
            "date": date_value,
            "price_usd": price,
            "currency": row.get("currency") or "USD",
            "condition": row.get("condition"),
            "exactness_score": row.get("exactness_score") if pd.notna(row.get("exactness_score")) else handbag_exactness(row),
            "source_confidence": min(_source_confidence(row), 0.75 if sold_flag else 0.65),
            "price_type": row.get("price_type") or ("realized_with_premium" if sold_flag else "ask"),
            "source_access": row.get("source_access") or "user_export",
            "venue": "Fashionphile",
            "auction_name": None,
            "lot_id": _string_value(row, "listing_id", "lot_id"),
            "brand": _string_value(row, "brand"),
            "model": _string_value(row, "model"),
            "reference": _string_value(row, "reference"),
            "size": _string_value(row, "size"),
            "material": _string_value(row, "material"),
            "color": _string_value(row, "color"),
            "hardware": _string_value(row, "hardware"),
            "year": _int_value(row, "year"),
            "title": _string_value(row, "title"),
            "lot_url": _string_value(row, "listing_url", "source_url", "url"),
            "confidence_score": row.get("confidence_score"),
            "buyer_premium_included": False,
            "notes": row.get("notes") or row.get("title"),
        }
        rows.append(ComparableSale(**pd.Series(record).dropna().to_dict()).model_dump())
    if not rows:
        return pd.DataFrame(columns=COMPS_COLUMNS)
    return normalize_comps(pd.DataFrame(rows))


def normalize_chrono24_market_data(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for _, row in raw.iterrows():
        record = {
            "category": "watches",
            "source": row.get("source") or "Chrono24",
            "source_url": _first_value(row, "source_url", "url"),
            "date": _first_value(row, "date", "index_date"),
            "brand": row.get("brand"),
            "model": row.get("model"),
            "reference": row.get("reference"),
            "metric_name": row.get("metric_name") or row.get("index_name") or "chrono24_market_metric",
            "metric_value": _first_value(row, "metric_value", "index_value", "estimated_value_usd"),
            "currency": row.get("currency") or "USD",
            "source_access": row.get("source_access") or "public_page",
            "source_confidence": row.get("source_confidence") if pd.notna(row.get("source_confidence")) else 0.75,
            "notes": row.get("notes"),
        }
        rows.append(MarketIndexObservation(**pd.Series(record).dropna().to_dict()).model_dump())
    return pd.DataFrame(rows)


def normalize_category_comps(raw: pd.DataFrame, *, category: str, score_fn) -> pd.DataFrame:
    rows: list[dict] = []
    for idx, row in raw.iterrows():
        comp_id = row.get("comp_id")
        if pd.isna(comp_id) or not str(comp_id).strip():
            comp_id = f"{category}-import-{idx + 1:05d}"
        notes_parts = []
        for field in ("brand", "model", "reference", "size", "material", "color", "year", "configuration", "box_papers", "provenance"):
            value = row.get(field)
            if pd.notna(value) and str(value).strip():
                notes_parts.append(f"{field}={value}")
        record = {
            "comp_id": comp_id,
            "category": category,
            "subcategory": row.get("subcategory") or row.get("model") or row.get("reference") or "uncategorized",
            "asset_id": row.get("asset_id"),
            "source": row.get("source") or "user_import",
            "source_url": row.get("source_url"),
            "date": row.get("date") or row.get("sale_date"),
            "price_usd": row.get("price_usd") or row.get("price") or row.get("sale_price"),
            "currency": row.get("currency") or "USD",
            "condition": row.get("condition"),
            "exactness_score": row.get("exactness_score") if pd.notna(row.get("exactness_score")) else score_fn(row),
            "source_confidence": _source_confidence(row),
            "price_type": row.get("price_type") or "realized_with_premium",
            "source_access": row.get("source_access") or "user_export",
            "venue": row.get("venue"),
            "auction_name": row.get("auction_name"),
            "lot_id": row.get("lot_id"),
            "brand": _string_value(row, "brand"),
            "model": _string_value(row, "model"),
            "reference": _string_value(row, "reference"),
            "size": _string_value(row, "size"),
            "material": _string_value(row, "material"),
            "color": _string_value(row, "color"),
            "hardware": _string_value(row, "hardware"),
            "year": _int_value(row, "year"),
            "title": _string_value(row, "title"),
            "auction_url": _string_value(row, "auction_url"),
            "lot_url": _string_value(row, "lot_url", "source_url", "url"),
            "raw_text_path": _string_value(row, "raw_text_path"),
            "confidence_score": row.get("confidence_score"),
            "estimate_low_usd": row.get("estimate_low_usd"),
            "estimate_high_usd": row.get("estimate_high_usd"),
            "buyer_premium_included": row.get("buyer_premium_included"),
            "notes": row.get("notes") or "; ".join(notes_parts) or None,
        }
        rows.append(ComparableSale(**pd.Series(record).dropna().to_dict()).model_dump())
    if not rows:
        return pd.DataFrame(columns=COMPS_COLUMNS)
    return normalize_comps(pd.DataFrame(rows))


def load_handbag_imports(path: Path | None = None) -> pd.DataFrame:
    connector = CsvConnector(
        name="handbags_user_import",
        path=path or IMPORT_DIR / "handbags_comps.csv",
        normalize=lambda raw: normalize_category_comps(raw, category="handbags", score_fn=handbag_exactness),
    )
    return connector.load_normalized()


def load_watch_imports(path: Path | None = None) -> pd.DataFrame:
    connector = CsvConnector(
        name="watches_user_import",
        path=path or IMPORT_DIR / "watches_comps.csv",
        normalize=lambda raw: normalize_category_comps(raw, category="watches", score_fn=watch_exactness),
    )
    return connector.load_normalized()


def load_sothebys_results(path: Path | None = None) -> pd.DataFrame:
    return CsvConnector("sothebys_results", path or IMPORT_DIR / "sothebys_results.csv", lambda raw: normalize_auction_results(raw, source_name="Sothebys")).load_normalized()


def load_christies_results(path: Path | None = None) -> pd.DataFrame:
    return CsvConnector("christies_results", path or IMPORT_DIR / "christies_results.csv", lambda raw: normalize_auction_results(raw, source_name="Christies")).load_normalized()


def load_phillips_results(path: Path | None = None) -> pd.DataFrame:
    return CsvConnector("phillips_results", path or IMPORT_DIR / "phillips_results.csv", lambda raw: normalize_auction_results(raw, source_name="Phillips")).load_normalized()


def load_fashionphile_listings(path: Path | None = None) -> pd.DataFrame:
    return CsvConnector("fashionphile_listings", path or IMPORT_DIR / "fashionphile_listings.csv", normalize_fashionphile_listings).load_normalized()


def load_chrono24_market_data(path: Path | None = None) -> pd.DataFrame:
    return CsvConnector("chrono24_market_data", path or IMPORT_DIR / "chrono24_market_data.csv", normalize_chrono24_market_data).load_normalized()


def load_all_category_imports() -> pd.DataFrame:
    frames = [
        load_handbag_imports(),
        load_watch_imports(),
        load_sothebys_results(),
        load_christies_results(),
        load_phillips_results(),
        load_fashionphile_listings(),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=COMPS_COLUMNS)
    return pd.concat(frames, ignore_index=True)
