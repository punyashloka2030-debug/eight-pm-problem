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
                    ensure_folders, get_json, log_decision, openaq_headers,
                    reset_cleaning_log_for_stage)

STAGE = "01_find_stations"

API = "https://api.openaq.org/v3"

# Coverage rule for proposing a station (we explain this in the report):
# a station must have PM2.5 for at least 60% of the hours in our range.
# We first tried 70%: only 5 stations passed. 60% adds BTM Layout (68%) and
# Peenya (62%), covering more of the city. That is safe because the gap rule in
# 07_gaps_outliers.py drops incomplete EVENINGS anyway, so a 62% station only
# contributes the evenings it fully recorded. (Team decision, M5, 2026-11-26.)
MIN_COVERAGE_PCT = 60.0
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

    # A station can have MORE THAN ONE PM2.5 sensor id: OpenAQ re-issued ids
    # (e.g. Hebbal has 20212 and 12235249). We keep all of them, joined by ";",
    # and later treat them as one station (a "station ID change" in the log).
    pm25_ids = []
    for s in sensors:
        if s.get("parameter", {}).get("name") == "pm25":
            pm25_ids.append(str(s.get("id")))

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
        "pm25_sensor_ids": ";".join(pm25_ids) if pm25_ids else None,
        "n_pm25_sensors": len(pm25_ids),
        "first_utc": first,
        "last_utc": last,
    }


def daily_pct_for_sensor(sensor_id):
    """
    Return {day: percentComplete} for one sensor inside our date range.

    We use the /sensors/{id}/days endpoint: one row per day, each with a
    `coverage.percentComplete` value (share of expected readings that arrived).
    About 416 days fits in one page of 1,000, so this is one request per sensor.
    """
    params = {
        "datetime_from": f"{DATE_START}T00:00:00Z",
        "datetime_to": f"{DATE_END}T23:59:59Z",
        "limit": 1000,
    }
    body = get_json("openaq", f"{API}/sensors/{sensor_id}/days", params, openaq_headers())

    pct_by_day = {}
    for d in body.get("results", []):
        # Guard: keep only days really inside our range, in case the API
        # ignored the date parameters.
        day = ((d.get("period") or {}).get("datetimeFrom") or {}).get("utc", "")[:10]
        if not (DATE_START <= day <= DATE_END):
            continue
        pct = (d.get("coverage") or {}).get("percentComplete")
        pct_by_day[day] = min(float(pct or 0), 100.0)
    return pct_by_day


def station_coverage(sensor_ids):
    """
    Coverage % for a station that may have several PM2.5 sensor ids.

    For each day we take the BEST sensor's percentComplete (if the old id is
    empty that day but the new id reported, the station still had data).
    Missing days count as 0. Sum / number of days in range = coverage %.
    """
    n_days_in_range = (date.fromisoformat(DATE_END) - date.fromisoformat(DATE_START)).days + 1
    best_by_day = {}
    per_sensor = []
    for sid in sensor_ids:
        pct_by_day = daily_pct_for_sensor(int(sid))
        sensor_cov = round(sum(pct_by_day.values()) / n_days_in_range, 1)
        per_sensor.append(f"{sid}:{sensor_cov}%")
        for day, pct in pct_by_day.items():
            best_by_day[day] = max(best_by_day.get(day, 0.0), pct)

    combined = round(sum(best_by_day.values()) / n_days_in_range, 1)
    return combined, len(best_by_day), " ".join(per_sensor)


def main():
    ensure_folders()
    reset_cleaning_log_for_stage(STAGE)  # re-running must not duplicate log rows

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
        & flat["pm25_sensor_ids"].notna()
    ].copy()
    print(f"   {len(candidates)} are fixed reference monitors with PM2.5")
    log_decision(STAGE, "Locations in the Bengaluru box are a mix of reference monitors, "
                 "low-cost sensors and locations without PM2.5",
                 len(flat) - len(candidates), "Kept only fixed reference monitors with a PM2.5 sensor",
                 "Low-cost and mobile sensors measure differently; mixing them compares unlike things")

    print(f"2) PM2.5 coverage for {DATE_START} to {DATE_END}")
    coverage_rows = []
    for _, row in candidates.iterrows():
        sensor_ids = row["pm25_sensor_ids"].split(";")
        pct, days_in, per_sensor = station_coverage(sensor_ids)
        coverage_rows.append({
            "openaq_location_id": row["openaq_location_id"],
            "pm25_coverage_pct": pct,
            "days_with_data": days_in,
            "coverage_per_sensor_id": per_sensor,
        })
        print(f"   {row['name'][:40]:40s} {pct:5.1f}%  ({days_in} days)  [{per_sensor}]")

    coverage = candidates.merge(pd.DataFrame(coverage_rows), on="openaq_location_id")
    coverage = coverage.sort_values("pm25_coverage_pct", ascending=False)
    coverage.to_csv(TABLES / "station_coverage.csv", index=False)

    # Station ID changes: count sensor ids that have 0% in our range although
    # the station itself lists them (old ids replaced by new 1223xxxx ids).
    dead_ids = sum(
        part.endswith(":0.0%")
        for text in coverage["coverage_per_sensor_id"]
        for part in text.split()
    )
    log_decision(STAGE, "Stations list several PM2.5 sensor ids; old ids have no data in our range "
                 "(OpenAQ re-issued sensor ids)", dead_ids,
                 "Treat all ids of one location as one station; per day take the id that reported",
                 "Otherwise one station would look like two, one of them empty")

    # Propose the best-covered stations, capped at MAX_STATIONS.
    proposed = coverage[coverage["pm25_coverage_pct"] >= MIN_COVERAGE_PCT].head(MAX_STATIONS)
    proposed.to_csv(INTERIM / "stations_proposed.csv", index=False)
    log_decision(STAGE, f"Monitors below {MIN_COVERAGE_PCT:.0f}% PM2.5 coverage for the study range",
                 len(coverage) - len(proposed),
                 f"Dropped; kept {len(proposed)} stations with coverage >= {MIN_COVERAGE_PCT:.0f}%",
                 "Too few complete evenings to time the evening peak; 70% left only 5 stations, "
                 "so the team chose 60% (M5)")

    print(f"\n3) Proposed {len(proposed)} stations (coverage >= {MIN_COVERAGE_PCT}%)")
    cols = ["openaq_location_id", "name", "pm25_coverage_pct", "coverage_per_sensor_id", "parameters"]
    print(proposed[cols].to_string(index=False))

    if len(proposed) < 6:
        print(
            "\n!! Fewer than 6 stations pass the coverage rule. STOP: OpenAQ coverage "
            "is thin. Tell the team; the fallback is CPCB manual downloads (M8)."
        )


if __name__ == "__main__":
    main()
