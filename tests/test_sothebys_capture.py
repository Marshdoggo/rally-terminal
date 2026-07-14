from pathlib import Path
import importlib.util
import sys

from alt_asset_explorer.connectors.category_imports import load_sothebys_results

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_sothebys_capture.py"
SPEC = importlib.util.spec_from_file_location("import_sothebys_capture", SCRIPT_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
lots_to_frame = MODULE.lots_to_frame
parse_sothebys_capture = MODULE.parse_sothebys_capture
write_import_csv = MODULE.write_import_csv
capture_stats = MODULE.capture_stats


CAPTURE_TEXT = """
1. Hermes
Rouge de Coeur Epsom Kelly 25 Sellier Gold Hardware, 2016
Estimate:
14,000 - 20,000 USD
LOT SOLD:
35,840 USD
Bidding is closed

7. Hermes
Bordeaux Shiny Porosus Crocodile Birkin 35 Palladium Hardware, 2010
Estimate:
25,000 - 35,000 USD
LOT SOLD:
32,000 USD
Bidding is closed

14. Louis Vuitton
Vintage Monogram Canvas Malle Courrier Lozine 100 Brass Hardware
Estimate:
10,000 - 15,000 USD
LOT SOLD:
20,480 USD
Bidding is closed
"""


CAPTURE_TEXT_WITH_MISSING_SOLD = """
1. Hermes
Rouge de Coeur Epsom Kelly 25 Sellier Gold Hardware, 2016
Estimate:
14,000 - 20,000 USD
Bidding is closed

13. Hermes
Rouge Sellier Clemence Birkin 35 Gold Hardware, 1999
Estimate:
8,000 - 14,000 USD
LOT SOLD:
12,800 USD
Bidding is closed
"""


def test_parse_sothebys_capture_extracts_lot_fields():
    lots = parse_sothebys_capture(
        CAPTURE_TEXT,
        auction_url="https://www.sothebys.com/en/buy/auction/2026/handbags-and-accessories-3",
        brand_filter="Hermes",
    )

    assert len(lots) == 2
    assert lots[1].lot_id == "7"
    assert lots[1].brand == "Hermes"
    assert lots[1].model == "Birkin"
    assert lots[1].size == "35"
    assert lots[1].material == "Porosus Crocodile"
    assert lots[1].estimate_low_usd == 25000
    assert lots[1].estimate_high_usd == 35000
    assert lots[1].realized_price_usd == 32000
    assert lots[1].currency == "USD"


def test_capture_stats_reports_missing_sold_prices():
    stats = capture_stats(CAPTURE_TEXT_WITH_MISSING_SOLD, brand_filter="Hermes")

    assert stats["lot_headers"] == 2
    assert stats["brand_matching_lots"] == 2
    assert stats["sold_price_lots"] == 1
    assert stats["brand_matching_sold_price_lots"] == 1


def test_sothebys_capture_output_loads_as_import_csv(tmp_path: Path):
    lots = parse_sothebys_capture(
        CAPTURE_TEXT,
        auction_url="https://www.sothebys.com/en/buy/auction/2026/handbags-and-accessories-3",
        brand_filter="Hermes",
    )
    frame = lots_to_frame(
        lots,
        auction_name="Handbags and Trunks: Including Property of An Important Private Collector",
        auction_url="https://www.sothebys.com/en/buy/auction/2026/handbags-and-accessories-3",
        sale_date="2026-06-23",
        venue="New York",
        category="handbags",
    )
    path = tmp_path / "sothebys_results.csv"

    write_import_csv(frame, path)
    comps = load_sothebys_results(path)

    assert len(comps) == 2
    assert comps.iloc[0]["source"] == "Sothebys"
    assert comps.iloc[0]["source_access"] == "user_export"
    assert comps.iloc[0]["price_type"] == "realized_with_premium"
    assert comps.iloc[0]["buyer_premium_included"]
    assert comps.iloc[1]["price_usd"] == 32000
