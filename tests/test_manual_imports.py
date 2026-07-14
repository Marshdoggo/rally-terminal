from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from alt_asset_explorer.manual_imports import (
    ASSET_COLUMNS,
    PRICE_COLUMNS,
    import_assets,
    import_price_history,
    validate_asset_rows,
    validate_price_rows,
)


def _asset_row(**overrides):
    row = {
        "asset_id": "rally-test-asset",
        "ticker": "TEST",
        "asset_name": "Test Asset",
        "category": "cards",
        "subcategory": "test",
        "status": "trading",
        "shares_outstanding": "1000",
        "offering_date": "2025-12-15",
        "offering_price_per_share": "10",
        "offering_market_cap": "10000",
        "first_trade_date": "2026-01-01",
        "exit_date": "",
        "exit_price_per_share": "",
        "exit_value_total": "",
        "exit_type": "",
        "source_reference": "manual fixture",
        "verified_at": "2026-07-11T12:00:00Z",
        "notes": "fixture",
    }
    row.update(overrides)
    return row


def _price_row(**overrides):
    row = {
        "asset_id": "rally-test-asset",
        "period_end": "2026-03-31",
        "observed_at": "2026-03-28",
        "price_per_share": "12",
        "market_cap": "12000",
        "event_type": "executed_trade",
        "source_type": "manual_research",
        "source_reference": "manual fixture",
        "collected_at": "2026-07-11T12:05:00Z",
        "researcher": "tester",
        "precision_status": "exact",
        "notes": "fixture",
    }
    row.update(overrides)
    return row


def _write(path: Path, rows: list[dict]) -> Path:
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_valid_asset_import_preserves_source_and_writes_normalized(tmp_path: Path):
    path = _write(tmp_path / "assets.csv", [_asset_row()])
    outcome = import_assets(path, output_dir=tmp_path / "normalized")

    assert len(outcome.accepted) == 1
    out = pd.read_csv(tmp_path / "normalized" / "assets.csv")
    assert out.iloc[0]["source_reference"] == "manual fixture"
    assert out.iloc[0]["implied_offering_market_cap"] == 10000


def test_valid_price_history_import_preserves_exact_status(tmp_path: Path):
    output_dir = tmp_path / "normalized"
    import_assets(_write(tmp_path / "assets.csv", [_asset_row()]), output_dir=output_dir)
    outcome = import_price_history(_write(tmp_path / "prices.csv", [_price_row(precision_status="chart_estimate", event_type="chart_observation")]), output_dir=output_dir)

    assert len(outcome.accepted) == 1
    out = pd.read_csv(output_dir / "price_observations.csv")
    assert out.iloc[0]["precision_status"] == "chart_estimate"
    assert out.iloc[0]["source_reference"] == "manual fixture"


def test_missing_required_columns_raise():
    frame = pd.DataFrame([_asset_row()]).drop(columns=["asset_id"])
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_asset_rows(frame)


def test_unknown_asset_id_rejected():
    accepted, rejected, _ = validate_price_rows(pd.DataFrame([_price_row(asset_id="missing")]), pd.DataFrame([_asset_row()]))
    assert accepted.empty
    assert "unknown_asset_id" in rejected.iloc[0]["rejection_reason"]


def test_duplicate_asset_id_rejected():
    accepted, rejected, _ = validate_asset_rows(pd.DataFrame([_asset_row(), _asset_row(asset_name="Changed")]))
    assert len(accepted) == 1
    assert "duplicate_asset_id" in rejected.iloc[0]["rejection_reason"]


def test_duplicate_price_observation_rejected():
    accepted, rejected, _ = validate_price_rows(pd.DataFrame([_price_row(), _price_row()]), pd.DataFrame([_asset_row()]))
    assert len(accepted) == 1
    assert "duplicate_price_observation" in rejected.iloc[0]["rejection_reason"]


def test_conflicting_same_date_price_observation_rejected():
    accepted, rejected, _ = validate_price_rows(pd.DataFrame([_price_row(), _price_row(price_per_share="13")]), pd.DataFrame([_asset_row()]))
    assert len(accepted) == 1
    assert "conflicting_price_observation" in rejected.iloc[0]["rejection_reason"]


def test_period_end_must_be_calendar_quarter_end():
    accepted, rejected, _ = validate_price_rows(pd.DataFrame([_price_row(period_end="2026-03-30")]), pd.DataFrame([_asset_row()]))
    assert accepted.empty
    assert "period_end_not_calendar_quarter_end" in rejected.iloc[0]["rejection_reason"]


def test_observed_at_after_period_end_is_preserved_with_warning():
    accepted, rejected, warnings = validate_price_rows(pd.DataFrame([_price_row(observed_at="2026-04-01")]), pd.DataFrame([_asset_row()]))
    assert len(accepted) == 1
    assert rejected.empty
    assert "observed_at_after_period_end" in warnings[0]


def test_quarter_lookback_warning_is_configurable():
    accepted, rejected, warnings = validate_price_rows(
        pd.DataFrame([_price_row(observed_at="2026-03-01")]),
        pd.DataFrame([_asset_row()]),
        max_quarter_lookback_days=14,
    )
    assert rejected.empty
    assert "observed_at_exceeds_quarter_lookback" in warnings[0]


def test_invalid_dates_controlled_values_and_negative_numbers_rejected():
    accepted, rejected, _ = validate_price_rows(
        pd.DataFrame([_price_row(observed_at="not-a-date", event_type="bid", price_per_share="-1", source_type="bad", precision_status="perfect")]),
        pd.DataFrame([_asset_row()]),
    )
    assert accepted.empty
    reasons = rejected.iloc[0]["rejection_reason"]
    assert "invalid_observed_at" in reasons
    assert "invalid_event_type" in reasons
    assert "invalid_source_type" in reasons
    assert "invalid_precision_status" in reasons
    assert "nonpositive_price_per_share" in reasons


def test_negative_share_count_rejected():
    accepted, rejected, _ = validate_asset_rows(pd.DataFrame([_asset_row(shares_outstanding="-10")]))
    assert accepted.empty
    assert "nonpositive_shares_outstanding" in rejected.iloc[0]["rejection_reason"]


def test_market_cap_reconciliation_warns_with_tolerance():
    accepted, rejected, warnings = validate_asset_rows(pd.DataFrame([_asset_row(offering_market_cap="10020")]), tolerance=0.01)
    assert rejected.empty
    assert warnings == []
    accepted, rejected, warnings = validate_asset_rows(pd.DataFrame([_asset_row(offering_market_cap="12000")]), tolerance=0.01)
    assert rejected.empty
    assert "offering_market_cap_reconciliation_difference" in warnings[0]


def test_observed_market_cap_reconciliation_warns():
    accepted, rejected, warnings = validate_price_rows(pd.DataFrame([_price_row(market_cap="15000")]), pd.DataFrame([_asset_row()]), tolerance=0.01)
    assert rejected.empty
    assert "observed_market_cap_reconciliation_difference" in warnings[0]


def test_dry_run_does_not_write_outputs(tmp_path: Path):
    outcome = import_assets(_write(tmp_path / "assets.csv", [_asset_row()]), dry_run=True, output_dir=tmp_path / "normalized")
    assert len(outcome.accepted) == 1
    assert not (tmp_path / "normalized" / "assets.csv").exists()


def test_quarantine_output_written_for_rejections(tmp_path: Path):
    outcome = import_assets(_write(tmp_path / "assets.csv", [_asset_row(asset_id="")]), output_dir=tmp_path / "normalized")
    assert len(outcome.rejected) == 1
    assert outcome.quarantine_path is not None
    assert outcome.quarantine_path.exists()
    assert "missing_asset_id" in pd.read_csv(outcome.quarantine_path).iloc[0]["rejection_reason"]


def test_idempotent_repeated_import(tmp_path: Path):
    output_dir = tmp_path / "normalized"
    path = _write(tmp_path / "assets.csv", [_asset_row()])
    first = import_assets(path, output_dir=output_dir)
    second = import_assets(path, output_dir=output_dir)
    assert len(first.accepted) == 1
    assert len(second.accepted) == 1
    assert len(pd.read_csv(output_dir / "assets.csv")) == 1


def test_template_column_lists_are_stable():
    assert ASSET_COLUMNS[0] == "asset_id"
    assert PRICE_COLUMNS[0] == "asset_id"
    assert "period_end" in PRICE_COLUMNS
