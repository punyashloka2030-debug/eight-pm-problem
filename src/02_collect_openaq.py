"""
02_collect_openaq.py — download hourly PM2.5, PM10, NO2 and CO for the
approved stations from the OpenAQ v3 API.

Input:   data/manual/stations_approved.csv   (from M5)
Output:  data/raw/openaq/*.json               one cached file per API page
         data/interim/stations.csv            the stations table (name, lat, lon, operator)
         data/interim/openaq_manifest.csv     which raw file holds which sensor-month

This script only DOWNLOADS. Flattening the JSON happens in 05_flatten_json.py,
so the raw files stay untouched (the brief wants raw -> clean to be traceable).

Why month by month? OpenAQ advises short date windows for the measurement
endpoints. A month is at most 744 hours, so it fits in one page of 1,000.
If the script stops halfway (network, laptop sleep), just run it again:
every finished month is already cached and is skipped instantly.

Run:  python src/02_collect_openaq.py      (about 10 minutes the first time)
"""

from datetime import date

import pandas as pd

from common import (DATE_END, DATE_START, INTERIM, MANUAL, cache_path,
                    ensure_folders, get_json, log_decision, openaq_headers,
                    reset_cleaning_log_for_stage)

API = "https://api.openaq.org/v3"
STAGE = "02_collect_openaq"

# The four pollutants in our question. OpenAQ's own parameter names.
PARAMETERS = ["pm25", "pm10", "no2", "co"]


def month_windows(start_text, end_text):
    """
    Split our date range into calendar months: [(from, to), ...].
    Each 'to' is midnight UTC at the start of the NEXT month. If OpenAQ treats
    'to' as inclusive, an hour on a boundary can arrive in two months. We do not
    hide that here: 06_time_and_types.py counts duplicates and logs their removal.
    """
    start = date.fromisoformat(start_text)
    end = date.fromisoformat(end_text)
    windows = []
    current = date(start.year, start.month, 1)
    while current <= end:
        # First day of the next month.
        if current.month == 12:
            next_month = date(current.year + 1, 1, 1)
        else:
            next_month = date(current.year, current.month + 1, 1)
        window_from = max(current, start)
        window_to = min(next_month, date.fromordinal(end.toordinal() + 1))
        windows.append((f"{window_from}T00:00:00Z", f"{window_to}T00:00:00Z"))
        current = next_month
    return windows


def station_details(location_id):
    """
    One stations-table row from /v3/locations/{id}, plus that station's sensors.
    We ask /v3/locations/{id}/sensors separately because that endpoint gives
    each sensor's first/last reading time, which the location record does not.
    """
    body = get_json("openaq", f"{API}/locations/{location_id}", None, openaq_headers())
    loc = body["results"][0]
    sensors = get_json("openaq", f"{API}/locations/{location_id}/sensors",
                       {"limit": 1000}, openaq_headers()).get("results", [])
    coords = loc.get("coordinates") or {}
    return {
        "station_id": f"BLR{location_id}",  # our own short key, stable across sensor-id changes
        "name": loc.get("name"),
        "lat": coords.get("latitude"),
        "lon": coords.get("longitude"),
        "operator": (loc.get("owner") or {}).get("name") or (loc.get("provider") or {}).get("name"),
        "openaq_location_id": location_id,
    }, sensors


def sensors_to_download(sensors):
    """
    Keep sensors for our four pollutants that were still reporting at the start
    of our range. Old sensor ids (last reading before DATE_START) would only
    return empty pages, so we skip them and log how many we skipped.
    """
    keep, skipped_stale = [], 0
    for s in sensors:
        name = (s.get("parameter") or {}).get("name")
        if name not in PARAMETERS:
            continue
        last = ((s.get("datetimeLast") or {}).get("utc") or "")[:10]
        if last and last < DATE_START:
            skipped_stale += 1
            continue
        keep.append(s)
    return keep, skipped_stale


def download_sensor_month(sensor_id, window_from, window_to):
    """Download every page of hourly values for one sensor in one month."""
    pages = []
    page = 1
    while True:
        params = {"datetime_from": window_from, "datetime_to": window_to,
                  "limit": 1000, "page": page}
        url = f"{API}/sensors/{sensor_id}/hours"
        body = get_json("openaq", url, params, openaq_headers())
        n = len(body.get("results", []))
        pages.append((cache_path("openaq", url, params).name, page, n))
        if n < 1000:
            return pages
        page += 1


def main():
    ensure_folders()
    reset_cleaning_log_for_stage(STAGE)

    approved = pd.read_csv(MANUAL / "stations_approved.csv")
    windows = month_windows(DATE_START, DATE_END)
    print(f"{len(approved)} stations x {len(PARAMETERS)} pollutants x {len(windows)} months")

    station_rows, manifest_rows = [], []
    total_stale = 0

    for _, st in approved.iterrows():
        location_id = int(st["openaq_location_id"])
        details, sensors = station_details(location_id)
        station_rows.append(details)

        keep, stale = sensors_to_download(sensors)
        total_stale += stale
        print(f"\n{details['name']}: {len(keep)} sensors to download, {stale} old ids skipped")

        for s in keep:
            parameter = s["parameter"]["name"]
            units = s["parameter"].get("units")
            n_sensor = 0
            for window_from, window_to in windows:
                for file_name, page, n in download_sensor_month(s["id"], window_from, window_to):
                    manifest_rows.append({
                        "station_id": details["station_id"],
                        "openaq_location_id": location_id,
                        "sensor_id": s["id"],
                        "parameter": parameter,
                        "units": units,
                        "window_from": window_from,
                        "page": page,
                        "n_results": n,
                        "raw_file": f"data/raw/openaq/{file_name}",
                    })
                    n_sensor += n
            print(f"   {parameter:5s} sensor {s['id']:>9}: {n_sensor:6d} hourly rows")

    pd.DataFrame(station_rows).to_csv(INTERIM / "stations.csv", index=False)
    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(INTERIM / "openaq_manifest.csv", index=False)

    total_rows = int(manifest["n_results"].sum())
    print(f"\nTOTAL hourly rows downloaded: {total_rows:,}")
    print(manifest.groupby("parameter")["n_results"].sum().to_string())

    log_decision(STAGE, "Approved stations also list sensor ids for our pollutants whose last "
                 f"reading is before {DATE_START}", total_stale,
                 "Skipped these old ids when downloading",
                 "They only return empty pages; the station's new id carries the data")


if __name__ == "__main__":
    main()
