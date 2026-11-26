"""
00_smoke_test.py — Phase 1 check: does each API return data for our city and
dates? We pull 1 day x 1 station only, so it takes seconds and costs nothing.

It prints a pass/fail line per source and writes outputs/tables/smoke_test.csv,
which the Phase 1 check-in paragraph quotes.

Run:  python src/00_smoke_test.py
"""

import pandas as pd

from common import (BENGALURU_BBOX, BENGALURU_CENTRE, DATE_START, TABLES,
                    ensure_folders, get_json, openaq_headers)

TEST_DAY = DATE_START  # first day of the study range


def test_openaq():
    """Find one Bengaluru monitor with PM2.5 and fetch its hourly values for one day."""
    bbox_text = ",".join(str(v) for v in BENGALURU_BBOX)
    body = get_json("openaq", "https://api.openaq.org/v3/locations",
                    {"bbox": bbox_text, "limit": 1000, "page": 1}, openaq_headers())
    locations = body.get("results", [])

    # Pick the first fixed monitor that has a PM2.5 sensor.
    chosen = None
    for loc in locations:
        if not loc.get("isMonitor"):
            continue
        for s in loc.get("sensors") or []:
            if s.get("parameter", {}).get("name") == "pm25":
                chosen = (loc, s)
                break
        if chosen:
            break
    if chosen is None:
        return {"source": "OpenAQ v3", "status": "FAIL",
                "detail": f"{len(locations)} locations in box, none is a PM2.5 monitor"}

    loc, sensor = chosen
    params = {"datetime_from": f"{TEST_DAY}T00:00:00Z",
              "datetime_to": f"{TEST_DAY}T23:59:59Z", "limit": 100}
    hours = get_json("openaq", f"https://api.openaq.org/v3/sensors/{sensor['id']}/hours",
                     params, openaq_headers()).get("results", [])

    # Check the API honoured our dates (a silently ignored filter would fool us).
    stamps = [(h.get("period") or {}).get("datetimeFrom", {}).get("utc", "") for h in hours]
    in_day = [t for t in stamps if t.startswith(TEST_DAY)]
    status = "PASS" if len(in_day) >= 12 else "FAIL"
    example = f"first={stamps[0]} value={hours[0].get('value')}" if hours else "no rows"
    return {"source": "OpenAQ v3", "status": status,
            "detail": f"{len(locations)} locations; '{loc.get('name')}' sensor {sensor['id']}: "
                      f"{len(in_day)}/24 hours on {TEST_DAY}; {example}"}


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
    # boundary_layer_height may be absent from the archive; record what we got.
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
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
