from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import ValidationError

from alt_asset_explorer.custom_indices import CustomIndexDefinition


READ_ONLY_ENV_VAR = "RALLY_CUSTOM_INDEX_READ_ONLY"


def custom_index_storage_is_read_only(env: dict[str, str] | None = None) -> bool:
    """Return whether local custom-index persistence is disabled for this runtime."""
    value = (env if env is not None else os.environ).get(READ_ONLY_ENV_VAR, "")
    return value.strip().casefold() in {"1", "true", "yes", "on"}


class CustomIndexStorageError(RuntimeError):
    pass


class DuplicateCustomIndexError(CustomIndexStorageError):
    pass


class CustomIndexStorage(ABC):
    @abstractmethod
    def list(self) -> list[CustomIndexDefinition]: ...

    @abstractmethod
    def get(self, index_id: str) -> CustomIndexDefinition | None: ...

    @abstractmethod
    def save(self, definition: CustomIndexDefinition) -> CustomIndexDefinition: ...


class JsonDirectoryCustomIndexStorage(CustomIndexStorage):
    """One validated JSON document per index; suitable for local development."""

    def __init__(self, directory: Path, *, read_only: bool = False):
        self.directory = Path(directory)
        self.read_only = read_only

    def _load_path(self, path: Path) -> CustomIndexDefinition | None:
        try:
            return CustomIndexDefinition.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError, json.JSONDecodeError):
            return None

    def list(self) -> list[CustomIndexDefinition]:
        if not self.directory.exists():
            return []
        records = [record for path in sorted(self.directory.glob("*.json")) if (record := self._load_path(path)) is not None]
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def get(self, index_id: str) -> CustomIndexDefinition | None:
        return self._load_path(self.directory / f"{index_id}.json") if (self.directory / f"{index_id}.json").exists() else None

    def save(self, definition: CustomIndexDefinition) -> CustomIndexDefinition:
        if self.read_only:
            raise CustomIndexStorageError("This custom-index store is read-only.")
        definition = CustomIndexDefinition.model_validate(definition)
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.get(definition.id) is not None:
            raise DuplicateCustomIndexError(f"An index with ID {definition.id!r} already exists.")
        duplicate_name = next((item for item in self.list() if item.name.casefold() == definition.name.casefold()), None)
        if duplicate_name:
            raise DuplicateCustomIndexError(f"An index named {definition.name!r} already exists.")
        destination = self.directory / f"{definition.id}.json"
        temporary = destination.with_suffix(".tmp")
        try:
            temporary.write_text(definition.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise CustomIndexStorageError(f"Unable to save custom index: {exc}") from exc
        return definition


class CombinedCustomIndexRegistry:
    """Read curated seed definitions and writable local definitions together."""

    def __init__(self, curated: CustomIndexStorage, local: CustomIndexStorage):
        self.curated = curated
        self.local = local

    def list(self) -> list[CustomIndexDefinition]:
        by_id = {item.id: item for item in self.curated.list()}
        by_id.update({item.id: item for item in self.local.list()})
        return sorted(by_id.values(), key=lambda item: item.updated_at, reverse=True)

    def get(self, index_id: str) -> CustomIndexDefinition | None:
        return self.local.get(index_id) or self.curated.get(index_id)

    def save(self, definition: CustomIndexDefinition) -> CustomIndexDefinition:
        if self.get(definition.id) is not None:
            raise DuplicateCustomIndexError(f"An index with ID {definition.id!r} already exists.")
        if any(item.name.casefold() == definition.name.casefold() for item in self.list()):
            raise DuplicateCustomIndexError(f"An index named {definition.name!r} already exists.")
        return self.local.save(definition)
