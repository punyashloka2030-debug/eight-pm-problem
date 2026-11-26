# QA_PREP — viva preparation (manual step M13)

The brief: *"In Q&A, any member may be asked to explain any line of code or any cleaning decision."*
So every member reads **all** of this, not only their own slides.

How to use it:
1. Read "The pipeline in one minute" until you can say it without looking.
2. For each script, open it and find the three key lines (line numbers are given). Say out loud what each does.
3. Cover the answers to the 25 questions and answer them to a teammate. Then rehearse the talk with
   `report/speaker_script.md` (7 minutes, timed).

Numbers below are from the run of 2026-11-26. If you re-run the pipeline, check them against
`outputs/tables/analysis_summary.json`.

---

## The pipeline in one minute

We download 14 months of hourly air quality for 7 Bengaluru monitors from the **OpenAQ API** (JSON) and
hourly weather from the **Open-Meteo API** (JSON); we build a **holiday calendar** by hand and check it
against the government notification; and we export **Google Trends** as a text-derived source.
We **flatten** the JSON into tables, convert every clock to **IST**, line up weather hours (which start at
:30) with air hours (which start at :00), and convert NO2/CO from ppb to the units the Indian AQI uses.
We **count every gap**, blank sensor failures, keep real extremes like Deepavali, and fill only gaps of up to
3 hours. **PySpark** resamples to hourly, joins air + weather + calendar and groups by hour and weekday.
**MySQL** holds the same data in 4 linked tables for SQL queries. The analysis compares rainy and dry
evenings **within the same month and day type**, and every number in the report and slides is read from
the pipeline's own output files. `make all` rebuilds everything.

## Numbers to remember

| What | Number |
|---|---|
| OpenAQ hourly rows / full grid rows | 204,584 / 279,552 |
| Weather hours / calendar days | 9,984 / 416 |
| Stations / coverage rule | 7 / ≥ 60% PM2.5 hours (70% left only 5) |
| Hours never sent | 75,136 (27% of the grid) |
| Short gaps forward-filled (≤ 3 h) | 12,612 |
| Flat-lines / zeros blanked | 1,720 / 877 |
| Usable station-evenings (≥ 6 of 7 real hours) | 2,040 (872 of 2,912 excluded) |
| Typical peak / share of peaks 19:00–22:00 | 20:00 / 65% |
| Edge peaks (17:00 or still rising at 23:00) | 25% |
| Rainy vs dry evenings compared | 409 vs 1,027 (79 rainy dates, 15 month × day-type groups) |
| Rain: peak height / peak timing | −29% (CI −43 to −13%) / −0.8 h (CI −1.3 to −0.4 h) |
| Regression check | −35%, −0.9 h |
| Weekday gap without festivals / p-value | 2.4 µg/m³ / 0.992 → no weekday stands out |
| Worst months / cleanest | Nov 2026 53.3, Mar 50.6, Apr 46.5 / Jun–Aug 16.9–19.3 µg/m³ |
| Deepavali 2025, 19:00–23:00 | 76.7 vs 32.5 µg/m³ (+136%) |
| Spreadsheet vs pandas pivot | 168 / 168 cells match |
| Calendar check (M6) | 2 dates corrected (Mahavir Jayanti 31 Mar, Valmiki Jayanti 25 Oct 2026) |

---

## Script by script

Each entry: **what it does**, **three key lines** (open the file at that line), **what breaks**.

### common.py — shared helpers
- **What:** folder paths, city settings, the polite cached API caller, the cleaning-log writer, `save_parquet`.
- **Key lines:**
  - L65 `MIN_SECONDS_BETWEEN_CALLS = 1.1` — wait at least 1.1 s between API calls (OpenAQ allows 60 per minute).
  - L78 `def get_json(...)` — every API call goes through here: it returns the cached file if we already
    downloaded it, so re-running costs nothing and the raw data stay unchanged.
  - L198 `df.to_parquet(path, ..., coerce_timestamps="us", ...)` — saves times in microseconds, because
    Spark cannot read pandas' default nanosecond timestamps.
- **What breaks:** no `.env` / wrong API key → 401 errors; deleting `data/raw/` forces a full re-download.

### 00_smoke_test.py / 00_spark_hello.py — Phase 1 checks
- **What:** fetch 1 day from each API to prove the sources work (Phase 1 check-in); start Spark once (M3).
- **Key idea:** the smoke test only tries sensors whose first/last dates cover the test day, because old
  5-digit sensor ids return empty pages.
- **What breaks:** no Java 17 → Spark cannot start ("JAVA_HOME is not set").

### 01_find_stations.py — which monitors, and how complete
- **What:** lists every OpenAQ location in the Bengaluru box, keeps reference monitors with PM2.5, measures
  each one's PM2.5 coverage for our dates, proposes stations.
- **Key lines:**
  - L42–46 `bbox_text = ...; params = {"bbox": bbox_text, ...}` — ask OpenAQ for everything inside the
    Bengaluru rectangle (min lon, min lat, max lon, max lat).
  - L84 `"is_monitor": loc.get("isMonitor")` — reference monitors only; low-cost sensors measure differently.
  - L197 `coverage[coverage["pm25_coverage_pct"] >= MIN_COVERAGE_PCT]` — the 60% rule (L31) chosen at M5.
- **What breaks:** a 70% rule leaves only 5 stations; old sensor ids show 0% coverage.

### 02_collect_openaq.py — download the air-quality data
- **What:** for each approved station and pollutant, downloads hourly values month by month and caches every page.
- **Key lines:**
  - L105 `params = {"datetime_from": window_from, "datetime_to": window_to, "limit": 1000, "page": page}` —
    one month per request (at most 744 hours) so pages stay small.
  - L107 `url = f"{API}/sensors/{sensor_id}/hours"` — the hourly endpoint: each value is already the average
    of four 15-minute readings.
  - L108 `body = get_json("openaq", url, params, openaq_headers())` — the cached, rate-limited call.
- **What breaks:** an expired key; asking for old sensor ids (they return empty pages, so they are skipped: log row 4).

### 03_collect_weather.py — download the weather
- **What:** one request to the Open-Meteo archive for hourly rain, temperature, humidity, wind, boundary layer.
- **Key lines:**
  - L44 `"hourly": ",".join(HOURLY)` — which hourly variables we ask for.
  - L45 `"timezone": "GMT"` — on purpose: we convert to IST ourselves so the conversion is visible and checked.
  - L50 `hourly = body.get("hourly", {})` — the answer is parallel arrays (time[], rain[], ...), not records.
- **What breaks:** the archive lags real time by a few days, so the newest days can be missing.

### 04_build_calendar.py — the holiday and festival calendar (draft)
- **What:** one row per date: weekday, season, Sundays and 2nd/4th Saturdays, holidays, festivals, long weekends.
  The human check (M6) saved the corrected file as `data/manual/calendar_verified.csv`.
- **Key lines:**
  - L148 `cal["is_holiday"] = cal["is_weekend"] | cal["is_general_holiday"]` — a day most offices are closed.
  - L152–159 the long-weekend loop — a run of 3 or more `is_holiday` days in a row.
  - L164 `cal["school_break"] = ""` — left blank for the human check rather than guessed.
- **What breaks:** a wrong date silently moves an evening between "working day" and "holiday" groups
  (M6 found 2 such dates).

### 05_flatten_json.py — JSON to tables
- **What:** turns the cached JSON into flat tables; writes a before/after example for the report.
- **Key lines:**
  - L65 `flat = pd.json_normalize(results)` — nested objects become dotted columns (`period.datetimeFrom.utc`).
  - L119 `weather = pd.DataFrame(body["hourly"])` — parallel arrays become columns directly.
  - L88–89 the log row — 32 columns after flattening; we keep 8 plus the ids.
- **What breaks:** if OpenAQ renames a JSON key, the kept-column list must change.

### 05b_load_trends.py — Google Trends
- **What:** reads the M7 CSV, turns "<1" into 0.5, makes weeks, compares with weekly rain and PM2.5 (Spearman).
- **Key idea:** Trends is weekly and relative (100 = busiest week), so it gives context, never single evenings.
- **What breaks:** Google changes the CSV header lines; a range over ~9 months gives weekly, not daily, values.

### 06_time_and_types.py — time zones, types, units
- **What:** one clock (IST), numbers as floats, NO2/CO in Indian AQI units, duplicates removed, weather aligned.
- **Key lines:**
  - L47–51 `pd.to_datetime(..., utc=True)` then `.dt.tz_convert(IST)` — parse UTC text, convert to IST;
    L55 parses OpenAQ's own '+05:30' copy, and the two are compared: 0 mismatches.
  - L80 `pd.to_numeric(df["value"], errors="coerce").astype("float64")` — text that is not a number becomes
    missing instead of breaking an average.
  - L156 `out["ts_ist"] = w["label_ist"] - pd.Timedelta(minutes=30)` — weather hours start at :30 IST; this
    puts each weather value on the IST hour whose middle it measures.
- **What breaks:** joining on the raw labels would pair every air reading with weather from 30 minutes earlier.

### 07_gaps_outliers.py — gaps, failures, real events, filling
- **What:** builds the full station × pollutant × hour grid, counts gaps, flags failures, keeps real extremes,
  applies the M11 human verdicts, forward-fills short gaps, marks usable evenings.
- **Key lines:**
  - L189 `run_id = (~same_as_before).cumsum()` (with L46 `FLATLINE_HOURS`) — numbers each run of identical
    values; a run of ≥ 6 hours (CO ≥ 12) is a stuck sensor.
  - L209 `is_spike = (value > SPIKE_RATIO * neighbours) & (value - neighbours > jump)` — one hour 5× both
    neighbours with a big jump is a glitch, unless it is a festival night or heavy rain.
  - L356 `.ffill(limit=FFILL_LIMIT_HOURS)` — forward-fill at most 3 hours; L379 `evening_usable` needs ≥ 6 of 7
    REAL evening hours, so a filled hour can never be the peak.
- **What breaks:** filling long gaps would invent days of data; removing all extremes would delete Deepavali.

### 07b_review_outliers.py — helper for M11
- **What:** for each of the 10 biggest unexplained values, prints ±3 h at the station, all other stations that
  hour, rain and festival flag; `--save` stores the verdicts.
- **Rule we used:** a real event builds up over hours AND other stations are high or it is a festival; a failure
  jumps from normal to huge and straight back at one station.

### 08_spark_job.py — the big-data step (PySpark)
- **What:** load → clean → resample → join → aggregate the largest table, saving row counts after each stage.
- **Key lines:**
  - L86 `readings.filter(F.col("value").isNotNull() & ~F.col("qc_flag").isin(FAILURE_FLAGS))` —
    279,552 → 213,940 rows: drop empty hours and failures, keep real events.
  - L108–109 `F.date_trunc("hour", ...).cast("timestamp_ntz")` then `.groupBy(...)` — resample to hourly; the
    cast stops Spark making the time zone-aware (it read back 5.5 h off before we fixed it).
  - L135–137 `.join(weather, on="ts_hour", how="left").join(calendar, on="date", how="left")` — left joins keep
    every PM2.5 hour (55,026); unmatched rows are counted (0).
- **What breaks:** pandas nanosecond parquet ("Illegal Parquet type"), no Java, or `toPandas()` with pandas 3.

### 09_load_mysql.py + sql/ — the relational version
- **What:** creates 4 tables from `sql/schema.sql`, loads them, draws the ER diagram, runs 7 queries.
- **Key lines:**
  - `sql/schema.sql` L42–43 `PRIMARY KEY (station_id, ts_ist, parameter)` and
    `FOREIGN KEY (station_id) REFERENCES stations (station_id)` — one value per station, hour and pollutant,
    and every reading must belong to a real station.
  - L39 `engine = create_engine(url)` — SQLAlchemy connection built from `.env` (port 3307 on our laptop).
  - L102 `df.to_sql(name, engine, if_exists="append", ..., chunksize=10_000)` — append into the tables
    schema.sql made, so our keys and types are kept.
- **What breaks:** MySQL container stopped (`sudo docker start eightpm-mysql`), wrong port or password in `.env`.

### 10_analysis.py — the answer in numbers
- **What:** peak timing, rain effect, worst weekdays/months, z-scores, AQI categories, event studies.
- **Key lines:**
  - L112 `rain_1622 = w[w["hour"].between(16, 21)].groupby("date")["precip_mm"].sum()` — rainy evening =
    ≥ 1 mm between 16:00 and 21:59; dry = < 0.1 mm from noon to midnight; the rest is left out.
  - L158 `shift = np.average(m[("peak_hour","rainy")] - m[("peak_hour","dry")], weights=w)` — rainy minus dry
    INSIDE each month × day-type group, averaged; L176 resamples whole dates 1,000 times for the 95% CI.
  - L191 `smf.ols("log_peak ~ rainy + C(month) + C(day_type) + C(station_id)", ...)` — the regression check,
    with standard errors clustered by date. (Also L90: the z-score; L272: the weekday permutation test.)
- **What breaks:** comparing raw rainy vs dry evenings would mostly compare monsoon with winter.

### 11_charts.py — charts with finding titles
- **What:** 7 charts whose titles are built from the numbers, so they change if the data change.
- **Key lines:** L77 `hw.pivot(index="weekday", columns="hour", values="mean_pm25")` — the heatmap grid from
  Spark's output; L93 `ax.imshow(...)` draws it; L99 `ax.axvspan(16.5, 23.5, ...)` the dashed evening box.
- **What breaks:** long titles overlapping (fixed by wrapping footnotes).

### 12_inventory_vprofile.py — inventory, source register, V profile
- **What:** every field with its measurement level and structure (AQI category = ORDINAL), the source register,
  and the V profile — all from the files, not typed in.

### 13_compare_spreadsheet.py — M10 check
- **Key lines:** L56 `pandas_long.merge(sheet, on=["hour","weekday"], how="outer", indicator=True)` — line up
  the two pivots cell by cell; L57 `abs_diff`; L24 `TOLERANCE = 0.01`. Result: 168/168 match.
- **What breaks:** choosing Sum instead of Average in the spreadsheet.

### 14_build_report.py / 15_build_slides.py — report and slides
- **What:** write the report (sections a–i, appendices) and the 10 slides from the output tables; render to
  .docx/.pdf/.pptx. Cleaning-log rows are found by their text, not their number, so a reordered log cannot put a
  wrong number in the report.

---

## 25 viva questions

**1. What is your question and what decision does it serve?**
Does rain delay, flatten or worsen Bengaluru's evening PM2.5 peak, and on which weekdays and months is it worst?
It decides when the city sends evening pollution alerts and whether rain-day rules need different timing.

**2. Why PM2.5?**
It is the pollutant most linked to health (fine particles reach the lungs) and it is measured hourly at official
monitors. NO2 and CO were downloaded too and used as a sanity check of our time zones.

**3. Classify `aqi_category`, `weekday`, `value` and `observed_count`.**
AQI category is ordinal (Good < … < Severe, unequal steps); weekday is ordinal in our inventory (ordered, repeats
weekly); value is continuous (ratio scale, true zero); observed_count is discrete (0–4 quarter-hours).

**4. Which V dominated?**
Variety (two JSON shapes, a hand-built CSV, a Trends CSV, three clocks) and velocity (28 new values per hour)
shaped the work more than volume; 204,584 rows fit in a laptop's memory. We still used PySpark so the same job
scales to more stations, 15-minute data and more years.

**5. Name your sources and how you accessed them.**
OpenAQ v3 API (JSON, API key), Open-Meteo archive API (JSON, no key), a holiday calendar typed from government
notifications, and a manual Google Trends CSV export. URLs, access dates and terms are in the source register.

**6. How did you flatten the JSON?**
OpenAQ sends a list of records with nested objects; `pd.json_normalize` turns nested keys into columns (32 of
them; we keep 8). Open-Meteo sends parallel arrays; `pd.DataFrame(body["hourly"])` makes each array a column.

**7. Explain your MySQL schema.**
Four tables: stations (PK station_id), readings (PK station_id + ts_ist + parameter, FK to stations),
weather_hourly (PK ts_ist), calendar (PK date). Readings join weather on the hour and calendar on the date.

**8. Show a JOIN and a GROUP BY.**
Q2: readings JOIN stations, GROUP BY station name, to count PM2.5 hours without a value per station.
Q5 joins three tables (readings, weather_hourly, calendar).

**9. What did the spreadsheet comparison show?**
The same hour × weekday pivot built in LibreOffice and in pandas matched in 168 of 168 cells (largest difference
0.005). The spreadsheet took about 25–30 minutes, is not reproducible, and is easy to get wrong (Sum vs Average).

**10. How many gaps were there and what rule did you use?**
75,136 of 279,552 station-hours (27%) were never sent. Pollutants: forward-fill up to 3 hours, longer gaps stay
empty. Smooth weather: interpolate up to 3 hours. Rain: never filled. An evening is used for peak timing only
with ≥ 6 of 7 real hours.

**11. Why 3 hours?**
PM2.5 changes slowly hour to hour, so carrying a value forward for a short dropout is a fair guess; beyond about
3 hours the evening rush itself can change, so filling would be invention.

**12. Why never fill rain?**
Rain starts and stops suddenly; interpolating would invent showers and change which evenings count as rainy.

**13. How did you convert UTC to IST, and how do you know it is right?**
`pd.to_datetime(utc=True)` then `tz_convert("Asia/Kolkata")`. OpenAQ also sends a '+05:30' local time, and our
conversion matched it in every row (0 mismatches). NO2 also peaks at 07:00 and 19:00 IST, the rush hours.

**14. What was the half-hour problem?**
Air-quality hours start at :00 IST, but Open-Meteo hours (requested in GMT) start at :30 IST. We put each weather
value on the IST hour whose middle it measures, and split rain totals half and half, before joining.

**15. How did you tell a sensor failure from Diwali night?**
Failures: exact zeros, flat-lines of ≥ 6 hours, one-hour spikes that jump and fall straight back, values outside
the analyser's range — blanked. Real events: festival nights, city-wide highs at ≥ 3 stations, heavy rain — kept.
A person reviewed the 10 biggest unexplained values (M11) by looking at build-up, other stations and the calendar.

**16. Why z-scores, and where?**
Stations have different baselines (Silk Board is a busy junction). A z-score within each station asks "how
unusual is this hour for this station", so rainy and dry curves can be compared across stations (chart 2).

**17. What does PySpark do in your project?**
Loads the 279,552-row table, drops empty and failed hours (213,940), resamples to hourly with `date_trunc`, joins
PM2.5 with weather and calendar (55,026 rows), and groups by weekday × hour (168 rows, the heatmap).

**18. How do you define a rainy and a dry evening?**
Rainy: ≥ 1 mm between 16:00 and 21:59. Dry: < 0.1 mm from 12:00 to 23:59. Evenings in between are left out so
the two groups are clearly different.

**19. How did you hold season and weekday constant?**
We compared rainy and dry evenings only inside the same month × day type (working day vs weekend/holiday),
15 groups, then averaged. A regression with month, day type and station effects gives the same answer.

**20. Where do the confidence intervals come from?**
A bootstrap: we resample whole dates 1,000 times (all stations on a date move together, because they share the
weather) and take the 2.5th and 97.5th percentiles: peak −43% to −13%, timing −1.3 to −0.4 h.

**21. Does rain cause cleaner evenings?**
We do not claim that. Rainy days are already cleaner at noon, before the rain window, so the weather systems
that bring rain (wind, cloud, mixing) are a confounder; fewer people going out in rain is another.

**22. Why do you say no weekday stands out, when Monday is highest?**
Both Deepavalis fall on or next to a Monday. Without festival dates the gap is 2.4 µg/m³, and shuffling weekday
labels between dates 1,000 times gives a gap this large almost every time (p = 0.992).

**23. What is an "edge peak"?**
An evening whose maximum is at 17:00 or 23:00, the edge of our window; 25% of evenings. Usually PM2.5 is still
rising at 23:00 as the night air traps pollution near the ground, so we report these separately.

**24. What are your main limitations?**
7 monitors all within 13 km of the centre (outer city unseen); one weather point for the city; 30% of
station-evenings too incomplete to time; correlation not cause; no traffic counts; Trends is weekly and
represents online searchers only.

**25. How did you use generative AI?**
Claude (Anthropic) through Claude Code wrote most of the code and drafted the report and slides, under our rules
(no invented numbers, every number from a pipeline file). We chose the question, stations and 60% rule, built the
spreadsheet pivot and judged the outliers ourselves. Full disclosure: Appendix F of the report.
