"""
00_smoke_test.py — Phase 1 check: does each API return data for our city and
dates? We pull 1 day x a few stations only, so it takes seconds and costs nothing.

It prints:
  - every Bengaluru PM2.5 monitor OpenAQ knows, with its first/last reading date
    (some sensor ids are old and stopped reporting; we must not test those)
  - a pass/fail line per source
and writes outputs/tables/smoke_test.csv, which the Phase 1 check-in quotes.

Run:  python src/00_smoke_test.py
"""

import pandas as pd

from common import (BENGALURU_BBOX, BENGALURU_CENTRE, DATE_START, TABLES,
                    ensure_folders, get_json, openaq_headers)

TEST_DAY = DATE_START  # first day of the study range
MAX_STATIONS_TO_TRY = 3


def list_pm25_monitors():
    """Return one row per (fixed monitor, PM2.5 sensor) in the Bengaluru box."""
    bbox_text = ",".join(str(v) for v in BENGALURU_BBOX)
    body = get_json("openaq", "https://api.openaq.org/v3/locations",
                    {"bbox": bbox_text, "limit": 1000, "page": 1}, openaq_headers())
    locations = body.get("results", [])

    rows = []
    for loc in locations:
        if not loc.get("isMonitor"):
            continue
        for s in loc.get("sensors") or []:
            if s.get("parameter", {}).get("name") == "pm25":
                rows.append({
                    "location_id": loc.get("id"),
                    "name": loc.get("name"),
                    "pm25_sensor_id": s.get("id"),
                    "first_utc": ((loc.get("datetimeFirst") or {}).get("utc") or "")[:10],
                    "last_utc": ((loc.get("datetimeLast") or {}).get("utc") or "")[:10],
                })
    return len(locations), pd.DataFrame(rows)


def hours_on_test_day(sensor_id):
    """How many hourly PM2.5 values this sensor has on TEST_DAY (0-24)."""
    params = {"datetime_from": f"{TEST_DAY}T00:00:00Z",
              "datetime_to": f"{TEST_DAY}T23:59:59Z", "limit": 100}
    hours = get_json("openaq", f"https://api.openaq.org/v3/sensors/{sensor_id}/hours",
                     params, openaq_headers()).get("results", [])
    # Count only stamps really on TEST_DAY, in case the API ignored the filter.
    stamps = [(h.get("period") or {}).get("datetimeFrom", {}).get("utc", "") for h in hours]
    in_day = [t for t in stamps if t.startswith(TEST_DAY)]
    example = f"first={stamps[0]} value={hours[0].get('value')}" if hours else "no rows"
    return len(in_day), example


def test_openaq():
    n_locations, monitors = list_pm25_monitors()
    if monitors.empty:
        return {"source": "OpenAQ v3", "status": "FAIL",
                "detail": f"{n_locations} locations in box, none is a PM2.5 monitor"}

    print(f"\nPM2.5 monitors in the Bengaluru box ({len(monitors)}):")
    print(monitors.sort_values("last_utc", ascending=False).to_string(index=False))

    # Only test monitors that were reporting across our test day. An old sensor
    # id whose last reading is before TEST_DAY can never pass, so skip it.
    active = monitors[(monitors["first_utc"] <= TEST_DAY) & (monitors["last_utc"] >= TEST_DAY)]
    if active.empty:
        return {"source": "OpenAQ v3", "status": "FAIL",
                "detail": f"{len(monitors)} PM2.5 monitors, none active on {TEST_DAY}"}

    tried = []
    for _, m in active.head(MAX_STATIONS_TO_TRY).iterrows():
        n_hours, example = hours_on_test_day(int(m["pm25_sensor_id"]))
        tried.append(f"'{m['name']}' sensor {m['pm25_sensor_id']}: {n_hours}/24 ({example})")
        if n_hours >= 12:
            return {"source": "OpenAQ v3", "status": "PASS",
                    "detail": f"{n_locations} locations, {len(active)} PM2.5 monitors active on "
                              f"{TEST_DAY}; " + " | ".join(tried)}

    return {"source": "OpenAQ v3", "status": "FAIL", "detail": " | ".join(tried)}


def test_open_meteo():
    """Fetch one day of hourly weather for the city centre, in GMT on purpose."""
    lat, lon = BENGALURU_CENTRE
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": TEST_DAY, "end_date": TEST_DAY,
        "hourly": "precipitation,rain,temperature_2m,relative_humidity_2m,"
                  "wind_speed_10m,boundary_layer_height",
        "timezone": "GMT",  # we convert to IST ourselves, visibly, in 06_time_and_types.py
    }
    body = get_json("openmeteo", "https://archive-api.open-meteo.com/v1/archive", params)
    hourly = body.get("hourly", {})
    n = len(hourly.get("time", []))
    got = [k for k in params["hourly"].split(",") if k in hourly]
    missing = [k for k in params["hourly"].split(",") if k not in hourly]
    status = "PASS" if n == 24 else "FAIL"
    return {"source": "Open-Meteo archive", "status": status,
            "detail": f"{n}/24 hours; got {got}; missing {missing}"}


def main():
    ensure_folders()
    results = []
    for test in (test_openaq, test_open_meteo):
        try:
            results.append(test())
        # Show the real error instead of hiding it. SystemExit is caught too, so a
        # missing OpenAQ key still lets the Open-Meteo test run.
        except (Exception, SystemExit) as error:
            results.append({"source": test.__name__, "status": "FAIL", "detail": str(error)[:300]})

    table = pd.DataFrame(results)
    table.to_csv(TABLES / "smoke_test.csv", index=False)
    print("\nRESULT")
    for _, r in table.iterrows():
        print(f"  {r['source']:20s} {r['status']}\n    {r['detail']}")


if __name__ == "__main__":
    main()
