# Manual Rally Research Workflow

This project accepts human-transcribed Rally research only. Do not scrape Rally for this workflow, and do not fabricate missing fields.

1. Select one Rally asset from the initial research universe.
2. Verify its identity, ticker, and Rally URL.
3. Record category and subcategory using the project’s current category vocabulary where possible.
4. Record shares outstanding exactly as shown by Rally or the cited source.
5. Record offering price per share and offering market cap when visible.
6. Record current status: announced, offering, funded, holding_period, trading, accepting_orders, suspended, asset_sale_pending, liquidated, delisted, or unknown.
7. Open the historical trading view.
8. Record each visible historical point as a separate row.
9. Distinguish exact tooltip values from rounded values and chart estimates.
10. Retain the Rally source reference or SEC/manual source reference for every row.
11. Save the CSVs as `data/manual_imports/incoming/rally_asset_master_manual.csv` and `data/manual_imports/incoming/rally_quarterly_prices_manual.csv`.
12. Run the combined processor in dry-run mode:

```bash
python3 scripts/process_manual_research.py \
  --assets data/manual_imports/incoming/rally_asset_master_manual.csv \
  --prices data/manual_imports/incoming/rally_quarterly_prices_manual.csv \
  --dry-run
```

13. Review warnings and quarantined-row reasons.
14. Run the actual import without `--dry-run`:

```bash
python3 scripts/process_manual_research.py \
  --assets data/manual_imports/incoming/rally_asset_master_manual.csv \
  --prices data/manual_imports/incoming/rally_quarterly_prices_manual.csv
```

15. The processor rebuilds coverage and indices after a successful actual import.

Original manual files are archived by run ID. Rejected rows are written to `data/manual_imports/quarantine/` with machine-readable rejection reasons.
