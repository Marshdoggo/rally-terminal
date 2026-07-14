from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd


BIRKIN_COLUMNS = [
    "record_type",
    "source",
    "asset_id",
    "ticker",
    "name",
    "series_name",
    "lot_id",
    "auction_name",
    "source_url",
    "date",
    "market_cap_usd",
    "offering_price",
    "shares",
    "price_usd",
    "estimate_low_usd",
    "estimate_high_usd",
    "brand",
    "model",
    "size",
    "material",
    "color",
    "year",
    "is_exotic",
    "exactness_score",
    "source_confidence",
    "comparison_role",
]

MATERIAL_PATTERNS = (
    "Niloticus Crocodile",
    "Porosus Crocodile",
    "Mississippiensis Alligator",
    "Alligator",
    "Crocodile",
    "Ostrich",
    "Lizard",
    "Togo",
    "Epsom",
    "Clemence",
    "Chevre",
    "Swift",
    "Box",
    "Evercalf",
    "Evercolor",
    "Tadelakt",
    "Madame",
)

EXOTIC_TOKENS = ("crocodile", "alligator", "ostrich", "lizard")


def _ascii(value: object) -> str:
    if pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", _ascii(value)).strip()


def _contains_birkin(value: object) -> bool:
    return bool(re.search(r"birkin", _ascii(value), re.I))


def _find_material(text: str) -> str:
    lowered = _ascii(text).lower()
    for material in MATERIAL_PATTERNS:
        if _ascii(material).lower() in lowered:
            return material
    return ""


def _find_size(text: str) -> str:
    match = re.search(r"\bBirkin\s+(?P<size>\d{2,3})\b", _ascii(text), re.I)
    return match.group("size") if match else ""


def _find_year(text: str) -> str:
    years = re.findall(r"\b(19\d{2}|20\d{2})\b", _ascii(text))
    return years[-1] if years else ""


def _find_color(text: str, material: str) -> str:
    clean = _norm(text)
    match = re.search(r"\bBirkin\b", _ascii(clean), re.I)
    if not match:
        return ""
    before_model = clean[: match.start()].strip(" ,")
    before_model = re.sub(r"^(Limited Edition|Vintage|Rare)\s+", "", before_model, flags=re.I).strip()
    before_model = re.sub(r"\b(19\d{2}|20\d{2})\b", "", before_model).strip(" ,")
    before_model = re.sub(r"\bHermes\b", "", before_model, flags=re.I).strip(" ,")
    if material:
        before_model = re.sub(re.escape(material), "", before_model, flags=re.I).strip(" ,")
    return before_model[:80]


def parse_birkin_features(text: object) -> dict[str, object]:
    clean = _norm(text)
    material = _find_material(clean)
    return {
        "brand": "Hermes" if re.search(r"hermes|birkin", _ascii(clean), re.I) else "",
        "model": "Birkin" if _contains_birkin(clean) else "",
        "size": _find_size(clean),
        "material": material,
        "color": _find_color(clean, material),
        "year": _find_year(clean),
        "is_exotic": any(token in _ascii(clean).lower() for token in EXOTIC_TOKENS),
    }


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=BIRKIN_COLUMNS)


def _row_with_columns(row: dict) -> dict:
    return {column: row.get(column) for column in BIRKIN_COLUMNS}


def build_birkin_comparison(assets: pd.DataFrame, comps: pd.DataFrame, sec_series: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    if not assets.empty:
        for _, asset in assets.iterrows():
            text = " ".join(str(asset.get(field) or "") for field in ("name", "series_name", "subcategory"))
            if not _contains_birkin(text):
                continue
            features = parse_birkin_features(text)
            rows.append(
                _row_with_columns(
                    {
                        "record_type": "rally_asset",
                        "source": "Rally seed",
                        "asset_id": asset.get("asset_id"),
                        "ticker": asset.get("ticker"),
                        "name": asset.get("name"),
                        "series_name": asset.get("series_name"),
                        "source_url": asset.get("source_url"),
                        "date": asset.get("offering_date"),
                        "market_cap_usd": asset.get("market_cap_usd"),
                        "offering_price": asset.get("offering_price"),
                        "shares": asset.get("shares"),
                        "source_confidence": asset.get("source_confidence"),
                        "comparison_role": "rally_market_reference",
                        **features,
                    }
                )
            )

    if not sec_series.empty:
        for _, series in sec_series.iterrows():
            text = " ".join(str(series.get(field) or "") for field in ("series_name", "asset_name"))
            if not _contains_birkin(text):
                continue
            features = parse_birkin_features(text)
            rows.append(
                _row_with_columns(
                    {
                        "record_type": "rally_sec_series",
                        "source": "SEC EDGAR",
                        "asset_id": str(series.get("series_id") or "").lower().replace(" ", "-"),
                        "name": series.get("asset_name"),
                        "series_name": series.get("series_name"),
                        "source_url": series.get("filing_url"),
                        "date": series.get("filing_date"),
                        "offering_price": series.get("offering_price"),
                        "shares": series.get("shares"),
                        "source_confidence": series.get("source_confidence"),
                        "comparison_role": "rally_fundamental_context",
                        **features,
                    }
                )
            )

    if not comps.empty:
        for _, comp in comps.iterrows():
            title = comp.get("notes") or comp.get("subcategory") or ""
            if str(comp.get("source")) != "Sothebys" or not _contains_birkin(title):
                continue
            features = parse_birkin_features(title)
            rows.append(
                _row_with_columns(
                    {
                        "record_type": "sothebys_comp",
                        "source": "Sothebys",
                        "asset_id": comp.get("asset_id"),
                        "name": title,
                        "lot_id": comp.get("lot_id"),
                        "auction_name": comp.get("auction_name"),
                        "source_url": comp.get("source_url"),
                        "date": comp.get("date"),
                        "price_usd": comp.get("price_usd"),
                        "estimate_low_usd": comp.get("estimate_low_usd"),
                        "estimate_high_usd": comp.get("estimate_high_usd"),
                        "exactness_score": comp.get("exactness_score"),
                        "source_confidence": comp.get("source_confidence"),
                        "comparison_role": "secondary_realized_comp",
                        **features,
                    }
                )
            )

    if not rows:
        return _empty()

    out = pd.DataFrame(rows)
    for column in BIRKIN_COLUMNS:
        if column not in out:
            out[column] = None
    for column in ("market_cap_usd", "offering_price", "shares", "price_usd", "estimate_low_usd", "estimate_high_usd", "exactness_score", "source_confidence"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    return out[BIRKIN_COLUMNS]


def birkin_market_summary(birkin_rows: pd.DataFrame, *, as_of: date | None = None) -> pd.DataFrame:
    as_of = as_of or date.today()
    comps = birkin_rows[birkin_rows["record_type"] == "sothebys_comp"].copy()
    if comps.empty:
        return pd.DataFrame(
            [
                {
                    "comp_count": 0,
                    "secondary_nav_usd": None,
                    "nav_low_usd": None,
                    "nav_high_usd": None,
                    "nav_confidence": 0.0,
                    "newest_comp_date": None,
                }
            ]
        )

    comps["date"] = pd.to_datetime(comps["date"], errors="coerce").dt.date
    comps = comps.dropna(subset=["price_usd"])
    if comps.empty:
        return pd.DataFrame()

    weights = []
    for _, comp in comps.iterrows():
        comp_date = comp.get("date")
        age_days = max((as_of - comp_date).days, 0) if isinstance(comp_date, date) else 365
        recency = max(0.20, 1 / (1 + age_days / 365))
        exactness = float(comp.get("exactness_score") or 0.5)
        confidence = float(comp.get("source_confidence") or 0.7)
        size_bonus = 1.15 if str(comp.get("size") or "") == "35" else 1.0
        weights.append(recency * exactness * confidence * size_bonus)
    comps["weight"] = weights
    secondary_nav = float((comps["price_usd"] * comps["weight"]).sum() / comps["weight"].sum())
    dispersion = float(comps["price_usd"].std(ddof=0) / secondary_nav) if len(comps) > 1 and secondary_nav else 0.25
    nav_confidence = min(0.90, max(0.05, float(comps["weight"].mean()) * min(1.0, len(comps) / 5)))
    return pd.DataFrame(
        [
            {
                "comp_count": len(comps),
                "secondary_nav_usd": secondary_nav,
                "nav_low_usd": secondary_nav * (1 - max(0.10, min(dispersion, 0.60))),
                "nav_high_usd": secondary_nav * (1 + max(0.10, min(dispersion, 0.60))),
                "nav_confidence": nav_confidence,
                "newest_comp_date": max(comps["date"]).isoformat(),
            }
        ]
    )
