"""
07b_review_outliers.py — helper for manual step M11.

For each of the 10 cases in outputs/tables/outlier_review_top10.csv it prints:
  - the station's own readings 3 hours before and after (did it build up, or jump?)
  - every other station's reading in the same hour (was the whole city high?)
  - rain in that hour and whether the date is a festival
so a human can decide: real event, or sensor failure?

Then, to save the verdicts, run for example:
  python src/07b_review_outliers.py --save "real,failure,real,real,failure,real,real,real,failure,real"
(one word per case, in the order printed; "real" or "failure")

Run:  python src/07b_review_outliers.py
"""

import sys

import pandas as pd

from common import CLEAN, MANUAL, TABLES

REVIEW_FILE = TABLES / "outlier_review_top10.csv"


def show_case(number, case, readings, weather, festival_dates):
    station, ts = case["station_id"], pd.Timestamp(case["ts_ist"])
    pm = readings[readings["parameter"] == "pm25"]

    print("=" * 78)
    print(f"CASE {number}: {case['station_name']}  {ts:%a %d %b %Y %H:%M} IST  "
          f"PM2.5 = {case['value_raw']:.0f} µg/m³   (flag: {case['qc_flag']})")

    # 1. The same station, 3 hours either side.
    window = pm[(pm["station_id"] == station) &
                pm["ts_ist"].between(ts - pd.Timedelta(hours=3), ts + pd.Timedelta(hours=3))]
    line = "  ".join(f"{t:%H}h:{'--' if pd.isna(v) else f'{v:.0f}'}"
                     for t, v in zip(window["ts_ist"], window["value_raw"]))
    print(f"  This station, ±3 h : {line}")

    # 2. Every other station, same hour.
    same_hour = pm[(pm["ts_ist"] == ts) & (pm["station_id"] != station)]
    others = "  ".join(f"{s[3:]}:{'--' if pd.isna(v) else f'{v:.0f}'}"
                       for s, v in zip(same_hour["station_id"], same_hour["value_raw"]))
    print(f"  Other stations     : {others}")

    # 3. Weather and calendar.
    rain = weather.loc[weather["ts_ist"] == ts, "precip_mm"]
    rain_text = f"{rain.iloc[0]:.1f} mm" if len(rain) else "n/a"
    festival = "YES" if ts.date() in festival_dates else "no"
    print(f"  Rain this hour     : {rain_text}    Festival date: {festival}")


def main():
    review = pd.read_csv(REVIEW_FILE, parse_dates=["ts_ist"])

    if len(sys.argv) == 3 and sys.argv[1] == "--save":
        verdicts = [v.strip().lower() for v in sys.argv[2].split(",")]
        if len(verdicts) != len(review) or not set(verdicts) <= {"real", "failure"}:
            sys.exit(f"Need exactly {len(review)} words, each 'real' or 'failure'.")
        review["human_verdict"] = ["real_event" if v == "real" else "sensor_failure" for v in verdicts]
        review.to_csv(REVIEW_FILE, index=False)
        print(f"Saved verdicts to {REVIEW_FILE}")
        print(review[["station_name", "ts_ist", "value_raw", "qc_flag", "human_verdict"]].to_string())
        return

    readings = pd.read_parquet(CLEAN / "readings_clean.parquet")
    weather = pd.read_parquet(CLEAN / "weather_hourly.parquet")
    calendar_file = MANUAL / "calendar_verified.csv"
    if not calendar_file.exists():
        calendar_file = MANUAL / "calendar_draft.csv"
    calendar = pd.read_csv(calendar_file, parse_dates=["date"])
    festival_dates = set(calendar.loc[calendar["is_festival"], "date"].dt.date)

    for number, (_, case) in enumerate(review.iterrows(), start=1):
        show_case(number, case, readings, weather, festival_dates)
    print("=" * 78)
    print("Values are PM2.5 in µg/m³, before any cleaning. '--' = no reading.")


if __name__ == "__main__":
    main()
