"""
10_analysis.py — answer the question with numbers.

  "Does rain delay, flatten or worsen Bengaluru's evening PM2.5 peak, and on
   which weekdays and months is the evening pollution rush worst?"

Input:   data/clean/readings_clean.parquet, data/clean/weather_hourly.parquet,
         data/clean/station_day_completeness.parquet, the calendar
Output:  outputs/tables/analysis_summary.json        every number the report and chart titles use
         outputs/tables/evening_peaks.csv            one row per usable station-evening
         outputs/tables/rain_effect_by_stratum.csv   rainy vs dry inside each month x day-type
         outputs/tables/rain_effect_regression.txt   the fixed-effects regression, in full
         outputs/tables/evening_by_weekday.csv / evening_by_month.csv
         outputs/tables/aqi_category_evening.csv     hourly AQI-category indicator (ORDINAL)
         outputs/tables/pm25_z_by_hour_rain.csv      normalised (z-score) curves, rainy vs dry
         outputs/tables/event_study_diwali.csv / event_study_heaviest_rain.csv
         outputs/tables/pivot_hour_weekday_pandas.csv
         data/manual/spreadsheet_export_city_hourly.csv   for manual step M10 (<= 50k rows)

Definitions (stated once, used everywhere):
  evening        17:00-23:00 IST
  evening peak   the hour with the highest REAL PM2.5 reading in that window;
                 peak height = that reading. Only "usable" evenings (>= 6 of 7 real hours).
  edge peak      the maximum is at 17:00 or 23:00, i.e. on the window's edge: the level
                 was still falling from the afternoon, or still rising at night.
  rainy evening  >= 1.0 mm of rain between 16:00 and 21:59 (rain before or during the rush)
  dry evening    < 0.1 mm between 12:00 and 23:59 (no rain all afternoon and evening)
                 Evenings in between (a little rain, or rain only late) are left out.

Run:  python src/10_analysis.py
"""

import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from common import CLEAN, MANUAL, TABLES, ensure_folders

EVENING = list(range(17, 24))
RAINY_MM, DRY_MM = 1.0, 0.1
N_BOOT = 1000
RNG = np.random.default_rng(42)  # fixed seed: the same confidence intervals on every run

# CPCB AQI breakpoints for PM2.5 (µg/m³). The official AQI uses a 24-HOUR average;
# we apply the same bands to HOURLY values as an indicator, and say so.
AQI_BINS = [-0.1, 30, 60, 90, 120, 250, np.inf]
AQI_LABELS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def load_calendar():
    path = MANUAL / "calendar_verified.csv"
    if not path.exists():
        path = MANUAL / "calendar_draft.csv"
    cal = pd.read_csv(path, parse_dates=["date"])
    cal["date"] = cal["date"].dt.date
    return cal


def load_pm25():
    """PM2.5 station-hours with weather and calendar attached."""
    r = pd.read_parquet(CLEAN / "readings_clean.parquet")
    pm = r[r["parameter"] == "pm25"].copy()
    pm["is_real"] = pm["value"].notna() & ~pm["is_filled"]
    pm["date"] = pm["ts_ist"].dt.date
    pm["hour"] = pm["ts_ist"].dt.hour
    pm["weekday"] = pd.Categorical(pm["ts_ist"].dt.day_name(), categories=WEEKDAYS, ordered=True)
    pm["month"] = pm["ts_ist"].dt.to_period("M").astype(str)
    weather = pd.read_parquet(CLEAN / "weather_hourly.parquet")
    pm = pm.merge(weather, on="ts_ist", how="left")
    pm = pm.merge(load_calendar()[["date", "is_holiday", "is_festival", "season"]], on="date", how="left")
    return pm, weather


# ---------------------------------------------------------------------------
# Normalisation and the AQI category
# ---------------------------------------------------------------------------
def add_zscores(pm):
    """
    z = (value - station mean) / station standard deviation.
    Why per station? Silk Board (traffic junction) runs dirtier than Hebbal all
    the time. A z-score asks "how unusual is this hour FOR THIS STATION", so
    stations with different baselines can share one chart.
    """
    stats = pm.groupby("station_id")["value"].agg(["mean", "std"])
    pm = pm.join(stats, on="station_id")
    pm["pm25_z"] = (pm["value"] - pm["mean"]) / pm["std"]
    return pm.drop(columns=["mean", "std"])


def aqi_category_table(pm):
    """Share of evening station-hours in each AQI band. The category is ORDINAL."""
    ev = pm[pm["hour"].isin(EVENING) & pm["value"].notna()].copy()
    ev["aqi_category"] = pd.cut(ev["value"], AQI_BINS, labels=AQI_LABELS, ordered=True)
    table = (ev.groupby("aqi_category", observed=False).size().rename("station_hours").reset_index())
    table["pct"] = (100 * table["station_hours"] / table["station_hours"].sum()).round(1)
    table.to_csv(TABLES / "aqi_category_evening.csv", index=False)
    return table


# ---------------------------------------------------------------------------
# Evening peaks
# ---------------------------------------------------------------------------
def classify_evenings(weather):
    """Label each DATE as rainy, dry or other, from city-wide weather."""
    w = weather.copy()
    w["date"] = w["ts_ist"].dt.date
    w["hour"] = w["ts_ist"].dt.hour
    rain_1622 = w[w["hour"].between(16, 21)].groupby("date")["precip_mm"].sum()
    rain_1224 = w[w["hour"].between(12, 23)].groupby("date")["precip_mm"].sum()
    days = pd.DataFrame({"rain_16_22_mm": rain_1622, "rain_12_24_mm": rain_1224})
    days["evening_type"] = np.select(
        [days["rain_16_22_mm"] >= RAINY_MM, days["rain_12_24_mm"] < DRY_MM],
        ["rainy", "dry"], default="other")
    return days.reset_index()


def evening_peaks(pm, weather):
    """One row per usable station-evening: peak hour, peak height, rain type."""
    usable = pd.read_parquet(CLEAN / "station_day_completeness.parquet")
    usable = usable[usable["evening_usable"]][["station_id", "date"]]

    ev = pm[pm["hour"].isin(EVENING) & pm["is_real"]]
    ev = ev.merge(usable, on=["station_id", "date"])
    idx = ev.groupby(["station_id", "date"])["value"].idxmax()
    peaks = ev.loc[idx, ["station_id", "date", "hour", "value", "weekday", "month",
                         "is_holiday", "is_festival", "season"]]
    peaks = peaks.rename(columns={"hour": "peak_hour", "value": "peak_height"})
    means = ev.groupby(["station_id", "date"])["value"].mean().rename("evening_mean").reset_index()
    peaks = peaks.merge(means, on=["station_id", "date"])
    peaks["edge_peak"] = peaks["peak_hour"].isin([17, 23])
    peaks["day_type"] = np.where(peaks["is_holiday"] == True, "holiday_or_weekend", "working_day")  # noqa: E712
    peaks = peaks.merge(classify_evenings(weather), on="date", how="left")
    peaks.to_csv(TABLES / "evening_peaks.csv", index=False)
    return peaks


# ---------------------------------------------------------------------------
# Rain effect, with season and weekday held constant
# ---------------------------------------------------------------------------
def stratified_difference(df):
    """
    Compare rainy and dry evenings INSIDE each month x day-type stratum, then
    average the differences, weighting each stratum by its number of rainy
    evenings. Strata without both kinds of evening cannot be compared and drop out.
    Returns (shift in peak hour, % change in peak height, % change in evening mean).
    """
    g = df.groupby(["month", "day_type", "evening_type"])[["peak_hour", "peak_height", "evening_mean"]]
    means = g.mean().unstack("evening_type")
    counts = df.groupby(["month", "day_type", "evening_type"]).size().unstack("evening_type")
    ok = counts.reindex(columns=["rainy", "dry"]).notna().all(axis=1)
    if ok.sum() == 0:
        return np.nan, np.nan, np.nan, 0
    m, w = means[ok], counts.loc[ok, "rainy"]
    shift = np.average(m[("peak_hour", "rainy")] - m[("peak_hour", "dry")], weights=w)
    height = (np.average(m[("peak_height", "rainy")], weights=w) /
              np.average(m[("peak_height", "dry")], weights=w) - 1) * 100
    level = (np.average(m[("evening_mean", "rainy")], weights=w) /
             np.average(m[("evening_mean", "dry")], weights=w) - 1) * 100
    return shift, height, level, int(ok.sum())


def rain_effect(peaks):
    comp = peaks[peaks["evening_type"].isin(["rainy", "dry"])].copy()
    shift, height, level, n_strata = stratified_difference(comp)

    # Bootstrap by DATE: all stations share one day's weather, so their evenings
    # are not independent. Resampling whole dates keeps that honest.
    dates = comp["date"].unique()
    by_date = {d: g for d, g in comp.groupby("date")}
    boot = []
    for _ in range(N_BOOT):
        sample = RNG.choice(dates, size=len(dates), replace=True)
        boot.append(stratified_difference(pd.concat([by_date[d] for d in sample]))[:3])
    boot = np.array(boot, dtype=float)
    ci = np.nanpercentile(boot, [2.5, 97.5], axis=0)

    # Per-stratum table for the appendix.
    strat = (comp.groupby(["month", "day_type", "evening_type"])
             .agg(n=("peak_height", "size"), mean_peak_hour=("peak_hour", "mean"),
                  mean_peak_height=("peak_height", "mean"))
             .round(2).reset_index())
    strat.to_csv(TABLES / "rain_effect_by_stratum.csv", index=False)

    # Cross-check with a regression: month, day type and station fixed effects.
    comp["rainy"] = (comp["evening_type"] == "rainy").astype(int)
    comp["log_peak"] = np.log(comp["peak_height"])
    fit_h = smf.ols("log_peak ~ rainy + C(month) + C(day_type) + C(station_id)", data=comp).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(comp["date"])[0]})
    fit_t = smf.ols("peak_hour ~ rainy + C(month) + C(day_type) + C(station_id)", data=comp).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(comp["date"])[0]})
    (TABLES / "rain_effect_regression.txt").write_text(
        "PEAK HEIGHT (log)\n" + str(fit_h.summary()) + "\n\nPEAK HOUR\n" + str(fit_t.summary()))

    reg_pct = (np.exp(fit_h.params["rainy"]) - 1) * 100
    reg_ci = (np.exp(fit_h.conf_int().loc["rainy"]) - 1) * 100

    edge = comp.groupby("evening_type")["edge_peak"].mean() * 100
    late = comp.groupby("evening_type")["peak_hour"].apply(lambda h: (h >= 21).mean() * 100)
    return {
        "n_rainy_evenings": int((comp["evening_type"] == "rainy").sum()),
        "n_dry_evenings": int((comp["evening_type"] == "dry").sum()),
        "n_rainy_dates": int(comp.loc[comp["evening_type"] == "rainy", "date"].nunique()),
        "n_strata_compared": n_strata,
        "peak_hour_shift_h": round(shift, 2),
        "peak_hour_shift_ci": [round(x, 2) for x in ci[:, 0]],
        "peak_height_change_pct": round(height, 1),
        "peak_height_change_ci": [round(x, 1) for x in ci[:, 1]],
        "evening_mean_change_pct": round(level, 1),
        "evening_mean_change_ci": [round(x, 1) for x in ci[:, 2]],
        "regression_peak_height_pct": round(reg_pct, 1),
        "regression_peak_height_ci": [round(x, 1) for x in reg_ci],
        "regression_peak_hour_shift_h": round(fit_t.params["rainy"], 2),
        "regression_peak_hour_ci": [round(x, 2) for x in fit_t.conf_int().loc["rainy"]],
        "pct_edge_peaks": {k: round(v, 1) for k, v in edge.items()},
        "pct_peaks_at_or_after_21h": {k: round(v, 1) for k, v in late.items()},
    }


# ---------------------------------------------------------------------------
# Which weekdays and months are worst?
# ---------------------------------------------------------------------------
def worst_weekdays_months(pm, peaks):
    ev = pm[pm["hour"].isin(EVENING) & pm["value"].notna()]
    by_wd = (ev.groupby("weekday", observed=True)["value"].agg(["mean", "size"])
             .rename(columns={"mean": "mean_evening_pm25", "size": "n_station_hours"}).round(1))
    by_wd["mean_peak_height"] = peaks.groupby("weekday", observed=True)["peak_height"].mean().round(1)
    by_wd.to_csv(TABLES / "evening_by_weekday.csv")

    by_m = (ev.groupby("month")["value"].agg(["mean", "size"])
            .rename(columns={"mean": "mean_evening_pm25", "size": "n_station_hours"}).round(1))
    by_m["typical_peak_hour"] = peaks.groupby("month")["peak_hour"].median()
    by_m.to_csv(TABLES / "evening_by_month.csv")

    wd_sorted = by_wd["mean_evening_pm25"].sort_values(ascending=False)
    m_sorted = by_m["mean_evening_pm25"].sort_values(ascending=False)
    return {
        "worst_weekday": wd_sorted.index[0], "worst_weekday_pm25": float(wd_sorted.iloc[0]),
        "best_weekday": wd_sorted.index[-1], "best_weekday_pm25": float(wd_sorted.iloc[-1]),
        "worst_months": list(m_sorted.index[:3]), "worst_months_pm25": [float(x) for x in m_sorted.iloc[:3]],
        "best_months": list(m_sorted.index[-3:]), "best_months_pm25": [float(x) for x in m_sorted.iloc[-3:]],
    }


def peak_timing(peaks):
    """When does the peak happen? Overall, and how often it is a real evening peak."""
    interior = peaks[~peaks["edge_peak"]]
    counts = peaks["peak_hour"].value_counts().sort_index()
    return {
        "n_usable_evenings": int(len(peaks)),
        "peak_hour_counts": {int(k): int(v) for k, v in counts.items()},
        "pct_edge_peaks_all": round(peaks["edge_peak"].mean() * 100, 1),
        "interior_peak_median_hour": float(interior["peak_hour"].median()),
        "interior_peak_iqr": [float(interior["peak_hour"].quantile(q)) for q in (0.25, 0.75)],
        "pct_peaks_19_to_22": round(peaks["peak_hour"].between(19, 22).mean() * 100, 1),
    }


# ---------------------------------------------------------------------------
# Normalised curves, event studies, the pandas pivot and the spreadsheet export
# ---------------------------------------------------------------------------
def z_curves(pm, peaks):
    """Mean z-score by hour on rainy vs dry evenings (dates as classified above)."""
    types = peaks[["date", "evening_type"]].drop_duplicates()
    z = pm[pm["value"].notna()].merge(types, on="date")
    z = z[z["evening_type"].isin(["rainy", "dry"]) & z["hour"].between(12, 23)]
    table = z.groupby(["evening_type", "hour"])["pm25_z"].agg(["mean", "size"]).round(3).reset_index()
    table.to_csv(TABLES / "pm25_z_by_hour_rain.csv", index=False)
    return table


def matched_event(pm, event_dates, label, calendar):
    """
    City-mean PM2.5 by hour on the event day(s) vs matched normal days:
    same weekday, same month, not a festival, not the event itself.
    """
    city = pm[pm["value"].notna()].groupby(["date", "hour"])["value"].mean().reset_index()
    festival = set(calendar.loc[calendar["is_festival"] == True, "date"])  # noqa: E712
    rows, matched_all = [], []
    for d in event_dates:
        d = pd.Timestamp(d)
        same = [x for x in city["date"].unique()
                if pd.Timestamp(x).weekday() == d.weekday() and pd.Timestamp(x).month == d.month
                and x != d.date() and x not in festival]
        matched_all += same
        rows.append(city[city["date"] == d.date()].assign(kind=label))
    matched = city[city["date"].isin(matched_all)].groupby("hour")["value"].mean().reset_index()
    matched["kind"] = "matched normal days"
    out = pd.concat(rows + [matched], ignore_index=True)
    return out, len(set(matched_all))


def event_studies(pm, weather, calendar):
    results = {}
    diwali_2025 = ["2025-10-20", "2025-10-21", "2025-10-22"]
    d, n = matched_event(pm, diwali_2025[:1], "Deepavali night (20 Oct 2025)", calendar)
    d.to_csv(TABLES / "event_study_diwali.csv", index=False)
    ev = d[d["kind"] != "matched normal days"]
    base = d[d["kind"] == "matched normal days"]
    late = lambda t: t[t["hour"].between(19, 23)]["value"].mean()  # noqa: E731
    results["diwali_19_23_mean"] = round(late(ev), 1)
    results["diwali_matched_19_23_mean"] = round(late(base), 1)
    results["diwali_n_matched_days"] = n

    daily_rain = weather.groupby(weather["ts_ist"].dt.date)["precip_mm"].sum()
    wettest = daily_rain.idxmax()
    d, n = matched_event(pm, [str(wettest)], f"Wettest day ({wettest}, {daily_rain.max():.0f} mm)", calendar)
    d.to_csv(TABLES / "event_study_heaviest_rain.csv", index=False)
    ev = d[d["kind"] != "matched normal days"]
    base = d[d["kind"] == "matched normal days"]
    results["wettest_day"] = str(wettest)
    results["wettest_day_mm"] = round(float(daily_rain.max()), 1)
    results["wettest_17_23_mean"] = round(ev[ev["hour"].isin(EVENING)]["value"].mean(), 1)
    results["wettest_matched_17_23_mean"] = round(base[base["hour"].isin(EVENING)]["value"].mean(), 1)
    results["wettest_n_matched_days"] = n
    return results


def pivot_and_export(pm):
    """
    City-average PM2.5 per hour (mean over the stations reporting that hour).
    1. Export it for the spreadsheet step (M10): ~10,000 rows, under the 50k limit.
    2. Build the SAME hour x weekday pivot in pandas, from the same file, so the
       two can be compared number by number.
    """
    city = (pm[pm["value"].notna()].groupby("ts_ist")["value"].mean().round(2)
            .rename("pm25_city_mean").reset_index())
    city["date"] = city["ts_ist"].dt.date
    city["weekday"] = city["ts_ist"].dt.day_name()
    city["hour"] = city["ts_ist"].dt.hour
    city[["date", "weekday", "hour", "pm25_city_mean"]].to_csv(
        MANUAL / "spreadsheet_export_city_hourly.csv", index=False)

    pivot = city.pivot_table(index="hour", columns="weekday", values="pm25_city_mean", aggfunc="mean")
    pivot = pivot[WEEKDAYS].round(2)
    pivot.to_csv(TABLES / "pivot_hour_weekday_pandas.csv")
    return len(city)


def main():
    ensure_folders()
    calendar = load_calendar()
    pm, weather = load_pm25()
    pm = add_zscores(pm)

    summary = {"generated_by": "src/10_analysis.py"}
    summary["aqi_evening"] = aqi_category_table(pm).set_index("aqi_category")["pct"].to_dict()
    peaks = evening_peaks(pm, weather)
    summary["peak_timing"] = peak_timing(peaks)
    summary["rain_effect"] = rain_effect(peaks)
    summary["worst"] = worst_weekdays_months(pm, peaks)
    z_curves(pm, peaks)
    summary["events"] = event_studies(pm, weather, calendar)
    summary["spreadsheet_export_rows"] = pivot_and_export(pm)

    (TABLES / "analysis_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
