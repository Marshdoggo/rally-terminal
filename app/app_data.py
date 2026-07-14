from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_REPORTS = PROJECT_ROOT / "data" / "reports"
DATA_NORMALIZED = PROJECT_ROOT / "data" / "normalized"
DATA_MANUAL_QUARANTINE = PROJECT_ROOT / "data" / "manual_imports" / "quarantine"


def processed_path(name: str) -> Path:
    return DATA_PROCESSED / f"{name}.csv"


def load_processed_csv(name: str, *, required: bool = False) -> pd.DataFrame:
    path = processed_path(name)
    if not path.exists():
        if required:
            st.warning(f"Missing `{path.name}`. Run `python3 scripts/build_dataset.py` from `{PROJECT_ROOT}`.")
        return pd.DataFrame()
    return pd.read_csv(path)


def load_report_csv(name: str) -> pd.DataFrame:
    path = DATA_REPORTS / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_normalized_csv(name: str) -> pd.DataFrame:
    path = DATA_NORMALIZED / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def quarantined_row_count() -> int:
    total = 0
    for path in DATA_MANUAL_QUARANTINE.glob("*.csv"):
        try:
            total += len(pd.read_csv(path))
        except Exception:
            continue
    return total


def latest_processed_timestamp() -> str:
    files = list(DATA_PROCESSED.glob("*"))
    if not files:
        return "No processed files found"
    latest = max(file.stat().st_mtime for file in files if file.is_file())
    return pd.to_datetime(latest, unit="s").strftime("%Y-%m-%d %H:%M:%S")


def render_data_diagnostics() -> None:
    with st.sidebar.expander("Data diagnostics", expanded=False):
        st.caption(f"Project root: `{PROJECT_ROOT}`")
        st.caption(f"Processed data: `{DATA_PROCESSED}`")
        st.caption(f"Latest processed file: `{latest_processed_timestamp()}`")


def empty_state() -> None:
    st.info(f"Run `python3 scripts/build_dataset.py` from `{PROJECT_ROOT}` to generate processed data.")
