-- queries.sql — questions we ask the database. Each query starts with a
-- "-- Qn:" line; src/09_load_mysql.py runs them all and saves each result to
-- outputs/tables/sql_qn.csv (and all of them to outputs/tables/sql_query_outputs.md).


-- Q1: How big is each table? (the V profile quotes these numbers)
SELECT 'stations' AS table_name, COUNT(*) AS n_rows FROM stations
UNION ALL SELECT 'readings', COUNT(*) FROM readings
UNION ALL SELECT 'weather_hourly', COUNT(*) FROM weather_hourly
UNION ALL SELECT 'calendar', COUNT(*) FROM calendar;


-- Q2: Gaps per station (JOIN + GROUP BY). How many PM2.5 hours have no usable value?
--     JOIN brings in the station name; GROUP BY gives one row per station.
SELECT s.name,
       COUNT(*)                                          AS hours_in_range,
       SUM(r.value IS NULL)                              AS hours_without_value,
       ROUND(100 * SUM(r.value IS NULL) / COUNT(*), 1)   AS pct_without_value
FROM readings AS r
JOIN stations AS s ON s.station_id = r.station_id
WHERE r.parameter = 'pm25'
GROUP BY s.name
ORDER BY pct_without_value DESC;


-- Q3: The heatmap in SQL (GROUP BY hour x weekday). Mean PM2.5 for each weekday
--     and IST hour, evenings only (17:00-23:00) to keep the output short.
--     WEEKDAY() gives Monday = 0 ... Sunday = 6.
SELECT WEEKDAY(r.ts_ist)        AS weekday_num,
       DAYNAME(r.ts_ist)        AS weekday,
       HOUR(r.ts_ist)           AS hour_ist,
       ROUND(AVG(r.value), 1)   AS mean_pm25,
       COUNT(r.value)           AS n_station_hours
FROM readings AS r
WHERE r.parameter = 'pm25'
  AND r.value IS NOT NULL
  AND HOUR(r.ts_ist) BETWEEN 17 AND 23
GROUP BY weekday_num, weekday, hour_ist
ORDER BY weekday_num, hour_ist;


-- Q4: Rainy vs dry evening hours (readings JOIN weather_hourly). Mean PM2.5 by IST
--     hour, split by whether it was raining in that hour.
SELECT HOUR(r.ts_ist)          AS hour_ist,
       w.is_rain_hour,
       ROUND(AVG(r.value), 1)  AS mean_pm25,
       COUNT(r.value)          AS n_station_hours
FROM readings AS r
JOIN weather_hourly AS w ON w.ts_ist = r.ts_ist
WHERE r.parameter = 'pm25'
  AND r.value IS NOT NULL
  AND HOUR(r.ts_ist) BETWEEN 17 AND 23
GROUP BY hour_ist, w.is_rain_hour
ORDER BY hour_ist, w.is_rain_hour;


-- Q5: Three-table join (readings JOIN weather_hourly JOIN calendar).
--     Evening PM2.5 by season, on working days vs holidays, rain vs dry.
SELECT c.season,
       c.is_holiday,
       w.is_rain_hour,
       ROUND(AVG(r.value), 1)  AS mean_evening_pm25,
       COUNT(r.value)          AS n_station_hours
FROM readings AS r
JOIN weather_hourly AS w ON w.ts_ist = r.ts_ist
JOIN calendar       AS c ON c.date = DATE(r.ts_ist)
WHERE r.parameter = 'pm25'
  AND r.value IS NOT NULL
  AND HOUR(r.ts_ist) BETWEEN 17 AND 23
GROUP BY c.season, c.is_holiday, w.is_rain_hour
ORDER BY c.season, c.is_holiday, w.is_rain_hour;


-- Q6: The worst festival nights (readings JOIN calendar JOIN stations).
--     Highest PM2.5 hours on festival dates, 18:00-23:59, and how they were classified.
SELECT c.date,
       c.holiday_name,
       s.name,
       HOUR(r.ts_ist)  AS hour_ist,
       r.value_raw     AS pm25,
       r.qc_flag
FROM readings AS r
JOIN calendar AS c ON c.date = DATE(r.ts_ist)
JOIN stations AS s ON s.station_id = r.station_id
WHERE r.parameter = 'pm25'
  AND c.is_festival = 1
  AND HOUR(r.ts_ist) >= 18
  AND r.value_raw IS NOT NULL
ORDER BY r.value_raw DESC
LIMIT 10;


-- Q7: When does the evening peak happen? (window function, MySQL 8)
--     For every station-evening, rank the hours 17:00-23:00 by PM2.5 and keep the
--     highest; then count how often each hour is the peak.
--     (All evenings here; 10_analysis.py repeats this on complete evenings only.)
WITH ranked AS (
    SELECT r.station_id,
           DATE(r.ts_ist)  AS day,
           HOUR(r.ts_ist)  AS hour_ist,
           ROW_NUMBER() OVER (PARTITION BY r.station_id, DATE(r.ts_ist)
                              ORDER BY r.value DESC) AS rank_in_evening
    FROM readings AS r
    WHERE r.parameter = 'pm25'
      AND r.value IS NOT NULL
      AND HOUR(r.ts_ist) BETWEEN 17 AND 23
)
SELECT hour_ist      AS peak_hour_ist,
       COUNT(*)      AS n_station_evenings
FROM ranked
WHERE rank_in_evening = 1
GROUP BY hour_ist
ORDER BY hour_ist;
