"""
03_collect_weather.py — download hourly weather for Bengaluru from the
Open-Meteo Historical Weather API (archive). No API key needed.

Output:  data/raw/openmeteo/*.json             the cached raw response
         data/interim/openmeteo_manifest.csv   which raw file holds what

We ask for ONE point (the city centre). That matches our weather_hourly table,
which has one row per hour for the whole city. It is also a limitation we name:
rain at Majestic is not always rain at Hebbal.

Time zone: we ask for timezone=GMT on purpose and convert to IST ourselves in
06_time_and_types.py, so the conversion is visible in code and in the
cleaning log, instead of happening silently inside the API.

Run:  python src/03_collect_weather.py     (a few seconds)
"""

import pandas as pd

from common import (BENGALURU_CENTRE, DATE_END, DATE_START, INTERIM, cache_path,
                    ensure_folders, get_json)

URL = "https://archive-api.open-meteo.com/v1/archive"

# The hourly variables we need, and why:
#   precipitation, rain       -> is it raining this hour? how hard?
#   temperature_2m            -> season and evening cooling
#   relative_humidity_2m      -> humid air holds particles longer
#   wind_speed_10m            -> wind disperses pollution (a confounder)
#   boundary_layer_height     -> a low "lid" at night traps pollution (a confounder)
HOURLY = ["precipitation", "rain", "temperature_2m", "relative_humidity_2m",
          "wind_speed_10m", "boundary_layer_height"]


def main():
    ensure_folders()
    lat, lon = BENGALURU_CENTRE
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": DATE_START,
        "end_date": DATE_END,
        "hourly": ",".join(HOURLY),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
    }
    # 14 months of hourly data is about 10,000 rows, which one request returns.
    body = get_json("openmeteo", URL, params)
    hourly = body.get("hourly", {})
    n = len(hourly.get("time", []))

    missing = [v for v in HOURLY if v not in hourly]
    print(f"Open-Meteo: {n:,} hourly rows from {hourly['time'][0]} to {hourly['time'][-1]} (GMT)")
    print(f"Variables missing from the response: {missing or 'none'}")
    print(f"Units: {body.get('hourly_units')}")

    manifest = pd.DataFrame([{
        "source": "openmeteo",
        "lat": lat, "lon": lon,
        "start_date": DATE_START, "end_date": DATE_END,
        "n_hours": n,
        "raw_file": f"data/raw/openmeteo/{cache_path('openmeteo', URL, params).name}",
    }])
    manifest.to_csv(INTERIM / "openmeteo_manifest.csv", index=False)


if __name__ == "__main__":
    main()
