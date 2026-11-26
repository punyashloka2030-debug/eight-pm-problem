# Spreadsheet vs pandas: the same hour-by-weekday pivot, built twice

Both versions use the same input: `data/manual/spreadsheet_export_city_hourly.csv`
(9,385 rows: mean PM2.5 across reporting stations, per hour).

**Automatic check (src/13_compare_spreadsheet.py):** 168 cells (24 hours x 7 weekdays);
168 match within 0.01 µg/m³; 0 missing on one side; largest difference
0.0050 µg/m³. **Result: MATCH.**

| | Spreadsheet (LibreOffice Calc) | pandas |
|---|---|---|
| Time taken | about 25-30 minutes | one `pivot_table` line; re-runs in seconds with `make analysis` |
| Row limit | about 1 million rows per sheet; we had to export a 9,385-row city average, not the 279,552-row readings table | no fixed limit; memory is the limit (the full table loads in seconds) |
| Reproducibility | clicks are not recorded; we kept screenshots (report/img/) and wrote the steps in MANUAL_STEPS.md | the code is the record; anyone can re-run it from raw data |
| Error risk | easy to pick the wrong summary (Sum instead of Mean) or a wrong range; weekdays sort alphabetically | errors are in code, so they can be reviewed and tested; same result every run |
| Best for | a quick look and sharing with non-coders | the pipeline, big tables, anything that must be repeated |

The "Mean" option is called "Average" in LibreOffice, the Save As box tried to overwrite the input file, and the terminal stayed busy while LibreOffice was open. Those are exactly the error risks the brief wants compared.
