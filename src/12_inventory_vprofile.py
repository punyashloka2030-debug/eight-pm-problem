"""
12_inventory_vprofile.py — three pieces of Module 1 evidence, built from the
files the pipeline produced (no numbers typed in by hand):

  outputs/tables/data_inventory.csv    every field: table, real example, measurement level,
                                       structure, source. AQI category marked ORDINAL.
  outputs/tables/source_register.csv   URL, access dates, method, terms of use, note
  outputs/tables/v_profile.csv         Volume (rows, MB), Velocity (readings per hour,
                                       data delay), Variety (formats) per source
  report/v_profile.md                  the one-page V profile, written from those numbers

Run:  python src/12_inventory_vprofile.py
"""

from datetime import datetime, timezone

import pandas as pd

from common import CLEAN, INTERIM, MANUAL, RAW, ROOT, SOURCE_LOG, TABLES, ensure_folders

REPORT = ROOT / "report"


def folder_mb(path):
    """Size in MB of one file, or of every file under a folder."""
    if not path.exists():
        return 0.0
    # A single file (e.g. a .parquet or .csv): rglob would find nothing inside it, so size it directly.
    if path.is_file():
        return round(path.stat().st_size / 1e6, 2)
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6, 1)


def first_value(df, column):
    """A real example value from the data (first non-empty one)."""
    values = df[column].dropna()
    values = values[values.astype(str) != ""]
    if not len(values):
        return ""
    value = values.iloc[0]
    return f"{value:.2f}" if isinstance(value, float) else str(value)


# ---------------------------------------------------------------------------
# Data inventory
# ---------------------------------------------------------------------------
def data_inventory():
    stations = pd.read_csv(INTERIM / "stations.csv")
    readings = pd.read_parquet(CLEAN / "readings_clean.parquet").head(50_000)
    weather = pd.read_parquet(CLEAN / "weather_hourly.parquet")
    cal_path = MANUAL / "calendar_verified.csv"
    calendar = pd.read_csv(cal_path if cal_path.exists() else MANUAL / "calendar_draft.csv")
    real_hours = readings[readings["value"].notna()]

    # (field, table, dataframe or fixed example, level, structure, source)
    S, SEMI, U = "structured", "semi-structured", "unstructured"
    OPENAQ, METEO, CAL = "OpenAQ v3 API (JSON)", "Open-Meteo archive API (JSON)", "Karnataka/central holiday lists (CSV we built)"
    rows = [
        ("station_id", "stations", stations, "nominal", S, "our key from OpenAQ location id"),
        ("name", "stations", stations, "nominal", S, OPENAQ),
        ("lat", "stations", stations, "continuous", S, OPENAQ),
        ("lon", "stations", stations, "continuous", S, OPENAQ),
        ("operator", "stations", stations, "nominal", S, OPENAQ),
        ("openaq_location_id", "stations", stations, "nominal (a number used as a label)", S, OPENAQ),
        ("ts_ist", "readings", real_hours, "continuous (interval scale: time)", SEMI + " (nested JSON text)", OPENAQ),
        ("parameter", "readings", real_hours, "nominal", SEMI, OPENAQ),
        ("value", "readings", real_hours, "continuous (ratio)", SEMI, OPENAQ),
        ("unit", "readings", real_hours, "nominal", SEMI, OPENAQ),
        ("qc_flag", "readings", real_hours, "nominal", S, "derived (07_gaps_outliers.py)"),
        ("is_filled", "readings", real_hours, "nominal (binary)", S, "derived (07_gaps_outliers.py)"),
        ("observed_count", "readings", real_hours, "discrete (0-4 quarter-hours)", SEMI, OPENAQ),
        ("ts_ist", "weather_hourly", weather, "continuous (interval scale: time)", SEMI + " (JSON arrays)", METEO),
        ("precip_mm", "weather_hourly", weather, "continuous (ratio)", SEMI, METEO),
        ("rain_mm", "weather_hourly", weather, "continuous (ratio)", SEMI, METEO),
        ("temp_c", "weather_hourly", weather, "continuous (interval)", SEMI, METEO),
        ("rh_pct", "weather_hourly", weather, "continuous (ratio, 0-100)", SEMI, METEO),
        ("wind_kmh", "weather_hourly", weather, "continuous (ratio)", SEMI, METEO),
        ("blh_m", "weather_hourly", weather, "continuous (ratio)", SEMI, METEO),
        ("is_rain_hour", "weather_hourly", weather, "nominal (binary)", S, "derived: precip_mm >= 0.1"),
        ("date", "calendar", calendar, "continuous (interval scale: time)", S, CAL),
        ("weekday", "calendar", calendar, "ordinal (ordered, repeats weekly)", S, CAL),
        ("is_holiday", "calendar", calendar, "nominal (binary)", S, CAL),
        ("holiday_name", "calendar", calendar, "nominal", U + " (free text names)", CAL),
        ("is_long_weekend", "calendar", calendar, "nominal (binary)", S, "derived: 3+ days off in a row"),
        ("is_festival", "calendar", calendar, "nominal (binary)", S, CAL),
        ("season", "calendar", calendar, "nominal (cyclic, no natural first)", S, "derived: IMD seasons by month"),
        ("aqi_category", "analysis", "Moderate", "ORDINAL (Good < Satisfactory < Moderate < Poor < "
         "Very Poor < Severe)", S, "derived: CPCB PM2.5 breakpoints, applied hourly"),
        ("pm25_z", "analysis", "1.84", "continuous (unitless)", S, "derived: z-score within station"),
        ("peak_hour", "analysis", "20", "discrete (17-23)", S, "derived: hour of the evening maximum"),
        ("evening_type", "analysis", "rainy", "nominal (rainy / dry / other)", S, "derived from weather"),
        ("search_interest", "trends", "0-100 index", "discrete (relative index 0-100)",
         S + " export of unstructured search text", "Google Trends (manual CSV, M7)"),
    ]
    table = pd.DataFrame([{
        "field": f, "table": t,
        "example": ex if isinstance(ex, str) else first_value(ex, f),
        "measurement_level": lvl, "structure": st, "source": src,
    } for f, t, ex, lvl, st, src in rows])
    table.to_csv(TABLES / "data_inventory.csv", index=False)
    print(f"data_inventory.csv: {len(table)} fields")


# ---------------------------------------------------------------------------
# Source register
# ---------------------------------------------------------------------------
REGISTER = [
    {"source": "openaq", "name": "OpenAQ v3 API", "url": "https://api.openaq.org/v3",
     "method": "API (JSON), scripts 01/02, key in .env, month windows, cached",
     "terms_url": "https://docs.openaq.org/about/terms",
     "note": "Aggregates CPCB/KSPCB monitors; licence depends on the original provider: credit CPCB/KSPCB and OpenAQ. "
             "Free tier 60 req/min, 2,000 req/h."},
    {"source": "openmeteo", "name": "Open-Meteo Historical Weather API",
     "url": "https://archive-api.open-meteo.com/v1/archive",
     "method": "API (JSON), script 03, timezone=GMT, cached", "terms_url": "https://open-meteo.com/en/terms",
     "note": "CC BY 4.0; free non-commercial use under 10,000 calls/day. One city-centre point."},
    {"source": "calendar",
     "name": "Karnataka general holidays 2025 (DPAR 16 HHL 2024) and 2026 (DPAR 16 HHL 2025) + central list 2026",
     "url": "https://cag.gov.in/uploads/media/Karnataka-State-Holidays-2025-067764409e26023-56493682.pdf ; "
            "https://kea.co.in/wp-content/uploads/2025/11/Circular-No-089-2025-KARNATAKA-GOVERNMENT-HOLIDAYS-FOR-THE-YEAR-2026.pdf ; "
            "https://cag.gov.in/uploads/media/Holiday-List-2026-069521fe6f358d0-89936988.pdf",
     "method": "Typed in by hand (04_build_calendar.py), checked date by date in M6 -> calendar_verified.csv",
     "terms_url": "Government publication",
     "note": ("2026 state notification read from the copy enclosed in KEA Circular 089/2025. M6 check: 2 dates "
              "corrected (Mahavir Jayanti 31 Mar, Valmiki Jayanti 25 Oct 2026); school breaks from news reports "
              "of the DSEL academic calendars.")},
    {"source": "trends", "name": "Google Trends (Karnataka): bangalore traffic / bangalore rain / AQI bangalore",
     "url": "https://trends.google.com/trends/explore", "method": "Manual CSV export (M7); no scraping",
     "terms_url": "https://policies.google.com/terms",
     "note": "Weekly relative index 0-100 for a 14-month range; context only, not hourly."},
]


def source_register():
    log = pd.read_csv(SOURCE_LOG) if SOURCE_LOG.exists() else pd.DataFrame(columns=["source", "accessed_utc", "bytes"])
    rows = []
    for entry in REGISTER:
        sub = log[log["source"] == entry["source"]]
        rows.append({**entry,
                     "first_access_utc": sub["accessed_utc"].min() if len(sub) else "manual",
                     "last_access_utc": sub["accessed_utc"].max() if len(sub) else "manual",
                     "n_api_requests": len(sub),
                     "mb_downloaded": round(sub["bytes"].sum() / 1e6, 1) if len(sub) else 0})
    pd.DataFrame(rows).to_csv(TABLES / "source_register.csv", index=False)
    print("source_register.csv written")


# ---------------------------------------------------------------------------
# V profile
# ---------------------------------------------------------------------------
def v_profile():
    # Use the human-checked calendar once it exists (M6), else the draft.
    cal_path = MANUAL / "calendar_verified.csv"
    calendar = pd.read_csv(cal_path if cal_path.exists() else MANUAL / "calendar_draft.csv")
    stations = pd.read_csv(INTERIM / "stations.csv")
    flat = pd.read_csv(INTERIM / "openaq_locations_flat.csv")
    access = pd.read_csv(SOURCE_LOG) if SOURCE_LOG.exists() else None
    manifest = pd.read_csv(INTERIM / "openaq_manifest.csv")
    readings_rows = int(manifest["n_results"].sum())
    weather_rows = int(pd.read_csv(INTERIM / "openmeteo_manifest.csv")["n_hours"].sum())

    # Velocity 1: how many new readings per hour the network produces for us.
    n_series = manifest[["station_id", "parameter"]].drop_duplicates().shape[0]
    # Velocity 2: how fresh OpenAQ was when we looked (last reading vs our first access).
    approved = flat[flat["openaq_location_id"].isin(stations["openaq_location_id"])]
    last_reading = pd.to_datetime(approved["last_utc"], utc=True).max()
    # Compare with the moment we downloaded the LOCATIONS list, which is where last_utc came from.
    loc_rows = access[(access["source"] == "openaq") & access["url"].str.contains("locations\\?bbox")] \
        if access is not None else pd.DataFrame()
    looked = (pd.to_datetime(loc_rows["accessed_utc"], utc=True, format="ISO8601").max()
              if len(loc_rows) else datetime.now(timezone.utc))
    lag_hours = round((looked - last_reading).total_seconds() / 3600, 1)

    rows = [
        {"source": "OpenAQ hourly readings", "rows": readings_rows, "raw_mb": folder_mb(RAW / "openaq"),
         "clean_mb": folder_mb(CLEAN / "readings_clean.parquet"), "format": "JSON (nested records) -> parquet",
         "velocity": f"{n_series} series x 1 value/hour = {n_series} new values/hour "
                     f"({n_series * 4} raw 15-min readings/hour behind them); newest reading {lag_hours} h "
                     "old when we downloaded"},
        {"source": "Open-Meteo weather", "rows": weather_rows, "raw_mb": folder_mb(RAW / "openmeteo"),
         "clean_mb": folder_mb(CLEAN / "weather_hourly.parquet"), "format": "JSON (parallel arrays) -> parquet",
         "velocity": "1 row/hour for the city; archive published with a delay of a few days"},
        {"source": "Calendar", "rows": len(calendar), "raw_mb": 0,
         "clean_mb": folder_mb(cal_path if cal_path.exists() else MANUAL / "calendar_draft.csv"), "format": "CSV built by hand",
         "velocity": "1 row/day; fixed once a year by government notification"},
        {"source": "Full analysis grid (readings_clean)",
         "rows": len(pd.read_parquet(CLEAN / "readings_clean.parquet", columns=["value"])),
         "raw_mb": 0, "clean_mb": folder_mb(CLEAN / "readings_clean.parquet"),
         "format": "parquet (also MySQL table readings)",
         "velocity": "every station x pollutant x hour, gaps included as empty rows"},
    ]
    vp = pd.DataFrame(rows)
    vp.to_csv(TABLES / "v_profile.csv", index=False)

    md = ["# V profile (generated by src/12_inventory_vprofile.py)", "",
          "| Source | Rows | Raw MB | Clean MB | Format | Velocity |", "|---|---:|---:|---:|---|---|"]
    md += [f"| {r['source']} | {r['rows']:,} | {r['raw_mb']} | {r['clean_mb']} | {r['format']} | {r['velocity']} |"
           for r in rows]
    md += ["", f"**Volume.** {readings_rows:,} hourly air-quality rows from {len(stations)} stations over 14 months, "
               f"{folder_mb(RAW / 'openaq')} MB of raw JSON in {len(manifest):,} API pages. The full hourly grid "
               f"(with gaps as empty rows) is {rows[3]['rows']:,} rows.",
           f"**Velocity.** The network adds {n_series} new hourly values every hour for our stations "
           f"(each built from four 15-minute readings), and OpenAQ's newest reading was {lag_hours} hours old when "
           "we downloaded. That speed is why collection was written as resumable month-by-month pulls with a cache, "
           "not a one-off download.",
           "**Variety.** Two JSON shapes (OpenAQ nested records; Open-Meteo parallel arrays), a hand-built CSV "
           "calendar and a manual Trends CSV, with three clocks (UTC with 'Z', IST with '+05:30', and zone-less GMT).",
           "**Which V dominated?** Velocity and Variety shaped the work more than Volume. Volume is real but "
           "modest: our largest table fits in memory on a laptop, so PySpark was not strictly required at this size. "
           "We used PySpark and parquet because the same job scales unchanged to more stations, 15-minute data and "
           "more years, and because parquet keeps types (timestamps) intact between tools. Variety, especially the "
           "time zones, took most of the cleaning effort."]
    (REPORT / "v_profile.md").write_text("\n".join(md), encoding="utf-8")
    print("v_profile.csv and report/v_profile.md written")


def main():
    ensure_folders()
    data_inventory()
    source_register()
    v_profile()


if __name__ == "__main__":
    main()
