-- schema.sql — the relational version of our data (MySQL 8).
-- Run by src/09_load_mysql.py, which drops and recreates every table so that
-- `make mysql` always rebuilds the database from the cleaned files.
--
-- Four tables:
--   stations        one row per monitoring station                 (7 rows)
--   readings        one row per station x IST hour x pollutant     (the largest table)
--   weather_hourly  one row per IST hour, city-wide                (about 10,000 rows)
--   calendar        one row per date                               (416 rows)
--
-- How they link:
--   readings.station_id  -> stations.station_id   (a real FOREIGN KEY)
--   readings.ts_ist      ~  weather_hourly.ts_ist  (join on the same IST hour)
--   DATE(readings.ts_ist) ~ calendar.date          (join on the day)
-- The last two are joins but not foreign keys: a few reading hours have no
-- weather row (the first hours of 1 Oct 2025), and a foreign key would reject them.

DROP TABLE IF EXISTS readings;
DROP TABLE IF EXISTS stations;
DROP TABLE IF EXISTS weather_hourly;
DROP TABLE IF EXISTS calendar;

CREATE TABLE stations (
    station_id          VARCHAR(16)   NOT NULL,   -- our key, e.g. 'BLR6973' (stable even when OpenAQ sensor ids change)
    name                VARCHAR(100)  NOT NULL,
    lat                 DECIMAL(9,6),
    lon                 DECIMAL(9,6),
    operator            VARCHAR(60),               -- KSPCB or CPCB
    openaq_location_id  INT           NOT NULL,
    PRIMARY KEY (station_id)
);

CREATE TABLE readings (
    station_id      VARCHAR(16)   NOT NULL,
    ts_ist          DATETIME      NOT NULL,        -- start of the hour, Indian Standard Time
    parameter       VARCHAR(8)    NOT NULL,        -- pm25, pm10, no2, co
    value           DOUBLE        NULL,            -- cleaned value; NULL = gap or sensor failure
    value_raw       DOUBLE        NULL,            -- value as received (after unit conversion)
    unit            VARCHAR(8)    NOT NULL,        -- µg/m³ (CO: mg/m³)
    qc_flag         VARCHAR(24)   NOT NULL,        -- ok, missing, zero, flatline, real_event_festival, ...
    is_filled       TINYINT(1)    NOT NULL,        -- 1 = forward-filled (<= 3 h), not measured
    PRIMARY KEY (station_id, ts_ist, parameter),   -- composite key: one value per station, hour and pollutant
    CONSTRAINT fk_readings_station FOREIGN KEY (station_id) REFERENCES stations (station_id),
    INDEX idx_readings_ts (ts_ist)                 -- speeds up joins on the hour
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE weather_hourly (
    ts_ist        DATETIME   NOT NULL,             -- start of the IST hour (aligned in 06_time_and_types.py)
    precip_mm     DOUBLE,
    rain_mm       DOUBLE,
    temp_c        DOUBLE,
    rh_pct        DOUBLE,
    wind_kmh      DOUBLE,
    blh_m         DOUBLE,                          -- boundary-layer height, metres
    is_rain_hour  TINYINT(1),                      -- 1 if precip_mm >= 0.1
    PRIMARY KEY (ts_ist)
);

CREATE TABLE calendar (
    date             DATE          NOT NULL,
    weekday          VARCHAR(9)    NOT NULL,
    is_holiday       TINYINT(1)    NOT NULL,       -- weekend or Karnataka general holiday
    holiday_name     VARCHAR(80),
    is_long_weekend  TINYINT(1)    NOT NULL,
    is_festival      TINYINT(1)    NOT NULL,
    season           VARCHAR(16)   NOT NULL,       -- winter, pre_monsoon, sw_monsoon, post_monsoon
    PRIMARY KEY (date)
);
