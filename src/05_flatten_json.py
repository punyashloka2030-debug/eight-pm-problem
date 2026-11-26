"""
05_flatten_json.py — turn the nested JSON we downloaded into flat tables.

Input:   data/interim/openaq_manifest.csv  + the raw files it points to
         data/interim/openmeteo_manifest.csv + its raw file
Output:  data/interim/openaq_hours_flat.parquet   one row per sensor-hour
         data/interim/weather_flat.parquet        one row per hour
         data/interim/*_sample.csv                first 1,000 rows, easy to open
         outputs/tables/json_flatten_example.md   before/after example for the report

The two APIs send two different JSON SHAPES (that is the "variety" V):
  OpenAQ     = a list of records, each with nested objects inside
               (parameter{...}, period{datetimeFrom{utc, local}}, coverage{...}).
               pd.json_normalize turns nested keys into dotted column names,
               e.g. period -> datetimeFrom -> utc becomes "period.datetimeFrom.utc".
  Open-Meteo = one object holding parallel ARRAYS (time[], rain[], ...).
               Each array becomes one column; position i in every array is hour i.

We do NOT fix types or time zones here: timestamps stay as the text the API sent.
That is 06_time_and_types.py's job, so each step can be explained on its own.

Run:  python src/05_flatten_json.py
"""

import json

import pandas as pd

from common import (INTERIM, ROOT, TABLES, ensure_folders, log_decision,
                    reset_cleaning_log_for_stage)

STAGE = "05_flatten_json"

# Which flattened OpenAQ columns we keep, and the short names we give them.
# Everything else (summary quantiles etc.) is dropped to keep the table light;
# the raw files still have it if we ever need it.
OPENAQ_KEEP = {
    "value": "value",
    "parameter.name": "parameter",
    "parameter.units": "unit",
    "period.datetimeFrom.utc": "ts_utc_text",
    "period.datetimeFrom.local": "ts_local_text",
    "coverage.expectedCount": "expected_count",
    "coverage.observedCount": "observed_count",
    "flagInfo.hasFlags": "openaq_has_flags",
}


def load_body(relative_path):
    """Read one cached raw file and return the API body inside it."""
    with open(ROOT / relative_path, encoding="utf-8") as f:
        return json.load(f)["body"]


def flatten_openaq():
    manifest = pd.read_csv(INTERIM / "openaq_manifest.csv")
    pieces = []
    example_written = False

    # Only files that actually contain rows (empty months have n_results = 0).
    for _, m in manifest[manifest["n_results"] > 0].iterrows():
        results = load_body(m["raw_file"])["results"]

        # THE key line: nested JSON records -> flat DataFrame.
        flat = pd.json_normalize(results)

        # Save one before/after example for the report (section 4, formats).
        if not example_written:
            write_flatten_example(results[0], flat.iloc[[0]])
            example_written = True

        # Keep only the columns we need. If OpenAQ ever drops a field, create
        # it as empty so every piece has the same columns.
        for col in OPENAQ_KEEP:
            if col not in flat.columns:
                flat[col] = None
        flat = flat[list(OPENAQ_KEEP)].rename(columns=OPENAQ_KEEP)

        # Add which station and sensor this file belongs to (not inside the JSON).
        flat["station_id"] = m["station_id"]
        flat["sensor_id"] = m["sensor_id"]
        pieces.append(flat)

    hours = pd.concat(pieces, ignore_index=True)
    n_nested_cols = len(pd.json_normalize(load_body(manifest.loc[manifest["n_results"] > 0,
                                                                   "raw_file"].iloc[0])["results"]).columns)
    log_decision(STAGE, f"OpenAQ hourly records are nested JSON ({n_nested_cols} columns after "
                 "json_normalize: parameter, period, summary, coverage objects)", len(hours),
                 f"Flattened with pd.json_normalize; kept {len(OPENAQ_KEEP)} columns + station/sensor ids",
                 "Tables and SQL need one value per cell; summary quantiles are not used in our question")

    # Units check: record what each pollutant arrived in. CO is the usual problem
    # (CPCB reports mg/m3, other networks ug/m3 or ppm). 06 standardises them.
    units = hours.groupby(["parameter", "unit"]).size().reset_index(name="rows")
    print("Units as received:\n" + units.to_string(index=False))
    units.to_csv(TABLES / "units_as_received.csv", index=False)

    hours.to_parquet(INTERIM / "openaq_hours_flat.parquet", index=False)
    hours.head(1000).to_csv(INTERIM / "openaq_hours_flat_sample.csv", index=False)
    print(f"OpenAQ: {len(hours):,} rows x {hours.shape[1]} columns")
    return hours


def write_flatten_example(record, flat_row):
    """Before (nested JSON) and after (one flat row) for the report appendix."""
    text = ["# JSON flattening example (from 05_flatten_json.py)", "",
            "## Before: one OpenAQ hourly record as received (nested JSON)", "",
            "```json", json.dumps(record, indent=1, ensure_ascii=False), "```", "",
            "## After: the same record as one row (`pd.json_normalize`)", "",
            flat_row.T.rename(columns={flat_row.index[0]: "value"}).to_markdown(), ""]
    (TABLES / "json_flatten_example.md").write_text("\n".join(text), encoding="utf-8")


def flatten_weather():
    manifest = pd.read_csv(INTERIM / "openmeteo_manifest.csv")
    body = load_body(manifest["raw_file"].iloc[0])

    # Parallel arrays -> columns. pd.DataFrame(dict_of_lists) does exactly that.
    weather = pd.DataFrame(body["hourly"])
    weather = weather.rename(columns={"time": "ts_gmt_text"})

    log_decision(STAGE, "Open-Meteo sends parallel arrays (time[], rain[], ...) instead of records",
                 len(weather), "Turned each array into a column with pd.DataFrame",
                 "Different JSON shape from OpenAQ; both must end up as one row per hour")

    weather.to_parquet(INTERIM / "weather_flat.parquet", index=False)
    weather.head(1000).to_csv(INTERIM / "weather_flat_sample.csv", index=False)
    print(f"Weather: {len(weather):,} rows x {weather.shape[1]} columns")
    return weather


def main():
    ensure_folders()
    reset_cleaning_log_for_stage(STAGE)
    flatten_openaq()
    flatten_weather()


if __name__ == "__main__":
    main()
