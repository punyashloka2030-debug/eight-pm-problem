"""
01_find_stations.py — find Bengaluru air-quality stations on OpenAQ and
measure how complete each one is for our date range.

Output:
  data/interim/openaq_locations_flat.csv   every location in the Bengaluru box
  outputs/tables/station_coverage.csv      PM2.5 coverage % per station, ranked
  data/interim/stations_proposed.csv       the 6-10 stations we propose (for M5)

Run:  python src/01_find_stations.py
"""

from datetime import date

import pandas as pd

from common import (BENGALURU_BBOX, DATE_END, DATE_START, INTERIM, TABLES,
                    ensure_folders, get_json, openaq_headers)

API = "https://api.openaq.org/v3"

# Coverage rule for proposing a station (we explain this in the report):
# a station must have PM2.5 for at least 70% of the hours in our range.
# Below that, too many evenings are missing to time the evening peak.
MIN_COVERAGE_PCT = 70.0
MAX_STATIONS = 10


def fetch_locations_in_bbox():
    """
    Ask OpenAQ for every location inside the Bengaluru bounding box.
    bbox order is min lon, min lat, max lon, max lat (OpenAQ docs, Geospatial
    queries). limit=1000 is the largest page OpenAQ allows, so one page is
    normally enough for one city, but we still loop in case it is not.
    """
    bbox_text = ",".join(str(v) for v in BENGALURU_BBOX)
    all_results = []
    page = 1
    while True:
        params = {"bbox": bbox_text, "limit": 1000, "page": page}
        body = get_json("openaq", f"{API}/locations", params, openaq_headers())
        results = body.get("results", [])
        all_results.extend(results)
        if len(results) < 1000:
            break
        page += 1
    return all_results


def flatten_location(loc):
    """
    Turn one nested location record into one flat row.
    We keep the PM2.5 sensor id separately because coverage is checked on PM2.5.
    """
    sensors = loc.get("sensors") or []
    parameter_names = sorted({s.get("parameter", {}).get("name", "") for s in sensors})

    pm25_sensor_id = None
    for s in sensors:
        if s.get("parameter", {}).get("name") == "pm25":
            pm25_sensor_id = s.get("id")

    coords = loc.get("coordinates") or {}
    first = (loc.get("datetimeFirst") or {}).get("utc")
    last = (loc.get("datetimeLast") or {}).get("utc")

    return {
        "openaq_location_id": loc.get("id"),
        "name": loc.get("name"),
        "locality": loc.get("locality"),
        "lat": coords.get("latitude"),
        "lon": coords.get("longitude"),
        "provider": (loc.get("provider") or {}).get("name"),
        "owner": (loc.get("owner") or {}).get("name"),
        "is_monitor": loc.get("isMonitor"),
        "is_mobile": loc.get("isMobile"),
        "parameters": ";".join(p for p in parameter_names if p),
        "pm25_sensor_id": pm25_sensor_id,
        "first_utc": first,
        "last_utc": last,
    }


def pm25_coverage_pct(sensor_id):
    """
    Percentage of our date range that this PM2.5 sensor actually covered.

    We use the /sensors/{id}/days endpoint: one row per day, each with a
    `coverage.percentComplete` value (share of expected readings that arrived).
    Days that are missing entirely count as 0%. Sum / number of days = coverage.
    One request per station is cheap (about 416 days fits in one page).
    """
    params = {
        "datetime_from": f"{DATE_START}T00:00:00Z",
        "datetime_to": f"{DATE_END}T23:59:59Z",
        "limit": 1000,
    }
    body = get_json("openaq", f"{API}/sensors/{sensor_id}/days", params, openaq_headers())
    days = body.get("results", [])

    n_days_in_range = (date.fromisoformat(DATE_END) - date.fromisoformat(DATE_START)).days + 1
    total_pct = 0.0
    days_inside_range = 0
    for d in days:
        # Guard: check each returned day really is inside our range. If the API
        # ignored our date parameters we would otherwise get a wrong answer.
        day_start = ((d.get("period") or {}).get("datetimeFrom") or {}).get("utc", "")[:10]
        if not (DATE_START <= day_start <= DATE_END):
            continue
        days_inside_range += 1
        pct = (d.get("coverage") or {}).get("percentComplete")
        total_pct += min(float(pct or 0), 100.0)

    return round(total_pct / n_days_in_range, 1), days_inside_range, len(days)


def main():
    ensure_folders()

    print(f"1) Locations inside the Bengaluru box {BENGALURU_BBOX}")
    locations = fetch_locations_in_bbox()
    flat = pd.DataFrame([flatten_location(loc) for loc in locations])
    flat.to_csv(INTERIM / "openaq_locations_flat.csv", index=False)
    print(f"   found {len(flat)} locations")

    # Keep fixed reference monitors with a PM2.5 sensor. Low-cost sensors and
    # mobile units are measured differently, so mixing them would compare
    # unlike things. (We name this choice in the limitations section.)
    candidates = flat[
        (flat["is_monitor"] == True)  # noqa: E712  (explicit True keeps None out)
        & (flat["is_mobile"] != True)  # noqa: E712
        & flat["pm25_sensor_id"].notna()
    ].copy()
    print(f"   {len(candidates)} are fixed reference monitors with PM2.5")

    print(f"2) PM2.5 coverage for {DATE_START} to {DATE_END}")
    coverage_rows = []
    for _, row in candidates.iterrows():
        pct, days_in, days_returned = pm25_coverage_pct(int(row["pm25_sensor_id"]))
        coverage_rows.append({
            "openaq_location_id": row["openaq_location_id"],
            "pm25_coverage_pct": pct,
            "days_with_data": days_in,
            "days_returned_by_api": days_returned,
        })
        print(f"   {row['name'][:45]:45s} {pct:5.1f}%  ({days_in} days)")

    coverage = candidates.merge(pd.DataFrame(coverage_rows), on="openaq_location_id")
    coverage = coverage.sort_values("pm25_coverage_pct", ascending=False)
    coverage.to_csv(TABLES / "station_coverage.csv", index=False)

    # Propose the best-covered stations, capped at MAX_STATIONS.
    proposed = coverage[coverage["pm25_coverage_pct"] >= MIN_COVERAGE_PCT].head(MAX_STATIONS)
    proposed.to_csv(INTERIM / "stations_proposed.csv", index=False)

    print(f"\n3) Proposed {len(proposed)} stations (coverage >= {MIN_COVERAGE_PCT}%)")
    cols = ["openaq_location_id", "name", "provider", "pm25_coverage_pct", "parameters"]
    print(proposed[cols].to_string(index=False))

    if len(proposed) < 6:
        print(
            "\n!! Fewer than 6 stations pass the coverage rule. STOP: OpenAQ coverage "
            "is thin. Tell the team; the fallback is CPCB manual downloads (M8)."
        )


if __name__ == "__main__":
    main()
