from datetime import date

from alt_asset_explorer.export import MME_COLUMNS
from alt_asset_explorer.indices import RALLY_INDEX_COLUMNS
from alt_asset_explorer.pipeline import build_dataset


def test_mme_export_format():
    outputs = build_dataset(as_of=date(2026, 7, 2))
    export = outputs["universe_export"]
    assert list(export.columns) == MME_COLUMNS
    assert set(export["universe"]) == {"collectibles"}
    assert "rally_indices" in outputs
    assert list(outputs["rally_indices"].columns) == RALLY_INDEX_COLUMNS
