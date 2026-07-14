from __future__ import annotations

import pandas as pd

COMPS_COLUMNS = [
    "comp_id",
    "category",
    "subcategory",
    "asset_id",
    "source",
    "source_url",
    "date",
    "price_usd",
    "currency",
    "condition",
    "exactness_score",
    "source_confidence",
    "price_type",
    "source_access",
    "venue",
    "auction_name",
    "lot_id",
    "brand",
    "model",
    "reference",
    "size",
    "material",
    "color",
    "hardware",
    "year",
    "title",
    "auction_url",
    "lot_url",
    "raw_text_path",
    "confidence_score",
    "estimate_low_usd",
    "estimate_high_usd",
    "buyer_premium_included",
    "notes",
]


def normalize_comps(comps: pd.DataFrame) -> pd.DataFrame:
    out = comps.copy()
    for col in COMPS_COLUMNS:
        if col not in out.columns:
            out[col] = None
    out["currency"] = out["currency"].fillna("USD").str.upper()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["price_usd"] = pd.to_numeric(out["price_usd"], errors="coerce")
    out["exactness_score"] = pd.to_numeric(out["exactness_score"], errors="coerce").clip(0, 1)
    out["source_confidence"] = pd.to_numeric(out["source_confidence"], errors="coerce").clip(0, 1)
    out["price_type"] = out["price_type"].fillna("realized_with_premium")
    out["source_access"] = out["source_access"].fillna("public_page")
    out["estimate_low_usd"] = pd.to_numeric(out["estimate_low_usd"], errors="coerce")
    out["estimate_high_usd"] = pd.to_numeric(out["estimate_high_usd"], errors="coerce")
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["confidence_score"] = pd.to_numeric(out["confidence_score"], errors="coerce").clip(0, 1)
    out["confidence_score"] = out["confidence_score"].fillna(out["exactness_score"])
    return out[COMPS_COLUMNS]


def empty_comps_frame(category: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(columns=COMPS_COLUMNS)
    if category:
        df.loc[0, "category"] = category
    return df
