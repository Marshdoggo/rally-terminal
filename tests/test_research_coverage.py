from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_coverage_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "build_research_coverage.py"
    spec = importlib.util.spec_from_file_location("build_research_coverage", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_coverage_percentage_remains_null_when_denominator_unknown(tmp_path: Path, monkeypatch):
    module = _load_coverage_module()
    normalized = tmp_path / "normalized"
    reports = tmp_path / "reports"
    normalized.mkdir()
    monkeypatch.setattr(module, "DATA_NORMALIZED", normalized)
    monkeypatch.setattr(module, "DATA_REPORTS", reports)
    monkeypatch.setattr(module, "ensure_dirs", lambda: None)

    pd.DataFrame(
        [
            {
                "asset_id": "a",
                "ticker": "A",
                "asset_name": "Asset A",
                "category": "cards",
                "shares_outstanding": "",
                "offering_price_per_share": "10",
                "offering_market_cap": "",
                "warning_reason": "",
            }
        ]
    ).to_csv(normalized / "assets.csv", index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "a",
                "observed_at": "2026-01-01",
                "price_per_share": "11",
                "market_cap": "",
                "event_type": "executed_trade",
                "precision_status": "exact",
            }
        ]
    ).to_csv(normalized / "price_observations.csv", index=False)

    coverage = module.build_research_coverage()

    assert pd.isna(coverage.iloc[0]["historical_capture_pct"])
    assert bool(coverage.iloc[0]["index_eligible_equal_weight"]) is True
    assert bool(coverage.iloc[0]["index_eligible_market_cap"]) is False
