"""
06_time_and_types.py — fix time zones, types and units so that "the same hour"
means the same hour in every source.

Input:   data/interim/openaq_hours_flat.parquet, data/interim/weather_flat.parquet
Output:  data/interim/readings_typed.parquet      long table: station x ts_ist x parameter
         data/interim/weather_hourly_ist.parquet  one row per IST hour
         outputs/tables/ist_sanity_check.csv      NO2 by IST hour (the "does IST look right?" check)

What we fix, in order (each step writes a cleaning-log row with real counts):
  1. Three timestamp formats -> one: IST, as a plain datetime.
       OpenAQ UTC   "2026-06-30T23:30:00Z"        (ISO 8601, Z = UTC)
       OpenAQ local "2026-07-01T05:00:00+05:30"   (ISO 8601 with an offset)
       Open-Meteo   "2025-10-01T00:00"            (no zone at all; GMT because we asked for it)
  2. Check our own UTC->IST conversion against OpenAQ's local time.
  3. Values to float (anything that is not a number becomes missing, and is counted).
  4. Units: NO2 and CO arrive in ppb; Indian AQI uses ug/m3 (NO2) and mg/m3 (CO).
  5. Duplicate station-hour-parameter rows (e.g. the month-boundary hour).
  6. Align weather hours (which start at :30 IST) to air-quality hours (:00 IST).
  7. Sanity check: traffic NO2 should peak in the morning and evening rush, IST.

Run:  python src/06_time_and_types.py
"""

import pandas as pd

from common import (INTERIM, TABLES, ensure_folders, log_decision,
                    reset_cleaning_log_for_stage)

STAGE = "06_time_and_types"
IST = "Asia/Kolkata"  # UTC+05:30, no daylight saving

# ppb -> concentration at 25 C and 1 atm: ug/m3 = ppb x molecular weight / 24.45
# (24.45 L is the volume of one mole of gas at 25 C, 1 atm.)
MOLECULAR_WEIGHT = {"no2": 46.0055, "co": 28.010}
MOLAR_VOLUME_L = 24.45


# ---------------------------------------------------------------------------
# Air quality
# ---------------------------------------------------------------------------
def fix_openaq_times(df):
    """Steps 1-2: parse both OpenAQ timestamps and check they agree."""
    n = len(df)

    # utc=True tells pandas the "Z" means UTC, giving a time-zone-aware value.
    ts_utc = pd.to_datetime(df["ts_utc_text"], utc=True, errors="coerce")
    bad_utc = int(ts_utc.isna().sum())

    # Our conversion: UTC -> IST.
    ts_ist_aware = ts_utc.dt.tz_convert(IST)

    # OpenAQ's own local string carries "+05:30". Parse it independently,
    # convert to IST, and compare with ours. Any mismatch = a bug in one of them.
    ts_local = pd.to_datetime(df["ts_local_text"], utc=True, errors="coerce").dt.tz_convert(IST)
    mismatches = int((ts_local != ts_ist_aware).sum())

    log_decision(STAGE, "OpenAQ timestamps are ISO-8601 text in UTC ('...Z'), plus a second "
                 "local copy with a '+05:30' offset", n,
                 f"Parsed UTC with pd.to_datetime(utc=True) and converted to IST (Asia/Kolkata); "
                 f"{bad_utc} unparseable",
                 "MySQL and our charts need one clock; the commissioner thinks in IST")
    log_decision(STAGE, "Need proof that our UTC->IST conversion is right", mismatches,
                 "Compared our IST with OpenAQ's own '+05:30' local time; rows_affected = mismatches",
                 "An independent check: 0 mismatches means the conversion is correct")

    # Store IST WITHOUT the zone label (MySQL DATETIME has no time zone).
    # The column name ts_ist says which clock it is.
    df["ts_ist"] = ts_ist_aware.dt.tz_localize(None)
    off_the_hour = int((df["ts_ist"].dt.minute != 0).sum())
    log_decision(STAGE, "OpenAQ hours start at :30 UTC, i.e. on the hour in IST", off_the_hour,
                 "Checked every ts_ist falls on :00 IST; rows_affected = rows that do not",
                 "Confirms each reading is the average for the IST hour starting at ts_ist")
    return df.drop(columns=["ts_utc_text", "ts_local_text"])


def fix_openaq_values(df):
    """Step 3: values to float, counting anything that is not a number."""
    before_missing = int(df["value"].isna().sum())
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    newly_missing = int(df["value"].isna().sum()) - before_missing
    log_decision(STAGE, "Values must be numbers; text values would break averages", newly_missing,
                 "pd.to_numeric(errors='coerce') then float64; rows_affected = text values turned missing",
                 f"OpenAQ JSON already sends numbers ({before_missing} were null on arrival); "
                 "the cast guards against text from CPCB files if we add them")
    for col in ["expected_count", "observed_count"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


def standardise_units(df):
    """Step 4: NO2 ppb -> ug/m3, CO ppb -> mg/m3. PM is already ug/m3."""
    for parameter, target_unit, scale in [("no2", "µg/m³", 1.0), ("co", "mg/m³", 0.001)]:
        rows = (df["parameter"] == parameter) & (df["unit"] == "ppb")
        factor = MOLECULAR_WEIGHT[parameter] / MOLAR_VOLUME_L * scale
        df.loc[rows, "value"] = df.loc[rows, "value"] * factor
        df.loc[rows, "unit"] = target_unit
        log_decision(STAGE, f"{parameter.upper()} arrives in ppb, but Indian AQI breakpoints use "
                     f"{target_unit}", int(rows.sum()),
                     f"Converted: value x {factor:.5f} (MW {MOLECULAR_WEIGHT[parameter]} / 24.45"
                     f"{' / 1000' if scale != 1 else ''}, at 25 C, 1 atm)",
                     "Same units as the CPCB AQI table; 25 C/1 atm is the standard reference condition")

    leftover = df.groupby(["parameter", "unit"]).size()
    print("Units after standardising:\n" + leftover.to_string())
    return df


def drop_duplicates(df):
    """Step 5: one row per station x parameter x IST hour."""
    key = ["station_id", "parameter", "ts_ist"]
    dup = df.duplicated(key, keep=False)
    n_dup_rows = int(df.duplicated(key, keep="first").sum())
    # If two rows disagree, keep the one built from more 15-minute readings.
    df = (df.sort_values(key + ["observed_count"], ascending=[True, True, True, False])
            .drop_duplicates(key, keep="first"))
    log_decision(STAGE, "Same station, parameter and IST hour appears more than once "
                 f"({int(dup.sum())} rows involved; month-boundary hours or overlapping sensor ids)",
                 n_dup_rows, "Kept one row per key, preferring the higher observed_count",
                 "A duplicate would count that hour twice in every average")
    return df


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
def fix_weather(w):
    """
    Steps 1 and 6 for weather.

    Open-Meteo time "2025-10-01T00:00" has no zone; it is GMT because we asked
    for timezone=GMT. In IST that is 05:30, so weather hours sit half an hour off
    the air-quality hours (05:00, 06:00, ...). How we line them up:

      * Instantaneous variables (temperature, humidity, wind, boundary layer)
        are values AT the labelled time. The middle of the IST hour 05:00-06:00
        is 05:30, which is exactly a weather label. So we use the value at
        label = IST hour + 30 min.
      * Rain and precipitation are totals for the hour BEFORE the label.
        Label 05:30 IST covers 04:30-05:30; label 06:30 covers 05:30-06:30.
        The IST hour 05:00-06:00 takes half of each:
            rain(05:00 IST) = 0.5 x rain(label 05:30) + 0.5 x rain(label 06:30)
        (This assumes rain falls evenly within an hour, which we state as a limit.)
    """
    n = len(w)
    label_utc = pd.to_datetime(w["ts_gmt_text"], errors="coerce").dt.tz_localize("UTC")
    label_ist = label_utc.dt.tz_convert(IST).dt.tz_localize(None)
    log_decision(STAGE, "Open-Meteo times are text with NO zone ('2025-10-01T00:00'); GMT because "
                 "we requested timezone=GMT", n,
                 "Parsed, labelled as UTC (tz_localize), converted to IST (tz_convert)",
                 "Doing the conversion ourselves makes it visible and checkable, not hidden in the API")

    w = w.assign(label_ist=label_ist).sort_values("label_ist").reset_index(drop=True)

    out = pd.DataFrame()
    out["ts_ist"] = w["label_ist"] - pd.Timedelta(minutes=30)  # the IST hour whose middle is the label
    out["temp_c"] = w["temperature_2m"].astype(float)
    out["rh_pct"] = w["relative_humidity_2m"].astype(float)
    out["wind_kmh"] = w["wind_speed_10m"].astype(float)
    out["blh_m"] = w["boundary_layer_height"].astype(float)
    # Accumulations: half of this label + half of the next label.
    for src, dst in [("precipitation", "precip_mm"), ("rain", "rain_mm")]:
        values = w[src].astype(float)
        out[dst] = 0.5 * values + 0.5 * values.shift(-1)

    lost = int(out["rain_mm"].isna().sum())
    log_decision(STAGE, "Weather hours start at :30 IST; air-quality hours start at :00 IST", len(out),
                 "Instantaneous vars: value at the half-hour label (= middle of the IST hour). "
                 f"Rain: average of the two overlapping hourly totals x 2 halves; {lost} edge hour(s) "
                 "left missing",
                 "Joining on the raw labels would match every air reading with weather 30 minutes off")

    # A "rain hour" = at least 0.1 mm, the smallest amount a standard gauge records.
    out["is_rain_hour"] = out["precip_mm"] >= 0.1
    log_decision(STAGE, "Need a yes/no rain flag per hour", int(out["is_rain_hour"].sum()),
                 "is_rain_hour = precip_mm >= 0.1; rows_affected = rain hours",
                 "0.1 mm is the smallest measurable rainfall on a standard rain gauge")
    return out


# ---------------------------------------------------------------------------
# Step 7: does the IST clock look right?
# ---------------------------------------------------------------------------
def ist_sanity_check(readings):
    """
    Vehicle exhaust drives NO2, so city-wide NO2 should peak in the morning and
    evening rush hours IN IST. If we had shifted the clock by 5.5 hours, the
    peaks would land at implausible times (e.g. 03:00).
    """
    no2 = readings[readings["parameter"] == "no2"]
    by_hour = no2.groupby(no2["ts_ist"].dt.hour)["value"].mean().round(1)
    by_hour.index.name = "hour_ist"
    by_hour.to_frame("mean_no2_ugm3").to_csv(TABLES / "ist_sanity_check.csv")

    morning_peak = int(by_hour.loc[5:12].idxmax())
    evening_peak = int(by_hour.loc[16:23].idxmax())
    print(f"NO2 by IST hour: morning peak at {morning_peak}:00, evening peak at {evening_peak}:00")
    log_decision(STAGE, "Sanity check of the IST conversion", len(no2),
                 f"Mean NO2 by IST hour peaks at {morning_peak}:00 (morning) and {evening_peak}:00 "
                 "(evening); saved outputs/tables/ist_sanity_check.csv",
                 "Traffic NO2 should peak in the rush hours; plausible IST peaks support the conversion")


def main():
    ensure_folders()
    reset_cleaning_log_for_stage(STAGE)

    readings = pd.read_parquet(INTERIM / "openaq_hours_flat.parquet")
    print(f"Readings in: {len(readings):,}")
    readings = fix_openaq_times(readings)
    readings = fix_openaq_values(readings)
    readings = standardise_units(readings)
    readings = drop_duplicates(readings)
    readings = readings[["station_id", "sensor_id", "ts_ist", "parameter", "value", "unit",
                         "expected_count", "observed_count", "openaq_has_flags"]]
    readings.to_parquet(INTERIM / "readings_typed.parquet", index=False)
    print(f"Readings out: {len(readings):,}")

    weather = fix_weather(pd.read_parquet(INTERIM / "weather_flat.parquet"))
    weather.to_parquet(INTERIM / "weather_hourly_ist.parquet", index=False)
    print(f"Weather hours: {len(weather):,}  (rain hours: {int(weather['is_rain_hour'].sum()):,})")

    ist_sanity_check(readings)


if __name__ == "__main__":
    main()
