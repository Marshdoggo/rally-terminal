# Raw Page Captures

Place copied or saved visible auction-result text here before converting it into import CSVs.

Example:

```bash
python3 scripts/import_sothebys_capture.py data/raw/captures/sothebys_handbags_2026_06_page_1.txt \
  --auction-name "Handbags and Trunks: Including Property of An Important Private Collector" \
  --auction-url "https://www.sothebys.com/en/buy/auction/2026/handbags-and-accessories-3?locale=en&lotFilter=AllLots" \
  --sale-date 2026-06-23 \
  --venue "New York"
```

These files are user-captured source material. They are not normalized until an importer writes a CSV under `data/raw/imports/`.

For the February 2026 Sotheby's Handbags & Accessories page 2 capture, paste visible page text into:

```text
data/raw/captures/sothebys_handbags_accessories_2026_02_page_2.txt
```

Then run:

```bash
python3 scripts/import_sothebys_capture.py data/raw/captures/sothebys_handbags_accessories_2026_02_page_2.txt \
  --auction-name "Handbags & Accessories" \
  --auction-url "https://www.sothebys.com/en/buy/auction/2026/handbags-accessories?locale=en&lotFilter=AllLots" \
  --sale-date 2026-02-12 \
  --venue "New York" \
  --brand-filter Hermes \
  --output data/raw/imports/sothebys_results.csv \
  --append
```
