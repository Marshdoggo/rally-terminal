from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.paths import DATA_PROCESSED, REPORTS


def _render_template(context: dict) -> str:
    assets = sorted(context.get("assets", []), key=lambda row: row.get("investment_score") or 0, reverse=True)
    discounts = sorted(
        [row for row in assets if row.get("premium_discount_pct") is not None],
        key=lambda row: row["premium_discount_pct"],
    )
    lines = [
        f"# Collectibles Research Report - {context['as_of']}",
        "",
        "Research only. This is not financial advice and does not produce buy/sell recommendations.",
        "",
        "## Executive summary",
        f"- Assets covered: {len(assets)}",
        f"- Warning count: {len(context.get('warnings', []))}",
        "",
        "## Top valuation discounts",
    ]
    for row in discounts[:5]:
        lines.append(f"- {row['ticker']}: premium/discount {row['premium_discount_pct']:.1%}, NAV confidence {row.get('nav_confidence', 0):.0%}")
    lines.extend(["", "## Best liquidity-adjusted opportunities"])
    for row in assets[:5]:
        lines.append(f"- {row['ticker']}: score {row.get('investment_score', 0):.1f}, liquidity score {row.get('liquidity_score', 0):.1f}")
    lines.extend(["", "## Category movers", "- Manual seed data only; category momentum defaults require external data before interpretation."])
    lines.extend(["", "## Recent exits"])
    exits = context.get("recent_exits", [])
    if exits:
        for row in exits[:5]:
            lines.append(f"- {row.get('series_name') or row.get('asset_id')}: sale price {row.get('sale_price')}")
    else:
        lines.append("- No processed exits available.")
    lines.extend(["", "## Data-quality warnings"])
    for warning in context.get("warnings", []) or ["No generated warnings."]:
        lines.append(f"- {warning}")
    lines.extend(["", "## Watchlist"])
    for row in assets[:5]:
        lines.append(f"- {row['ticker']}: verify comps, liquidity, SEC filing history, and offering economics.")
    lines.extend(["", "## Caveats"])
    for caveat in context.get("caveats", []):
        lines.append(f"- {caveat}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today")
    args = parser.parse_args()
    report_date = date.today().isoformat() if args.date == "today" else args.date
    context_path = DATA_PROCESSED / "ai_context.json"
    if not context_path.exists():
        raise SystemExit("Run python scripts/build_dataset.py before writing a report.")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["as_of"] = report_date
    report = _render_template(context)
    REPORTS.mkdir(parents=True, exist_ok=True)
    output = REPORTS / f"collectibles_report_{report_date}.md"
    output.write_text(report, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
