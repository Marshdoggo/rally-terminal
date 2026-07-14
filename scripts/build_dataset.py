from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.pipeline import build_dataset


if __name__ == "__main__":
    outputs = build_dataset()
    print("Built processed datasets:")
    for name, frame in outputs.items():
        print(f"- {name}: {len(frame)} rows")
