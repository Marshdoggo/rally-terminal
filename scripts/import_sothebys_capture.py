from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DIAGNOSTICS_DIR = Path("data/diagnostics")
IMPORT_ERRORS_PATH = DIAGNOSTICS_DIR / "import_errors.csv"

KNOWN_BRANDS = (
    "Hermes",
    "Chanel",
    "Louis Vuitton",
    "Goyard",
    "Gucci",
    "Dior",
    "Fendi",
    "Prada",
    "Rolex",
    "Patek Philippe",
    "Audemars Piguet",
    "Cartier",
    "Omega",
)

MODEL_PATTERNS = (
    "Birkin",
    "Kelly",
    "Constance",
    "Lindy",
    "HAC",
    "Haut a Courroies",
    "Daytona",
    "Nautilus",
    "Royal Oak",
    "Submariner",
)

MATERIAL_PATTERNS = (
    "Togo",
    "Epsom",
    "Clemence",
    "Box",
    "Swift",
    "Evercolor",
    "Tadelakt",
    "Ostrich",
    "Lizard",
    "Alligator",
    "Porosus Crocodile",
    "Niloticus Crocodile",
    "Crocodile",
    "Canvas",
    "Leather",
)

HARDWARE_PATTERNS = (
    "Gold Hardware",
    "Palladium Hardware",
    "Permabrass Hardware",
    "Brushed Gold Hardware",
    "Electrum Hardware",
    "Black PVD Hardware",
    "Silver Hardware",
    "Brass Hardware",
    "Dark Silver Hardware",
)

LOT_RE = re.compile(r"^(?P<lot>\d+[A-Z]?)\.\s+(?P<label>.+?)\s*$")
ESTIMATE_RE = re.compile(r"Estimate:\s*(?P<low>[\d,]+)\s*-\s*(?P<high>[\d,]+)\s*(?P<currency>[A-Z]{3})", re.I)
SOLD_RE = re.compile(r"LOT SOLD:\s*(?P<price>[\d,]+)\s*(?P<currency>[A-Z]{3})", re.I)
URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class ParsedLot:
    lot_id: str
    title: str
    brand: str
    model: str
    size: str
    material: str
    color: str
    hardware: str
    year: int | None
    confidence_score: float
    estimate_low_usd: float | None
    estimate_high_usd: float | None
    realized_price_usd: float
    currency: str
    source_url: str


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _clean_line(value: str) -> str:
    value = value.replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", value)


def _money(value: str) -> float:
    return float(value.replace(",", ""))


def _slug(value: str) -> str:
    value = _ascii_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "auction"


def _canonical_brand(value: str) -> str:
    text = _ascii_text(value).lower()
    for brand in KNOWN_BRANDS:
        if _ascii_text(brand).lower() in text:
            return brand
    return ""


def _find_pattern(title: str, patterns: tuple[str, ...]) -> str:
    text = _ascii_text(title).lower()
    for pattern in patterns:
        if _ascii_text(pattern).lower() in text:
            return pattern
    return ""


def _infer_size(title: str, model: str) -> str:
    if not model:
        return ""
    text = _ascii_text(title)
    match = re.search(rf"\b{re.escape(_ascii_text(model))}\s+(?P<size>\d{{2,3}})\b", text, re.I)
    return match.group("size") if match else ""


def _infer_color(title: str, material: str, model: str) -> str:
    text = _ascii_text(title)
    stops = [part for part in (material, model) if part]
    first_stop = len(text)
    for stop in stops:
        match = re.search(rf"\b{re.escape(_ascii_text(stop))}\b", text, re.I)
        if match:
            first_stop = min(first_stop, match.start())
    candidate = text[:first_stop].strip(" ,")
    candidate = re.sub(r"^(Limited Edition|Vintage|Rare)\s+", "", candidate, flags=re.I).strip()
    return candidate[:80]


def _infer_year(title: str) -> int | None:
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", _ascii_text(title))
    return int(matches[-1]) if matches else None


def _confidence(*, brand: str, model: str, size: str, material: str, color: str, hardware: str, year: int | None, estimate: re.Match | None) -> float:
    score = 0.45
    score += 0.12 if brand else 0
    score += 0.14 if model else 0
    score += 0.08 if size else 0
    score += 0.08 if material else 0
    score += 0.04 if color else 0
    score += 0.04 if hardware else 0
    score += 0.03 if year else 0
    score += 0.02 if estimate else 0
    return round(min(score, 0.98), 3)


def _joined_window(lines: list[str], start: int, end: int) -> str:
    return " ".join(lines[start:end])


def parse_sothebys_capture(
    text: str,
    *,
    auction_url: str,
    default_currency: str = "USD",
    brand_filter: str | None = None,
) -> list[ParsedLot]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    lot_starts = [(idx, match) for idx, line in enumerate(lines) if (match := LOT_RE.match(line))]
    lots: list[ParsedLot] = []

    for pos, (idx, match) in enumerate(lot_starts):
        next_idx = lot_starts[pos + 1][0] if pos + 1 < len(lot_starts) else len(lines)
        block = lines[idx:next_idx]
        joined = _joined_window(lines, idx, next_idx)
        sold = SOLD_RE.search(joined)
        if not sold:
            continue

        estimate = ESTIMATE_RE.search(joined)
        label = match.group("label")
        brand = _canonical_brand(label)
        if brand_filter and _ascii_text(brand).lower() != _ascii_text(brand_filter).lower():
            continue
        title = ""
        if brand and len(block) > 1:
            title = block[1]
        else:
            title = label
        title = title.replace("...", "").strip()
        if not title or title.lower().startswith(("estimate:", "lot sold:")):
            title = label

        model = _find_pattern(title, MODEL_PATTERNS)
        material = _find_pattern(title, MATERIAL_PATTERNS)
        hardware = _find_pattern(title, HARDWARE_PATTERNS)
        year = _infer_year(title)
        size = _infer_size(title, model)
        color = _infer_color(title, material, model)
        source_url_match = URL_RE.search(joined)
        source_url = source_url_match.group(0).rstrip(")]") if source_url_match else auction_url
        currency = sold.group("currency") or (estimate.group("currency") if estimate else default_currency)

        lots.append(
            ParsedLot(
                lot_id=match.group("lot"),
                title=title,
                brand=brand,
                model=model,
                size=size,
                material=material,
                color=color,
                hardware=hardware,
                year=year,
                confidence_score=_confidence(brand=brand, model=model, size=size, material=material, color=color, hardware=hardware, year=year, estimate=estimate),
                estimate_low_usd=_money(estimate.group("low")) if estimate else None,
                estimate_high_usd=_money(estimate.group("high")) if estimate else None,
                realized_price_usd=_money(sold.group("price")),
                currency=currency,
                source_url=source_url,
            )
        )
    return lots


def capture_stats(text: str, *, brand_filter: str | None = None) -> dict[str, int]:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    lot_starts = [(idx, match) for idx, line in enumerate(lines) if (match := LOT_RE.match(line))]
    total = len(lot_starts)
    brand_matches = 0
    sold_blocks = 0
    brand_sold_blocks = 0
    for pos, (idx, match) in enumerate(lot_starts):
        next_idx = lot_starts[pos + 1][0] if pos + 1 < len(lot_starts) else len(lines)
        joined = _joined_window(lines, idx, next_idx)
        brand = _canonical_brand(match.group("label"))
        brand_ok = not brand_filter or _ascii_text(brand).lower() == _ascii_text(brand_filter).lower()
        has_sold = SOLD_RE.search(joined) is not None
        if brand_ok:
            brand_matches += 1
        if has_sold:
            sold_blocks += 1
        if brand_ok and has_sold:
            brand_sold_blocks += 1
    return {
        "lot_headers": total,
        "brand_matching_lots": brand_matches,
        "sold_price_lots": sold_blocks,
        "brand_matching_sold_price_lots": brand_sold_blocks,
    }


def lots_to_frame(
    lots: list[ParsedLot],
    *,
    auction_name: str,
    auction_url: str,
    sale_date: str,
    venue: str,
    category: str,
    raw_text_path: Path | None = None,
) -> pd.DataFrame:
    auction_slug = _slug(auction_name)
    rows = []
    for lot in lots:
        rows.append(
            {
                "comp_id": f"sothebys-{auction_slug}-{lot.lot_id.lower()}",
                "asset_id": "",
                "category": category,
                "title": lot.title,
                "brand": lot.brand,
                "model": lot.model,
                "reference": "",
                "size": lot.size,
                "material": lot.material,
                "color": lot.color,
                "hardware": lot.hardware,
                "year": lot.year,
                "condition": "",
                "auction_name": auction_name,
                "auction_url": auction_url,
                "lot_id": lot.lot_id,
                "venue": venue,
                "source_url": lot.source_url or auction_url,
                "lot_url": lot.source_url or auction_url,
                "raw_text_path": str(raw_text_path) if raw_text_path else "",
                "sale_date": sale_date,
                "realized_price_usd": lot.realized_price_usd,
                "currency": lot.currency,
                "confidence_score": lot.confidence_score,
                "estimate_low_usd": lot.estimate_low_usd,
                "estimate_high_usd": lot.estimate_high_usd,
                "buyer_premium_included": True,
                "price_type": "realized_with_premium",
                "source_access": "user_export",
                "notes": lot.title,
            }
        )
    return pd.DataFrame(rows)


def write_import_error(*, capture: Path, auction_name: str, row_identifier: str, message: str, raw_value: str = "") -> None:
    IMPORT_ERRORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "source": "Sothebys",
        "capture_path": str(capture),
        "auction_name": auction_name,
        "row_identifier": row_identifier,
        "error": message,
        "raw_value": raw_value,
    }
    frame = pd.DataFrame([row])
    if IMPORT_ERRORS_PATH.exists():
        frame = pd.concat([pd.read_csv(IMPORT_ERRORS_PATH), frame], ignore_index=True)
    frame.to_csv(IMPORT_ERRORS_PATH, index=False)


def validate_sale_date(value: str) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def write_import_csv(frame: pd.DataFrame, output: Path, *, append: bool = False) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if append and output.exists():
        existing = pd.read_csv(output)
        frame = pd.concat([existing, frame], ignore_index=True)
        frame = frame.drop_duplicates(subset=["comp_id"], keep="last")
    frame.to_csv(output, index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert copied Sotheby's auction result page text into sothebys_results.csv.")
    parser.add_argument("capture", type=Path, help="Plain text copied/saved from a Sotheby's auction results page.")
    parser.add_argument("--auction-name", required=True)
    parser.add_argument("--auction-url", required=True)
    parser.add_argument("--sale-date", required=True, help="YYYY-MM-DD date to assign to realized lot results.")
    parser.add_argument("--venue", required=True, help="Auction venue/location, e.g. New York.")
    parser.add_argument("--category", default="handbags", choices=["handbags", "watches", "other"])
    parser.add_argument("--brand-filter", default="", help="Optional canonical brand to keep, e.g. Hermes.")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--output", type=Path, default=Path("data/raw/imports/sothebys_results.csv"))
    parser.add_argument("--append", action="store_true", help="Append to the output CSV and de-duplicate by comp_id.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    sale_date = validate_sale_date(args.sale_date)
    if sale_date is None:
        write_import_error(
            capture=args.capture,
            auction_name=args.auction_name,
            row_identifier="sale_date",
            message="invalid sale date",
            raw_value=args.sale_date,
        )
        print("Sotheby's capture summary:")
        print(f"- invalid sale date logged: {args.sale_date}")
        print(f"- diagnostics: {IMPORT_ERRORS_PATH}")
        return
    text = args.capture.read_text(encoding="utf-8")
    brand_filter = args.brand_filter.strip() or None
    lots = parse_sothebys_capture(
        text,
        auction_url=args.auction_url,
        default_currency=args.currency,
        brand_filter=brand_filter,
    )
    frame = lots_to_frame(
        lots,
        auction_name=args.auction_name,
        auction_url=args.auction_url,
        sale_date=sale_date,
        venue=args.venue,
        category=args.category,
        raw_text_path=args.capture,
    )
    write_import_csv(frame, args.output, append=args.append)
    stats = capture_stats(text, brand_filter=brand_filter)
    print("Sotheby's capture summary:")
    print(f"- lot headers found: {stats['lot_headers']}")
    if brand_filter:
        print(f"- lots matching brand '{brand_filter}': {stats['brand_matching_lots']}")
        print(f"- matching lots with LOT SOLD prices: {stats['brand_matching_sold_price_lots']}")
    else:
        print(f"- lots with LOT SOLD prices: {stats['sold_price_lots']}")
    print(f"- rows written: {len(frame)}")
    print(f"- output: {args.output}")


if __name__ == "__main__":
    main()
