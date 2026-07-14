from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.manual_imports import add_common_args, import_price_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import manually researched Rally price observations.")
    add_common_args(parser)
    args = parser.parse_args()
    try:
        outcome = import_price_history(
            args.input,
            dry_run=args.dry_run,
            strict=args.strict,
            output_dir=args.output_dir,
            tolerance=args.materiality_tolerance,
            max_quarter_lookback_days=args.max_quarter_lookback_days,
        )
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    print(outcome.summary())
    if args.strict and (len(outcome.rejected) or outcome.warnings):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
