from pathlib import Path

import pytest

from alt_asset_explorer.custom_index_storage import (
    CombinedCustomIndexRegistry,
    CustomIndexStorageError,
    DuplicateCustomIndexError,
    JsonDirectoryCustomIndexStorage,
    custom_index_storage_is_read_only,
)
from alt_asset_explorer.custom_indices import new_custom_index_definition


def definition(name: str = "Space Race"):
    return new_custom_index_definition(
        name=name,
        description="Test basket",
        constituents=[{"asset_id": "moon", "ticker": "MOON", "weight": 1.0}],
        weighting_method="equal",
    )


def test_valid_index_saves_reloads_and_appears_in_registry(tmp_path: Path):
    curated = JsonDirectoryCustomIndexStorage(tmp_path / "curated", read_only=True)
    local = JsonDirectoryCustomIndexStorage(tmp_path / "local")
    registry = CombinedCustomIndexRegistry(curated, local)
    saved = registry.save(definition())
    assert registry.get(saved.id) == saved
    assert [item.id for item in registry.list()] == [saved.id]


def test_duplicate_id_and_name_are_rejected(tmp_path: Path):
    storage = JsonDirectoryCustomIndexStorage(tmp_path)
    first = storage.save(definition())
    with pytest.raises(DuplicateCustomIndexError, match="ID"):
        storage.save(first)
    with pytest.raises(DuplicateCustomIndexError, match="named"):
        storage.save(definition("space race"))


def test_corrupt_and_stale_records_are_skipped(tmp_path: Path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    stale = definition().model_dump(mode="json")
    stale["schema_version"] = 999
    import json
    (tmp_path / "stale.json").write_text(json.dumps(stale), encoding="utf-8")
    assert JsonDirectoryCustomIndexStorage(tmp_path).list() == []


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_cloud_read_only_flag_accepts_truthy_values(value: str):
    assert custom_index_storage_is_read_only({"RALLY_CUSTOM_INDEX_READ_ONLY": value})


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_cloud_read_only_flag_defaults_to_writable(value: str):
    assert not custom_index_storage_is_read_only({"RALLY_CUSTOM_INDEX_READ_ONLY": value})


def test_read_only_store_rejects_save(tmp_path: Path):
    storage = JsonDirectoryCustomIndexStorage(tmp_path, read_only=True)
    with pytest.raises(CustomIndexStorageError, match="read-only"):
        storage.save(definition())
