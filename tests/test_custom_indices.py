import pandas as pd
import pytest

from alt_asset_explorer.custom_indices import (
    build_custom_index,
    calculate_index_metrics,
    new_custom_index_definition,
    normalize_weights,
)


@pytest.fixture
def prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "a", "date": "2024-03-31", "last": 10},
            {"asset_id": "a", "date": "2024-06-30", "last": 12},
            {"asset_id": "a", "date": "2024-09-30", "last": 9},
            {"asset_id": "b", "date": "2024-03-31", "last": 20},
            {"asset_id": "b", "date": "2024-06-30", "last": 18},
            {"asset_id": "b", "date": "2024-09-30", "last": 22},
        ]
    )


def test_one_asset_matches_normalized_price(prices):
    result = build_custom_index(prices, asset_ids=["a"])
    assert result.series["index_level"].tolist() == pytest.approx([100, 120, 90])
    assert result.contributions.iloc[0]["contribution_points"] == pytest.approx(-10)


def test_equal_and_custom_weights_calculate_and_reconcile(prices):
    equal = build_custom_index(prices, asset_ids=["a", "b"])
    custom = build_custom_index(prices, asset_ids=["a", "b"], weights={"a": 0.75, "b": 0.25})

    assert equal.series["index_level"].tolist() == pytest.approx([100, 105, 100])
    assert custom.series.iloc[1]["index_level"] == pytest.approx(112.5)
    assert custom.series.iloc[-1]["index_level"] == pytest.approx(95.0)
    assert custom.contributions["contribution_points"].sum() == pytest.approx(-5.0)
    assert custom.contributions.iloc[0]["asset_id"] == "b"


def test_weights_normalize_or_reject():
    assert normalize_weights(["a", "b"], {"a": 3, "b": 1}) == {"a": 0.75, "b": 0.25}
    with pytest.raises(ValueError, match="positive"):
        normalize_weights(["a", "b"], {"a": 1, "b": 0})
    with pytest.raises(ValueError, match="exactly"):
        normalize_weights(["a", "b"], {"a": 1})


def test_alignment_uses_latest_common_start_and_drops_missing_dates():
    prices = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2023-12-31", "last": 8},
            {"asset_id": "a", "date": "2024-03-31", "last": 10},
            {"asset_id": "b", "date": "2024-03-31", "last": 20},
            {"asset_id": "a", "date": "2024-06-30", "last": 12},
            {"asset_id": "a", "date": "2024-09-30", "last": 14},
            {"asset_id": "b", "date": "2024-09-30", "last": 22},
        ]
    )
    result = build_custom_index(prices, asset_ids=["a", "b"])

    assert result.effective_start_date == "2024-03-31"
    assert result.series["date"].dt.date.astype(str).tolist() == ["2024-03-31", "2024-09-30"]
    assert result.warnings


def test_no_overlap_zero_and_invalid_prices_are_handled():
    no_overlap = pd.DataFrame(
        [
            {"asset_id": "a", "date": "2024-03-31", "last": 10},
            {"asset_id": "b", "date": "2024-06-30", "last": 20},
            {"asset_id": "b", "date": "2024-09-30", "last": 0},
        ]
    )
    result = build_custom_index(no_overlap, asset_ids=["a", "b"])
    assert result.series.empty
    assert "no common observed dates" in result.warnings[0]


def test_changing_constituent_or_weight_changes_result(prices):
    one = build_custom_index(prices, asset_ids=["a"])
    two = build_custom_index(prices, asset_ids=["a", "b"])
    weighted = build_custom_index(prices, asset_ids=["a", "b"], weights={"a": 0.8, "b": 0.2})
    assert not one.series["index_level"].equals(two.series["index_level"])
    assert not two.series["index_level"].equals(weighted.series["index_level"])


def test_metrics_known_drawdown_constant_and_insufficient_history():
    series = pd.DataFrame(
        {"date": pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2024-03-31"]), "index_level": [100, 120, 90, 110]}
    )
    metrics = calculate_index_metrics(series)
    assert metrics["total_return"] == pytest.approx(0.10)
    assert metrics["maximum_drawdown"] == pytest.approx(-0.25)
    assert metrics["current_drawdown"] == pytest.approx(110 / 120 - 1)
    assert metrics["best_period"] == pytest.approx(110 / 90 - 1)
    assert metrics["cagr"] is not None

    constant = calculate_index_metrics(pd.DataFrame({"date": ["2024-03-31", "2024-06-30", "2024-09-30"], "index_level": [100, 100, 100]}))
    assert constant["annualized_volatility"] == 0
    assert constant["sharpe_ratio"] is None
    short = calculate_index_metrics(pd.DataFrame({"date": ["2024-03-31"], "index_level": [100]}))
    assert short["annualized_volatility"] is None


def test_definition_validation_rejects_duplicates_and_bad_total():
    valid = new_custom_index_definition(
        name="Jurassic Index",
        description=None,
        constituents=[{"asset_id": "a", "weight": 0.5}, {"asset_id": "b", "weight": 0.5}],
        weighting_method="equal",
    )
    assert valid.id.startswith("custom_jurassic_index_")
    with pytest.raises(ValueError, match="sum"):
        new_custom_index_definition(
            name="Bad",
            description=None,
            constituents=[{"asset_id": "a", "weight": 0.2}],
            weighting_method="custom",
        )
    with pytest.raises(ValueError, match="unique"):
        new_custom_index_definition(
            name="Duplicate",
            description=None,
            constituents=[{"asset_id": "a", "weight": 0.5}, {"asset_id": "a", "weight": 0.5}],
            weighting_method="equal",
        )
