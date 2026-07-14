from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alt_asset_explorer.manual_imports import PRICE_EVENT_TYPES, quarter_ends_between
from alt_asset_explorer.paths import DATA_NORMALIZED, DATA_REPORTS, ensure_dirs


COVERAGE_COLUMNS = [
    "asset_id",
    "ticker",
    "asset_name",
    "category",
    "shares_verified",
    "offering_price_verified",
    "offering_market_cap_verified",
    "first_observation_date",
    "last_observation_date",
    "observation_count",
    "exact_observation_count",
    "rounded_observation_count",
    "chart_estimate_count",
    "unverified_observation_count",
    "visible_points_expected",
    "visible_points_captured",
    "historical_capture_pct",
    "largest_observation_gap_days",
    "index_eligible_equal_weight",
    "index_eligible_market_cap",
    "exclusion_reasons",
    "warning_count",
    "expected_quarters",
    "captured_quarters",
    "quarterly_capture_pct",
    "first_period_end",
    "last_period_end",
    "missing_period_ends",
    "duplicate_period_ends",
    "quarters_with_market_cap_validation",
    "quarters_with_warnings",
]


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _bool(value: object) -> bool:
    return bool(pd.notna(value) and str(value).strip() and str(value).strip().lower() != "nan")


def _largest_gap(dates: pd.Series) -> int | None:
    parsed = pd.to_datetime(dates, errors="coerce").dropna().sort_values()
    if len(parsed) < 2:
        return None
    gaps = parsed.diff().dropna().dt.days
    return int(gaps.max()) if not gaps.empty else None


def _clean_periods(values: pd.Series) -> list[str]:
    parsed = pd.to_datetime(values, errors="coerce").dropna().sort_values()
    return [item.date().isoformat() for item in parsed]


def build_research_coverage() -> pd.DataFrame:
    ensure_dirs()
    assets = _read(DATA_NORMALIZED / "assets.csv")
    prices = _read(DATA_NORMALIZED / "price_observations.csv")
    if assets.empty:
        out = pd.DataFrame(columns=COVERAGE_COLUMNS)
    else:
        if prices.empty:
            prices = pd.DataFrame(columns=["asset_id", "observed_at", "event_type", "precision_status", "market_cap", "warning_reason"])
        visible_meta = _read(DATA_NORMALIZED / "research_capture_metadata.csv")
        meta = {}
        if not visible_meta.empty and {"asset_id", "visible_points_expected", "visible_points_captured"}.issubset(visible_meta.columns):
            meta = visible_meta.set_index("asset_id").to_dict("index")
        rows: list[dict[str, object]] = []
        for _, asset in assets.sort_values("asset_id").iterrows():
            asset_id = asset["asset_id"]
            obs = prices[prices["asset_id"].astype(str) == str(asset_id)].copy()
            price_obs = obs[obs.get("event_type", pd.Series(dtype=str)).astype(str).isin(PRICE_EVENT_TYPES)].copy()
            precision = price_obs.get("precision_status", pd.Series(dtype=str)).astype(str)
            dates = pd.to_datetime(price_obs.get("observed_at", pd.Series(dtype=str)), errors="coerce").dropna()
            period_values = _clean_periods(price_obs.get("period_end", pd.Series(dtype=str)))
            captured_periods = sorted(set(period_values))
            duplicated_periods = sorted({period for period in period_values if period_values.count(period) > 1})
            expected_periods = []
            if _bool(asset.get("first_trade_date")):
                expected_periods = quarter_ends_between(asset.get("first_trade_date"), asset.get("exit_date") if _bool(asset.get("exit_date")) else pd.Timestamp.today().date().isoformat())
            missing_periods = sorted(set(expected_periods) - set(captured_periods)) if expected_periods else []
            visible_expected = meta.get(asset_id, {}).get("visible_points_expected")
            visible_captured = meta.get(asset_id, {}).get("visible_points_captured")
            expected_num = pd.to_numeric(visible_expected, errors="coerce")
            captured_num = pd.to_numeric(visible_captured, errors="coerce")
            capture_pct = None
            if pd.notna(expected_num) and expected_num > 0 and pd.notna(captured_num):
                capture_pct = float(captured_num) / float(expected_num)
            has_secondary_price = not price_obs.empty and pd.to_numeric(price_obs.get("price_per_share"), errors="coerce").gt(0).any()
            has_market_cap = pd.to_numeric(price_obs.get("market_cap"), errors="coerce").gt(0).any()
            has_shares = pd.to_numeric(pd.Series([asset.get("shares_outstanding")]), errors="coerce").notna().iloc[0]
            warnings = []
            if not has_secondary_price:
                warnings.append("missing_secondary_price_observation")
            if not has_shares:
                warnings.append("missing_shares_outstanding")
            if not has_market_cap:
                warnings.append("missing_observed_market_cap")
            warning_reason = str(asset.get("warning_reason") or "")
            obs_warnings = price_obs.get("warning_reason", pd.Series(dtype=str)).fillna("").astype(str)
            quarters_with_warnings = int(obs_warnings.map(lambda value: bool(value.strip())).sum())
            warning_count = len([item for item in warning_reason.split(";") if item.strip()]) + len(warnings) + quarters_with_warnings
            market_cap_validation = price_obs.get("implied_market_cap", pd.Series(dtype=str))
            quarters_with_market_cap_validation = int(pd.to_numeric(market_cap_validation, errors="coerce").notna().sum())
            rows.append(
                {
                    "asset_id": asset_id,
                    "ticker": asset.get("ticker"),
                    "asset_name": asset.get("asset_name"),
                    "category": asset.get("category"),
                    "shares_verified": _bool(asset.get("shares_outstanding")),
                    "offering_price_verified": _bool(asset.get("offering_price_per_share")),
                    "offering_market_cap_verified": _bool(asset.get("offering_market_cap")),
                    "first_observation_date": dates.min().date().isoformat() if not dates.empty else None,
                    "last_observation_date": dates.max().date().isoformat() if not dates.empty else None,
                    "observation_count": int(len(price_obs)),
                    "exact_observation_count": int((precision == "exact").sum()),
                    "rounded_observation_count": int((precision == "rounded").sum()),
                    "chart_estimate_count": int((precision == "chart_estimate").sum()),
                    "unverified_observation_count": int((precision == "unverified").sum()),
                    "visible_points_expected": None if pd.isna(expected_num) else int(expected_num),
                    "visible_points_captured": None if pd.isna(captured_num) else int(captured_num),
                    "historical_capture_pct": capture_pct,
                    "largest_observation_gap_days": _largest_gap(price_obs.get("observed_at", pd.Series(dtype=str))),
                    "index_eligible_equal_weight": bool(has_secondary_price),
                    "index_eligible_market_cap": bool(has_secondary_price and has_shares and has_market_cap),
                    "exclusion_reasons": "; ".join(warnings),
                    "warning_count": warning_count,
                    "expected_quarters": len(expected_periods) if expected_periods else None,
                    "captured_quarters": len(captured_periods),
                    "quarterly_capture_pct": (len(captured_periods) / len(expected_periods)) if expected_periods else None,
                    "first_period_end": captured_periods[0] if captured_periods else None,
                    "last_period_end": captured_periods[-1] if captured_periods else None,
                    "missing_period_ends": "; ".join(missing_periods),
                    "duplicate_period_ends": "; ".join(duplicated_periods),
                    "quarters_with_market_cap_validation": quarters_with_market_cap_validation,
                    "quarters_with_warnings": quarters_with_warnings,
                }
            )
        out = pd.DataFrame(rows, columns=COVERAGE_COLUMNS)

    DATA_REPORTS.mkdir(parents=True, exist_ok=True)
    out.to_csv(DATA_REPORTS / "research_coverage.csv", index=False)
    (DATA_REPORTS / "research_coverage.json").write_text(json.dumps(out.to_dict("records"), indent=2, sort_keys=True) + "\n")
    return out


if __name__ == "__main__":
    coverage = build_research_coverage()
    print(f"Wrote research coverage: {len(coverage)} assets")
