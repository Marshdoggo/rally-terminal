from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "src" / "alt_asset_explorer"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_MANUAL_IMPORTS = PROJECT_ROOT / "data" / "manual_imports"
DATA_NORMALIZED = PROJECT_ROOT / "data" / "normalized"
DATA_REPORTS = PROJECT_ROOT / "data" / "reports"
REPORTS = PROJECT_ROOT / "reports"
CONFIG = PROJECT_ROOT / "config"


def ensure_dirs() -> None:
    for path in (
        DATA_RAW,
        DATA_PROCESSED,
        DATA_MANUAL_IMPORTS / "incoming",
        DATA_MANUAL_IMPORTS / "archive",
        DATA_MANUAL_IMPORTS / "quarantine",
        DATA_MANUAL_IMPORTS / "templates",
        DATA_NORMALIZED,
        DATA_REPORTS,
        REPORTS,
        DATA_RAW / "sec",
    ):
        path.mkdir(parents=True, exist_ok=True)
