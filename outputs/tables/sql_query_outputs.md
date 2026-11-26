# SQL query outputs (from sql/queries.sql, run by 09_load_mysql.py)

## Q1: How big is each table? (the V profile quotes these numbers)

```sql
SELECT 'stations' AS table_name, COUNT(*) AS n_rows FROM stations
UNION ALL SELECT 'readings', COUNT(*) FROM readings
UNION ALL SELECT 'weather_hourly', COUNT(*) FROM weather_hourly
UNION ALL SELECT 'calendar', COUNT(*) FROM calendar
```

| table_name     |   n_rows |
|:---------------|---------:|
| stations       |        7 |
| readings       |   279552 |
| weather_hourly |     9984 |
| calendar       |      416 |

## Q2: Gaps per station (JOIN + GROUP BY). How many PM2.5 hours have no usable value?

```sql
SELECT s.name,
       COUNT(*)                                          AS hours_in_range,
       SUM(r.value IS NULL)                              AS hours_without_value,
       ROUND(100 * SUM(r.value IS NULL) / COUNT(*), 1)   AS pct_without_value
FROM readings AS r
JOIN stations AS s ON s.station_id = r.station_id
WHERE r.parameter = 'pm25'
GROUP BY s.name
ORDER BY pct_without_value DESC
```

| name                                   |   hours_in_range |   hours_without_value |   pct_without_value |
|:---------------------------------------|-----------------:|----------------------:|--------------------:|
| Peenya, Bengaluru - CPCB               |             9984 |                  4097 |                41   |
| BTM Layout, Bengaluru - CPCB           |             9984 |                  2884 |                28.9 |
| Bapuji Nagar, Bengaluru - KSPCB        |             9984 |                  2519 |                25.2 |
| Silk Board, Bengaluru - KSPCB          |             9984 |                  1604 |                16.1 |
| Hebbal, Bengaluru - KSPCB              |             9984 |                  1540 |                15.4 |
| Hombegowda Nagar, Bengaluru - KSPCB    |             9984 |                  1132 |                11.3 |
| Jayanagar 5th Block, Bengaluru - KSPCB |             9984 |                   966 |                 9.7 |

## Q3: The heatmap in SQL (GROUP BY hour x weekday). Mean PM2.5 for each weekday

```sql
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
ORDER BY weekday_num, hour_ist
```

|   weekday_num | weekday   |   hour_ist |   mean_pm25 |   n_station_hours |
|--------------:|:----------|-----------:|------------:|------------------:|
|             0 | Monday    |         17 |        29.7 |               315 |
|             0 | Monday    |         18 |        33.2 |               323 |
|             0 | Monday    |         19 |        37.1 |               327 |
|             0 | Monday    |         20 |        39   |               326 |
|             0 | Monday    |         21 |        39.7 |               320 |
|             0 | Monday    |         22 |        39.9 |               324 |
|             0 | Monday    |         23 |        37.4 |               319 |
|             1 | Tuesday   |         17 |        30.6 |               339 |
|             1 | Tuesday   |         18 |        32.5 |               334 |
|             1 | Tuesday   |         19 |        35.3 |               331 |
|             1 | Tuesday   |         20 |        38.1 |               324 |
|             1 | Tuesday   |         21 |        39.2 |               321 |
|             1 | Tuesday   |         22 |        39.1 |               321 |
|             1 | Tuesday   |         23 |        37.1 |               321 |
|             2 | Wednesday |         17 |        30.5 |               348 |
|             2 | Wednesday |         18 |        32.5 |               353 |
|             2 | Wednesday |         19 |        33.9 |               354 |
|             2 | Wednesday |         20 |        35.9 |               354 |
|             2 | Wednesday |         21 |        35.3 |               351 |
|             2 | Wednesday |         22 |        33.8 |               352 |
|             2 | Wednesday |         23 |        32.2 |               343 |
|             3 | Thursday  |         17 |        27.9 |               341 |
|             3 | Thursday  |         18 |        30   |               338 |
|             3 | Thursday  |         19 |        32.8 |               336 |
|             3 | Thursday  |         20 |        34.2 |               336 |
|             3 | Thursday  |         21 |        33.7 |               334 |
|             3 | Thursday  |         22 |        33   |               340 |
|             3 | Thursday  |         23 |        32.6 |               337 |
|             4 | Friday    |         17 |        28.3 |               350 |
|             4 | Friday    |         18 |        32.4 |               350 |

## Q4: Rainy vs dry evening hours (readings JOIN weather_hourly). Mean PM2.5 by IST

```sql
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
ORDER BY hour_ist, w.is_rain_hour
```

|   hour_ist |   is_rain_hour |   mean_pm25 |   n_station_hours |
|-----------:|---------------:|------------:|------------------:|
|         17 |              0 |        32.8 |              1687 |
|         17 |              1 |        20.5 |               642 |
|         18 |              0 |        34.5 |              1911 |
|         18 |              1 |        20.8 |               428 |
|         19 |              0 |        37.3 |              1977 |
|         19 |              1 |        21.7 |               358 |
|         20 |              0 |        38.7 |              2057 |
|         20 |              1 |        22.7 |               260 |
|         21 |              0 |        38.9 |              2041 |
|         21 |              1 |        22.7 |               248 |
|         22 |              0 |        37.4 |              2119 |
|         22 |              1 |        20.7 |               179 |
|         23 |              0 |        36.3 |              2023 |
|         23 |              1 |        22.5 |               280 |

## Q5: Three-table join (readings JOIN weather_hourly JOIN calendar).

```sql
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
ORDER BY c.season, c.is_holiday, w.is_rain_hour
```

| season       |   is_holiday |   is_rain_hour |   mean_evening_pm25 |   n_station_hours |
|:-------------|-------------:|---------------:|--------------------:|------------------:|
| post_monsoon |            0 |              0 |                39.4 |              3352 |
| post_monsoon |            0 |              1 |                23.1 |               583 |
| post_monsoon |            1 |              0 |                41.1 |              1625 |
| post_monsoon |            1 |              1 |                26.8 |               276 |
| pre_monsoon  |            0 |              0 |                43.7 |              2121 |
| pre_monsoon  |            0 |              1 |                30   |               142 |
| pre_monsoon  |            1 |              0 |                43.8 |              1260 |
| pre_monsoon  |            1 |              1 |                28.4 |                79 |
| sw_monsoon   |            0 |              0 |                22   |              2225 |
| sw_monsoon   |            0 |              1 |                18.3 |               973 |
| sw_monsoon   |            1 |              0 |                20.6 |              1088 |
| sw_monsoon   |            1 |              1 |                16.7 |               322 |
| winter       |            0 |              0 |                42.1 |              1516 |
| winter       |            0 |              1 |                53.2 |                14 |
| winter       |            1 |              0 |                39   |               628 |
| winter       |            1 |              1 |                18.6 |                 6 |

## Q6: The worst festival nights (readings JOIN calendar JOIN stations).

```sql
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
LIMIT 10
```

| date       | holiday_name                               | name                                   |   hour_ist |   pm25 | qc_flag             |
|:-----------|:-------------------------------------------|:---------------------------------------|-----------:|-------:|:--------------------|
| 2026-11-08 | Naraka Chaturdashi / Deepavali             | Silk Board, Bengaluru - KSPCB          |         21 |    355 | real_event_festival |
| 2026-11-08 | Naraka Chaturdashi / Deepavali             | Silk Board, Bengaluru - KSPCB          |         22 |    304 | real_event_festival |
| 2026-11-08 | Naraka Chaturdashi / Deepavali             | Silk Board, Bengaluru - KSPCB          |         23 |    302 | real_event_festival |
| 2026-11-08 | Naraka Chaturdashi / Deepavali             | Silk Board, Bengaluru - KSPCB          |         20 |    285 | real_event_festival |
| 2026-11-08 | Naraka Chaturdashi / Deepavali             | Jayanagar 5th Block, Bengaluru - KSPCB |         20 |    251 | real_event_festival |
| 2026-11-09 | Deepavali (Lakshmi Pooja / Govardhan Puja) | Jayanagar 5th Block, Bengaluru - KSPCB |         20 |    250 | real_event_festival |
| 2026-11-09 | Deepavali (Lakshmi Pooja / Govardhan Puja) | Jayanagar 5th Block, Bengaluru - KSPCB |         19 |    244 | real_event_festival |
| 2026-11-09 | Deepavali (Lakshmi Pooja / Govardhan Puja) | Hebbal, Bengaluru - KSPCB              |         21 |    226 | real_event_festival |
| 2025-10-21 | Deepavali (Lakshmi Pooja / Amavasya)       | Jayanagar 5th Block, Bengaluru - KSPCB |         21 |    221 | real_event_festival |
| 2026-11-10 | Balipadyami, Deepavali                     | Jayanagar 5th Block, Bengaluru - KSPCB |         22 |    216 | real_event_festival |

## Q7: When does the evening peak happen? (window function, MySQL 8)

```sql
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
ORDER BY hour_ist
```

|   peak_hour_ist |   n_station_evenings |
|----------------:|---------------------:|
|              17 |                  326 |
|              18 |                  226 |
|              19 |                  311 |
|              20 |                  468 |
|              21 |                  400 |
|              22 |                  306 |
|              23 |                  387 |
