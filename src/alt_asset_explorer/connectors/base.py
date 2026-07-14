from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class CsvConnector:
    name: str
    path: Path
    normalize: Callable[[pd.DataFrame], pd.DataFrame]

    def load_raw(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame()
        return pd.read_csv(self.path)

    def load_normalized(self) -> pd.DataFrame:
        raw = self.load_raw()
        if raw.empty:
            return pd.DataFrame()
        return self.normalize(raw)
