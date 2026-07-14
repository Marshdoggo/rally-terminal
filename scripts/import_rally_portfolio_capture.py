from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


TICKER_RE = re.compile(r"^#(?P<ticker>[A-Z0-9]+)$")
PRICE_RE = re.compile(r"^\$(?P<value>[\d,.]+)(?P<suffix>[KMB]?)$")


def _money(value: str) -> float:
    match = PRICE_RE.match(value.strip())
    if not match:
        raise ValueError(f"Cannot parse money value: {value}")
    amount = float(match.group("value").replace(",", ""))
    suffix = match.group("suffix")
    if suffix == "K":
        amount *= 1_000
    elif suffix == "M":
        amount *= 1_000_000
    elif suffix == "B":
        amount *= 1_000_000_000
    return amount


def _subcategory(name: str) -> str:
    text = name.lower()
    if "birkin" in text:
        return "hermes_birkin"
    if "kelly" in text:
        return "hermes_kelly"
    if "constance" in text:
        return "hermes_constance"
    return "handbag"


def _asset_id(ticker: str) -> str:
    return f"rally-{ticker.lower()}"


def parse_portfolio_text(text: str, *, capture_date: str, source_url: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[dict] = []
    snapshots: list[dict] = []
    i = 0
    while i < len(lines):
        ticker_match = TICKER_RE.match(lines[i])
        if not ticker_match:
            i += 1
            continue
        ticker = ticker_match.group("ticker")
        if i + 4 >= len(lines):
            i += 1
            continue
        name = lines[i + 1]
        price_token = lines[i + 2]
        market_cap_token = lines[i + 3]
        if "Market Cap" not in lines[i + 4] or not PRICE_RE.match(price_token) or not PRICE_RE.match(market_cap_token):
            i += 1
            continue
        price = _money(price_token)
        market_cap = _money(market_cap_token)
        share_count = max(1, round(market_cap / price)) if price else 1
        asset_id = _asset_id(ticker)
        rows.append(
            {
                "asset_id": asset_id,
                "ticker": ticker,
                "name": name,
                "category": "handbags" if "hermes" in name.lower() or "birkin" in name.lower() else "other",
                "subcategory": _subcategory(name),
                "issuer_cik": "",
                "series_name": f"Series #{ticker}",
                "offering_date": capture_date,
                "offering_price": price,
                "shares": share_count,
                "market_cap_usd": market_cap,
                "last_price_usd": price,
                "source_url": source_url,
                "source_confidence": 0.75,
                "rarity_score": 0.70,
                "status": "active",
                "notes": "Imported from visible Rally portfolio capture; offering fields are placeholders until reconciled to SEC filings.",
            }
        )
        snapshots.append(
            {
                "date": capture_date,
                "asset_id": asset_id,
                "ticker": ticker,
                "price": price,
                "bid": "",
                "ask": "",
                "volume": 0,
                "market_cap_usd": market_cap,
                "source": "rally_portfolio_capture",
                "source_confidence": 0.75,
            }
        )
        i += 5
    return pd.DataFrame(rows), pd.DataFrame(snapshots)


def write_csv(frame: pd.DataFrame, output: Path, *, append: bool, key: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if append and output.exists():
        frame = pd.concat([pd.read_csv(output), frame], ignore_index=True)
        frame = frame.drop_duplicates(subset=[key], keep="last")
    frame.to_csv(output, index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert copied Rally portfolio page text into Rally asset and snapshot imports.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--capture-date", required=True)
    parser.add_argument("--source-url", default="https://app.rallyrd.com/app/investments")
    parser.add_argument("--asset-output", type=Path, default=Path("data/raw/imports/rally_assets.csv"))
    parser.add_argument("--snapshot-output", type=Path, default=Path("data/raw/imports/rally_snapshots.csv"))
    parser.add_argument("--append", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    assets, snapshots = parse_portfolio_text(args.capture.read_text(encoding="utf-8"), capture_date=args.capture_date, source_url=args.source_url)
    write_csv(assets, args.asset_output, append=args.append, key="asset_id")
    write_csv(snapshots, args.snapshot_output, append=args.append, key="asset_id")
    print("Rally portfolio capture summary:")
    print(f"- asset rows written: {len(assets)}")
    print(f"- snapshot rows written: {len(snapshots)}")
    print(f"- asset output: {args.asset_output}")
    print(f"- snapshot output: {args.snapshot_output}")


if __name__ == "__main__":
    main()
