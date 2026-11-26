"""
05b_load_trends.py — load the Google Trends CSVs from manual step M7 and line
them up with our weekly air and rain data.

Input:   data/manual/trends_all_three.csv  (the export with all three terms on one 0-100 scale)
Output:  data/interim/trends_weekly.csv      long format: week_start x term x interest
         outputs/tables/trends_vs_data.csv   weekly search interest next to weekly rain and PM2.5
         outputs/tables/trends_correlation.csv

Google Trends is our "unstructured" source: it is built from millions of free-text
searches, and Google gives us only a relative index (100 = the busiest week in the
range). It is WEEKLY for a 14-month range, so it can add context, never explain one evening.

If M7 is not done yet, the script says so and stops without error.

Run:  python src/05b_load_trends.py
"""

import csv

import pandas as pd

from common import CLEAN, INTERIM, MANUAL, TABLES, log_decision, reset_cleaning_log_for_stage

STAGE = "05b_load_trends"
TRENDS_FILE = MANUAL / "trends_all_three.csv"


def read_trends_csv(path):
    """
    A Trends export may start with a 'Category: ...' line and a blank line
    before the real header ('Week', then one column per search term). Values
    below 1 are written as the TEXT '<1'. We find the header row, then read on.
    """
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header_index = next(i for i, r in enumerate(rows)
                        if r and r[0].strip().lower() in ("week", "day", "month", "time"))
    header = [h.strip() for h in rows[header_index]]
    data = [r for r in rows[header_index + 1:] if r and r[0].strip()]
    return pd.DataFrame(data, columns=header)


def main():
    if not TRENDS_FILE.exists():
        print(f"{TRENDS_FILE.name} not found: manual step M7 not done yet. Skipping Trends.")
        return
    reset_cleaning_log_for_stage(STAGE)

    wide = read_trends_csv(TRENDS_FILE)
    time_col = wide.columns[0]
    long = wide.melt(id_vars=time_col, var_name="term", value_name="interest_text")
    # Column names look like 'bangalore rain: (Karnataka)'; keep just the search term.
    long["term"] = long["term"].str.split(":").str[0].str.strip()

    # TYPE CASTING: '<1' is text meaning "more than 0 but under 1". We store 0.5,
    # the middle of that range, and count how many cells needed it.
    below_one = (long["interest_text"].str.strip() == "<1")
    long["interest"] = pd.to_numeric(long["interest_text"].str.replace("<1", "0.5", regex=False),
                                     errors="coerce")
    log_decision(STAGE, "Google Trends writes very low interest as the text '<1'", int(below_one.sum()),
                 "Replaced '<1' with 0.5, then cast the column from text to float",
                 "Numbers stored as text cannot be averaged; 0.5 is the middle of 'between 0 and 1'")
    unparsed = int(long["interest"].isna().sum())
    log_decision(STAGE, "Trends values that are still not numbers after casting", unparsed,
                 "Left missing", "Nothing to guess from")

    long["week_start"] = pd.to_datetime(long[time_col]).dt.date
    long = long[["week_start", "term", "interest"]]
    long.to_csv(INTERIM / "trends_weekly.csv", index=False)
    print(f"Trends: {long['week_start'].nunique()} weeks x {long['term'].nunique()} terms")

    # Weekly rain (mm) and weekly evening PM2.5 for the same weeks.
    # Trends weeks start on SUNDAY, so we label our days by the Sunday that starts their week.
    weather = pd.read_parquet(CLEAN / "weather_hourly.parquet")
    weather["week_start"] = (weather["ts_ist"] - pd.to_timedelta((weather["ts_ist"].dt.dayofweek + 1) % 7, unit="D")).dt.date
    rain = weather.groupby("week_start")["precip_mm"].sum().rename("rain_mm_week")

    pm = pd.read_parquet(CLEAN / "readings_clean.parquet")
    pm = pm[(pm["parameter"] == "pm25") & pm["value"].notna() & pm["ts_ist"].dt.hour.between(17, 23)]
    pm["week_start"] = (pm["ts_ist"] - pd.to_timedelta((pm["ts_ist"].dt.dayofweek + 1) % 7, unit="D")).dt.date
    evening = pm.groupby("week_start")["value"].mean().rename("evening_pm25_week")

    wide_terms = long.pivot(index="week_start", columns="term", values="interest")
    joined = wide_terms.join(rain).join(evening).dropna(subset=["rain_mm_week", "evening_pm25_week"])
    joined.round(2).to_csv(TABLES / "trends_vs_data.csv")

    # Spearman rank correlation: does search interest rise in the same weeks as rain / PM2.5?
    rows = []
    for term in wide_terms.columns:
        for measure in ["rain_mm_week", "evening_pm25_week"]:
            rows.append({"term": term, "measure": measure, "n_weeks": len(joined),
                         "spearman_rho": round(joined[term].corr(joined[measure], method="spearman"), 2)})
    corr = pd.DataFrame(rows)
    corr.to_csv(TABLES / "trends_correlation.csv", index=False)
    print(corr.to_string(index=False))


if __name__ == "__main__":
    main()
