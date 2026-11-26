"""
07_gaps_outliers.py — count the gaps, catch sensor failures, keep real extreme
events, then fill short gaps with stated rules.

Input:   data/interim/readings_typed.parquet, data/interim/weather_hourly_ist.parquet,
         data/manual/calendar_verified.csv (or calendar_draft.csv until M6 is done)
Output:  data/clean/readings_clean.parquet           station x ts_ist x parameter, with qc_flag
         data/clean/weather_hourly.parquet
         data/clean/station_day_completeness.parquet  which evenings are usable for peak timing
         outputs/tables/gaps_per_station.csv
         outputs/tables/outlier_examples.csv          concrete examples of every flag type
         outputs/tables/outlier_review_top10.csv      for manual step M11
         outputs/charts/gap_heatmap_pm25.png          the gap chart

The order matters:
  1. Build a complete hourly grid, so a missing hour becomes a visible empty row.
  2. Count gaps BEFORE touching anything (the honest baseline).
  3. Flag sensor failures and blank them (they become gaps too).
  4. Flag real extreme events and KEEP them.
  5. Fill only short gaps, and mark every filled value.

Run:  python src/07_gaps_outliers.py
"""

import matplotlib

matplotlib.use("Agg")  # draw charts to files, no window needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (save_parquet, CHARTS, CLEAN, DATE_END, DATE_START, INTERIM, MANUAL, TABLES,
                    ensure_folders, log_decision, reset_cleaning_log_for_stage)

STAGE = "07_gaps_outliers"

# ---------------------------------------------------------------------------
# Rules (every number here is explained in the report and QA_PREP.md)
# ---------------------------------------------------------------------------
FFILL_LIMIT_HOURS = 3        # forward-fill at most 3 missing hours in a row
EVENING_HOURS = list(range(17, 24))  # 17:00-23:00 IST: where we look for the evening peak
EVENING_MIN_OBSERVED = 6     # an evening counts for peak timing only if >= 6 of its 7 hours are REAL

# Flat-line: the same value repeated this many hours in a row is a stuck sensor.
# CO is reported with coarse resolution, so honest repeats are more common: longer window.
FLATLINE_HOURS = {"pm25": 6, "pm10": 6, "no2": 6, "co": 12}

# Spike: one hour far above BOTH neighbours, then straight back down.
#   value > SPIKE_RATIO x mean(neighbours)  AND  value - mean(neighbours) > SPIKE_JUMP
SPIKE_RATIO = 5
SPIKE_JUMP = {"pm25": 150, "pm10": 250, "no2": 150, "co": 5}  # ug/m3, CO in mg/m3

# Instrument range. Above this the analyser cannot measure; it is an error code.
MAX_VALID = {"pm25": 1000, "pm10": 1000, "no2": 1000, "co": 50}

# Sentinel codes some loggers write when a sensor fails. NO2 and CO were
# converted from ppb in 06, so we convert back before comparing.
SENTINELS = {999, 9999}
PPB_FACTOR = {"no2": 46.0055 / 24.45, "co": 28.010 / 24.45 / 1000}

# A REAL extreme event: above the station's own 99.5th percentile.
EXTREME_PERCENTILE = 0.995
HEAVY_RAIN_MM = 10.0         # >= 10 mm in one hour: cloudburst-type rain

# Human verdicts from manual step M11. Kept in data/manual/ because this script
# rewrites outputs/tables/ on every run and would otherwise erase them.
VERDICTS_FILE = MANUAL / "outlier_verdicts.csv"
REVIEW_FILE = TABLES / "outlier_review_top10.csv"


def load_calendar():
    """Use the human-verified calendar if it exists; otherwise the draft (and say so)."""
    verified = MANUAL / "calendar_verified.csv"
    if verified.exists():
        return pd.read_csv(verified, parse_dates=["date"]), "verified"
    print("!! calendar_verified.csv not found (M6 pending): using calendar_draft.csv")
    return pd.read_csv(MANUAL / "calendar_draft.csv", parse_dates=["date"]), "draft"


# ---------------------------------------------------------------------------
# 1-2. Complete grid and gap counting
# ---------------------------------------------------------------------------
def complete_grid(readings):
    """
    One row for EVERY station x parameter x hour in the study range.
    Hours the API never sent appear as rows with value = NaN.
    """
    hours = pd.date_range(f"{DATE_START} 00:00", f"{DATE_END} 23:00", freq="h")
    combos = readings[["station_id", "parameter"]].drop_duplicates()
    grid = combos.merge(pd.DataFrame({"ts_ist": hours}), how="cross")
    full = grid.merge(readings, on=["station_id", "parameter", "ts_ist"], how="left")
    full["unit"] = full.groupby("parameter")["unit"].transform(lambda s: s.ffill().bfill())
    return full.sort_values(["station_id", "parameter", "ts_ist"]).reset_index(drop=True)


def longest_missing_run(is_missing):
    """Length of the longest run of True values (consecutive missing hours)."""
    longest = current = 0
    for missing in is_missing:
        current = current + 1 if missing else 0
        longest = max(longest, current)
    return longest


def count_gaps(full):
    rows = []
    for (station, parameter), g in full.groupby(["station_id", "parameter"]):
        missing = g["value"].isna()
        rows.append({
            "station_id": station,
            "parameter": parameter,
            "hours_expected": len(g),
            "hours_missing": int(missing.sum()),
            "pct_missing": round(100 * missing.mean(), 1),
            "longest_gap_hours": longest_missing_run(missing.tolist()),
        })
    gaps = pd.DataFrame(rows)
    gaps.to_csv(TABLES / "gaps_per_station.csv", index=False)

    pm = gaps[gaps["parameter"] == "pm25"]
    worst = pm.sort_values("longest_gap_hours").iloc[-1]
    log_decision(STAGE, f"Hours the API never sent, after building the full hourly grid "
                 f"({len(full):,} station-parameter-hours)", int(gaps["hours_missing"].sum()),
                 "Counted per station and parameter (outputs/tables/gaps_per_station.csv)",
                 "Gaps must be visible before any rule touches them; silent dropping hides bias")
    log_decision(STAGE, f"Longest PM2.5 gap: {worst['longest_gap_hours']} hours "
                 f"(~{worst['longest_gap_hours'] / 24:.0f} days) at {worst['station_id']}",
                 int(worst["longest_gap_hours"]),
                 "Not filled (far beyond the 3-hour limit); those evenings drop out of peak timing",
                 "Inventing days of data would be fabrication")
    return gaps


def gap_heatmap(full, stations):
    """Station x date heatmap: share of PM2.5 hours present each day."""
    pm = full[full["parameter"] == "pm25"].copy()
    pm["date"] = pm["ts_ist"].dt.date
    daily = pm.groupby(["station_id", "date"])["value"].apply(lambda v: v.notna().mean() * 100)
    table = daily.unstack("date")
    names = stations.set_index("station_id")["name"].str.replace(", Bengaluru", "", regex=False)
    table.index = [names.get(s, s) for s in table.index]

    overall = 100 - pm["value"].isna().mean() * 100
    fig, ax = plt.subplots(figsize=(12, 3.6))
    image = ax.imshow(table.values, aspect="auto", cmap="Greys", vmin=0, vmax=100,
                      interpolation="nearest")
    ax.set_yticks(range(len(table.index)))
    ax.set_yticklabels(table.index, fontsize=8)
    month_starts = [i for i, d in enumerate(table.columns) if d.day == 1]
    ax.set_xticks(month_starts)
    ax.set_xticklabels([table.columns[i].strftime("%b %y") for i in month_starts], fontsize=8)
    ax.set_title(f"PM2.5 was recorded for {overall:.0f}% of station-hours; white stripes are days "
                 "a station sent nothing", fontsize=10, loc="left")
    cbar = fig.colorbar(image, ax=ax, pad=0.01)
    cbar.set_label("% of hours with data", fontsize=8)
    fig.tight_layout()
    fig.savefig(CHARTS / "gap_heatmap_pm25.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 3. Sensor failures
# ---------------------------------------------------------------------------
def flag_failures(full):
    """Set qc_flag for each failure type. Order: the first matching rule wins."""
    full["value_raw"] = full["value"]
    full["qc_flag"] = np.where(full["value"].isna(), "missing", "ok")

    def mark(mask, flag, description, why):
        mask = mask & (full["qc_flag"] == "ok")
        full.loc[mask, "qc_flag"] = flag
        log_decision(STAGE, description, int(mask.sum()),
                     f"qc_flag = '{flag}'; value blanked (treated as a gap)", why)

    # Sentinel codes, compared in the units the logger wrote.
    original = full["value"] / full["parameter"].map(PPB_FACTOR).fillna(1.0)
    mark(original.round(0).isin(SENTINELS), "sentinel",
         "Sensor error codes 999 / 9999", "Loggers write these when the analyser fails; not air")
    mark(full["value"] > full["parameter"].map(MAX_VALID), "out_of_range",
         "Values above the analyser's measuring range", "Physically not measurable; an error code")
    mark(full["value"] < 0, "negative", "Negative concentrations",
         "A concentration cannot be below zero; usually a calibration drift")
    mark(full["value"] == 0, "zero",
         "Exact zero readings", "Bengaluru city air is never exactly zero for these pollutants")

    # Flat-lines: run-length of identical consecutive values within a station-parameter.
    key = ["station_id", "parameter"]
    same_as_before = (full["value"] == full.groupby(key)["value"].shift(1))
    run_id = (~same_as_before).cumsum()
    run_length = full.groupby(run_id)["value"].transform("size")
    limit = full["parameter"].map(FLATLINE_HOURS)
    mark(full["value"].notna() & (run_length >= limit), "flatline",
         "Flat-lines: same value repeated for >= 6 hours (CO >= 12)",
         "A working sensor jitters; an exact repeat for hours means it is stuck")
    return full


def flag_spikes_and_events(full, calendar, weather):
    """
    Single-hour spikes are suspicious UNLESS they happen on a festival night
    (fireworks) or during heavy rain. That is how we separate a sensor glitch
    from Diwali.
    """
    key = ["station_id", "parameter"]
    prev = full.groupby(key)["value"].shift(1)
    nxt = full.groupby(key)["value"].shift(-1)
    neighbours = (prev + nxt) / 2
    jump = full["parameter"].map(SPIKE_JUMP)
    is_spike = (full["value"] > SPIKE_RATIO * neighbours) & (full["value"] - neighbours > jump)

    # Festival nights: the festival date 17:00 to 05:59 next morning.
    festival_dates = set(calendar.loc[calendar["is_festival"], "date"].dt.date)
    shifted_date = (full["ts_ist"] - pd.Timedelta(hours=6)).dt.date  # 02:00 counts as the night before
    on_festival_night = shifted_date.isin(festival_dates) & (
        (full["ts_ist"].dt.hour >= 17) | (full["ts_ist"].dt.hour < 6))

    heavy_rain_hours = set(weather.loc[weather["precip_mm"] >= HEAVY_RAIN_MM, "ts_ist"])
    in_heavy_rain = full["ts_ist"].isin(heavy_rain_hours)

    ok = full["qc_flag"] == "ok"
    spike_failure = is_spike & ok & ~on_festival_night & ~in_heavy_rain
    full.loc[spike_failure, "qc_flag"] = "spike"
    log_decision(STAGE, f"Single-hour spikes (> {SPIKE_RATIO}x both neighbours and a large jump) "
                 "NOT on a festival night or in heavy rain", int(spike_failure.sum()),
                 "qc_flag = 'spike'; value blanked", "Real pollution builds and fades over hours; "
                 "one isolated hour that jumps and drops back is a glitch")

    # Real extremes: above the station's own 99.5th percentile, not a failure.
    threshold = full[full["qc_flag"] == "ok"].groupby(key)["value"].quantile(EXTREME_PERCENTILE)
    full = full.join(threshold.rename("p995"), on=key)
    extreme = (full["qc_flag"] == "ok") & (full["value"] > full["p995"])

    # How many stations are extreme in the same hour? City-wide = real air, not one sensor.
    n_stations_extreme = extreme.groupby([full["parameter"], full["ts_ist"]]).transform("sum")

    full.loc[extreme & on_festival_night, "qc_flag"] = "real_event_festival"
    full.loc[extreme & in_heavy_rain & (full["qc_flag"] == "ok"), "qc_flag"] = "real_event_rain"
    full.loc[extreme & (n_stations_extreme >= 3) & (full["qc_flag"] == "ok"),
             "qc_flag"] = "real_event_citywide"
    full.loc[extreme & (full["qc_flag"] == "ok"), "qc_flag"] = "extreme_unexplained"

    for flag, why in [
        ("real_event_festival", "Fireworks on festival nights (e.g. Deepavali) are real pollution"),
        ("real_event_rain", "Extreme values during >= 10 mm/h rain: real weather, kept for the event study"),
        ("real_event_citywide", ">= 3 stations extreme in the same hour: the air itself, not one sensor"),
        ("extreme_unexplained", "Above the 99.5th percentile, no festival/rain/city-wide match: "
                                "kept but sent to manual review (M11)"),
    ]:
        log_decision(STAGE, f"Extreme values (above each station's 99.5th percentile): {flag}",
                     int((full["qc_flag"] == flag).sum()), f"Kept; qc_flag = '{flag}'", why)

    return full  # keeps the p995 column; apply_human_verdicts needs it


def load_verdicts():
    """
    Read the M11 verdicts. The first time, they may still be only in the review
    table (written by 07b_review_outliers.py --save), so copy them across once.
    """
    if not VERDICTS_FILE.exists() and REVIEW_FILE.exists():
        review = pd.read_csv(REVIEW_FILE)
        done = review[review["human_verdict"].fillna("").str.len() > 0]
        if len(done):
            done[["station_id", "parameter", "ts_ist", "value_raw", "human_verdict"]].to_csv(
                VERDICTS_FILE, index=False)
            print(f"Copied {len(done)} M11 verdicts to {VERDICTS_FILE.name}")
    if VERDICTS_FILE.exists():
        return pd.read_csv(VERDICTS_FILE, parse_dates=["ts_ist"])
    return pd.DataFrame(columns=["station_id", "parameter", "ts_ist", "human_verdict"])


def apply_human_verdicts(full, verdicts):
    """
    Apply each M11 verdict to the whole EPISODE around the reviewed hour:
    the unbroken run of hours at that station where the value stays above the
    station's 95th percentile. One bad morning is one decision, not ten.
    (Why 95th and not 99.5th? A long bad episode pushes the 99.5th percentile up
    into the episode itself, so the run would be cut short.)
    """
    if verdicts.empty:
        print("No M11 verdicts yet")
        return full

    changed = {"sensor_failure": 0, "real_event": 0}
    for _, v in verdicts.iterrows():
        mask = (full["station_id"] == v["station_id"]) & (full["parameter"] == v["parameter"])
        series = full[mask]  # already sorted by time
        hits = series.index[series["ts_ist"] == v["ts_ist"]]
        if len(hits) == 0:
            continue
        positions = list(series.index)
        start = end = positions.index(hits[0])
        p95 = series["value_raw"].quantile(0.95)
        high = series["value_raw"] > p95
        while start > 0 and high.iloc[start - 1]:
            start -= 1
        while end < len(positions) - 1 and high.iloc[end + 1]:
            end += 1
        episode = positions[start:end + 1]

        new_flag = "failure_reviewed" if v["human_verdict"] == "sensor_failure" else "real_event_reviewed"
        newly = full.loc[episode, "qc_flag"] != new_flag
        changed[v["human_verdict"]] += int(newly.sum())
        full.loc[episode, "qc_flag"] = new_flag

    log_decision(STAGE, f"Manual review (M11) of {len(verdicts)} flagged PM2.5 hours: verdict applied "
                 "to the whole high-value episode around each", changed["sensor_failure"],
                 "Episodes judged sensor failures: qc_flag = 'failure_reviewed', value blanked",
                 "A human looked at build-up, other stations, rain and festivals "
                 "(see report/reflection_notes.md)")
    log_decision(STAGE, "Manual review (M11): episodes judged real events", changed["real_event"],
                 "qc_flag = 'real_event_reviewed'; kept",
                 "Real extreme air must stay in the data, or we would understate the worst evenings")
    return full


def save_examples(full, stations):
    """Up to 3 concrete examples of every flag, and the top-10 cases for M11."""
    names = stations.set_index("station_id")["name"]
    flagged = full[~full["qc_flag"].isin(["ok", "missing"])].copy()
    flagged["station_name"] = flagged["station_id"].map(names)
    cols = ["qc_flag", "station_id", "station_name", "parameter", "ts_ist", "value_raw", "unit"]

    examples = (flagged.sort_values("value_raw", ascending=False)
                .groupby("qc_flag").head(3)[cols].sort_values("qc_flag"))
    examples.to_csv(TABLES / "outlier_examples.csv", index=False)

    # M11: the 10 most extreme PM2.5 cases a human should look at,
    # unexplained ones first, then the biggest spikes.
    # Cases already decided in M11 are left out, so this list shows what is still unreviewed.
    review = flagged[(flagged["parameter"] == "pm25") &
                     ~flagged["qc_flag"].str.endswith("_reviewed")].copy()
    review["priority"] = review["qc_flag"].map(
        {"extreme_unexplained": 0, "spike": 1, "real_event_citywide": 2}).fillna(3)
    review = review.sort_values(["priority", "value_raw"], ascending=[True, False]).head(10)
    review["human_verdict"] = ""  # M11: write "sensor_failure" or "real_event"
    review[cols + ["human_verdict"]].to_csv(REVIEW_FILE, index=False)


# ---------------------------------------------------------------------------
# 5. Fill rules
# ---------------------------------------------------------------------------
def fill_gaps(full):
    """
    Blank failures, then forward-fill at most 3 hours.
    Why forward-fill and not interpolate for pollution? Interpolation draws a
    straight line between neighbours and can invent a peak shape; forward-fill
    only repeats the last real value, and we stop after 3 hours. Every filled
    value is marked is_filled = True, and peak timing ignores evenings that
    are not mostly real data anyway.
    """
    failures = ["sentinel", "out_of_range", "negative", "zero", "flatline", "spike", "failure_reviewed"]
    full.loc[full["qc_flag"].isin(failures), "value"] = np.nan

    before = full["value"].isna()
    full["value"] = full.groupby(["station_id", "parameter"])["value"].ffill(limit=FFILL_LIMIT_HOURS)
    full["is_filled"] = before & full["value"].notna()
    log_decision(STAGE, "Short gaps (<= 3 consecutive hours) in pollutant series",
                 int(full["is_filled"].sum()),
                 "Forward-filled, limit 3 hours; is_filled = True on every filled value",
                 "Keeps hourly averages from losing whole hours to brief dropouts, without "
                 "inventing long stretches")
    still_missing = int(full["value"].isna().sum())
    log_decision(STAGE, "Gaps longer than 3 hours", still_missing,
                 "Left missing (not filled)", "Beyond 3 hours we would be guessing")
    return full


def evening_completeness(full):
    """
    Which station-evenings are good enough to time the PM2.5 peak?
    Rule: at least 6 of the 7 evening hours (17:00-23:00) must be REAL readings
    (not missing, not filled, not a failure).
    """
    pm = full[(full["parameter"] == "pm25") & full["ts_ist"].dt.hour.isin(EVENING_HOURS)].copy()
    pm["date"] = pm["ts_ist"].dt.date
    pm["is_real"] = pm["value"].notna() & ~pm["is_filled"]
    days = pm.groupby(["station_id", "date"])["is_real"].sum().reset_index(name="evening_real_hours")
    days["evening_usable"] = days["evening_real_hours"] >= EVENING_MIN_OBSERVED

    dropped = int((~days["evening_usable"]).sum())
    log_decision(STAGE, f"Station-evenings with fewer than {EVENING_MIN_OBSERVED} of 7 real PM2.5 hours "
                 f"(out of {len(days):,} station-evenings)", dropped,
                 "Excluded from peak-timing analysis (evening_usable = False); kept for averages",
                 "With 2+ evening hours missing we cannot tell WHEN the peak happened")
    save_parquet(days, CLEAN / "station_day_completeness.parquet")
    return days


def clean_weather(weather):
    """Weather: interpolate smooth variables over short gaps; never invent rain."""
    smooth = ["temp_c", "rh_pct", "wind_kmh", "blh_m"]
    missing_before = int(weather[smooth].isna().sum().sum())
    weather[smooth] = weather[smooth].interpolate(limit=FFILL_LIMIT_HOURS, limit_area="inside")
    filled = missing_before - int(weather[smooth].isna().sum().sum())
    log_decision(STAGE, "Missing hours in smooth weather variables (temperature, humidity, wind, "
                 "boundary layer)", filled, "Linear interpolation, at most 3 hours",
                 "These change smoothly hour to hour, so a straight line is a fair estimate")
    log_decision(STAGE, "Missing rain hours", int(weather["rain_mm"].isna().sum()),
                 "Not filled", "Rain starts and stops suddenly; interpolating would invent showers")
    save_parquet(weather, CLEAN / "weather_hourly.parquet")
    return weather


def main():
    ensure_folders()
    reset_cleaning_log_for_stage(STAGE)

    readings = pd.read_parquet(INTERIM / "readings_typed.parquet")
    weather = pd.read_parquet(INTERIM / "weather_hourly_ist.parquet")
    stations = pd.read_csv(INTERIM / "stations.csv")
    calendar, calendar_status = load_calendar()
    print(f"Calendar: {calendar_status}")

    full = complete_grid(readings)
    print(f"Full grid: {len(full):,} rows ({len(readings):,} with data)")
    count_gaps(full)
    gap_heatmap(full, stations)

    full = flag_failures(full)
    full = flag_spikes_and_events(full, calendar, weather)
    full = apply_human_verdicts(full, load_verdicts())
    full = full.drop(columns=["p995"])
    save_examples(full, stations)
    print("\nqc_flag counts:\n" + full["qc_flag"].value_counts().to_string())

    full = fill_gaps(full)
    evening_completeness(full)
    clean_weather(weather)

    keep = ["station_id", "ts_ist", "parameter", "value", "value_raw", "unit", "qc_flag",
            "is_filled", "observed_count"]
    save_parquet(full[keep], CLEAN / "readings_clean.parquet")
    full[keep].head(5000).to_csv(CLEAN / "readings_clean_sample.csv", index=False)
    print(f"\nreadings_clean: {len(full):,} rows -> data/clean/readings_clean.parquet")


if __name__ == "__main__":
    main()
