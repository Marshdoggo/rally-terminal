import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from app_data import DATA_PROCESSED, PROJECT_ROOT, processed_path


def test_app_data_resolves_repo_processed_path():
    assert PROJECT_ROOT == ROOT
    assert DATA_PROCESSED == ROOT / "data" / "processed"
    assert processed_path("assets") == ROOT / "data" / "processed" / "assets.csv"
