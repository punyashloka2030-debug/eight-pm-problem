"""
13_compare_spreadsheet.py — manual step M10, the automatic check:
did the spreadsheet pivot (built by hand in LibreOffice/Excel/Google Sheets)
give the SAME numbers as the pandas pivot?

Input:   data/manual/spreadsheet_pivot.csv        the pivot exported from the spreadsheet (M10)
         outputs/tables/pivot_hour_weekday_pandas.csv   from 10_analysis.py (same source file)
Output:  outputs/tables/spreadsheet_vs_pandas.csv  cell-by-cell differences
         report/spreadsheet_vs_pandas.md           the side-by-side note for the report

Both pivots are built from the same file, data/manual/spreadsheet_export_city_hourly.csv
(mean city PM2.5 per hour), so any difference means a mistake in one of them.

Run:  python src/13_compare_spreadsheet.py
"""

import csv

import pandas as pd

from common import MANUAL, ROOT, TABLES

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TOLERANCE = 0.01  # µg/m³; spreadsheets and pandas may round the last digit differently


def read_spreadsheet_pivot(path):
    """
    A spreadsheet pivot exported to CSV has title rows above the table and
    maybe a 'Total Result' row and column. We look for the header row that
    contains weekday names, then read the hour rows below it.
    """
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header_index = next(i for i, row in enumerate(rows) if sum(c.strip() in WEEKDAYS for c in row) >= 5)
    header = [c.strip() for c in rows[header_index]]

    records = []
    for row in rows[header_index + 1:]:
        first = row[0].strip() if row else ""
        if not first.replace(".", "", 1).isdigit():  # stops at 'Total Result' or blank rows
            continue
        for column, cell in zip(header[1:], row[1:]):
            if column in WEEKDAYS and cell.strip():
                records.append({"hour": int(float(first)), "weekday": column,
                                "spreadsheet": float(cell.replace(",", ""))})
    return pd.DataFrame(records)


def main():
    sheet = read_spreadsheet_pivot(MANUAL / "spreadsheet_pivot.csv")
    pandas_pivot = pd.read_csv(TABLES / "pivot_hour_weekday_pandas.csv", index_col="hour")
    pandas_long = pandas_pivot.reset_index().melt(id_vars="hour", var_name="weekday", value_name="pandas")

    both = pandas_long.merge(sheet, on=["hour", "weekday"], how="outer", indicator=True)
    both["abs_diff"] = (both["pandas"] - both["spreadsheet"]).abs().round(4)
    both.to_csv(TABLES / "spreadsheet_vs_pandas.csv", index=False)

    n_cells = len(pandas_long)
    missing = int((both["_merge"] != "both").sum())
    max_diff = float(both["abs_diff"].max())
    n_match = int((both["abs_diff"] <= TOLERANCE).sum())
    verdict = "MATCH" if missing == 0 and n_match == n_cells else "DIFFERENT"

    print(f"Cells compared: {n_cells}  |  matching within {TOLERANCE}: {n_match}  |  "
          f"missing on one side: {missing}  |  largest difference: {max_diff:.4f}  ->  {verdict}")

    rows_in_export = sum(1 for _ in open(MANUAL / "spreadsheet_export_city_hourly.csv")) - 1
    note = f"""# Spreadsheet vs pandas: the same hour-by-weekday pivot, built twice

Both versions use the same input: `data/manual/spreadsheet_export_city_hourly.csv`
({rows_in_export:,} rows: mean PM2.5 across reporting stations, per hour).

**Automatic check (src/13_compare_spreadsheet.py):** {n_cells} cells (24 hours x 7 weekdays);
{n_match} match within {TOLERANCE} µg/m³; {missing} missing on one side; largest difference
{max_diff:.4f} µg/m³. **Result: {verdict}.**

| | Spreadsheet (LibreOffice Calc) | pandas |
|---|---|---|
| Time taken | [[TODO-HUMAN: minutes it took you in M10]] | one `pivot_table` line; re-runs in seconds with `make analysis` |
| Row limit | about 1 million rows per sheet; we had to export a {rows_in_export:,}-row city average, not the 279,552-row readings table | no fixed limit; memory is the limit (the full table loads in seconds) |
| Reproducibility | clicks are not recorded; we kept screenshots (report/img/) and wrote the steps in MANUAL_STEPS.md | the code is the record; anyone can re-run it from raw data |
| Error risk | easy to pick the wrong summary (Sum instead of Mean) or a wrong range; weekdays sort alphabetically | errors are in code, so they can be reviewed and tested; same result every run |
| Best for | a quick look and sharing with non-coders | the pipeline, big tables, anything that must be repeated |

[[TODO-HUMAN: one or two sentences in your own words on what was easy or hard in the spreadsheet.]]
"""
    (ROOT / "report" / "spreadsheet_vs_pandas.md").write_text(note, encoding="utf-8")
    print("Note written to report/spreadsheet_vs_pandas.md")


if __name__ == "__main__":
    main()
