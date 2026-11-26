"""
08_spark_job.py — the big-data step: load, clean, resample, join and aggregate
the largest table (readings, 279,552 rows) with PySpark, printing and saving the
row count after every stage.

Input:   data/clean/readings_clean.parquet   (from 07)
         data/clean/weather_hourly.parquet   (from 07)
         data/manual/calendar_verified.csv   (or calendar_draft.csv until M6)
Output:  data/clean/spark_pm25_station_hour/          PM2.5 station-hour ⋈ weather ⋈ calendar (parquet folder)
         outputs/tables/spark_row_counts.csv          rows after every stage (report appendix)
         outputs/tables/spark_pm25_hour_weekday.csv   168 rows: the heatmap data
         outputs/tables/spark_pm25_month_hour.csv     month x hour
         outputs/tables/spark_pm25_rain_hour.csv      rain vs dry, by hour

Why Spark here? 280k rows fit in pandas on a laptop, so honestly Spark is not
REQUIRED at this size. We use it because the same code runs unchanged on a
cluster when the data grows: more stations, 15-minute data, more years. The
V profile in the report says this plainly.

The same stages run cell by cell in notebooks/spark_job.ipynb.

Run:  python src/08_spark_job.py
"""

import time

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from common import CLEAN, MANUAL, TABLES, ensure_folders, log_decision, reset_cleaning_log_for_stage

STAGE = "08_spark_job"
FAILURE_FLAGS = ["sentinel", "out_of_range", "negative", "zero", "flatline", "spike", "failure_reviewed"]

ROW_COUNTS = []  # one entry per stage, saved at the end


def start_spark():
    """
    local[*] = run on this laptop with every CPU core.
    The session time zone is set to IST so Spark never shifts our IST
    timestamps (they are stored without a zone, as TIMESTAMP_NTZ).
    """
    spark = (SparkSession.builder.master("local[*]")
             .appName("eight-pm-problem")
             .config("spark.sql.session.timeZone", "Asia/Kolkata")
             .config("spark.sql.shuffle.partitions", "8")  # small data: fewer, bigger tasks
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def record(stage, description, df, started):
    """Count rows (this forces Spark to actually run the stage) and remember it."""
    rows = df.count()
    seconds = round(time.time() - started, 1)
    ROW_COUNTS.append({"stage": stage, "description": description, "rows": rows, "seconds": seconds})
    print(f"  [{stage}] {description}: {rows:,} rows ({seconds}s)")
    return rows


def to_pandas_small(df):
    """
    Bring a SMALL Spark result back as a pandas table.
    We build it from plain Python rows instead of df.toPandas(), because PySpark
    warns that its pandas bridge does not fully support pandas 3 yet.
    """
    return pd.DataFrame([row.asDict() for row in df.collect()])


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------
def stage_load(spark):
    t = time.time()
    readings = spark.read.parquet(str(CLEAN / "readings_clean.parquet"))
    record("1_load", "Load readings_clean (full station x parameter x hour grid)", readings, t)
    return readings


def stage_clean(readings):
    """Keep only usable values: drop empty hours and every sensor-failure flag."""
    t = time.time()
    before = readings.count()
    clean = readings.filter(F.col("value").isNotNull() & ~F.col("qc_flag").isin(FAILURE_FLAGS))
    after = record("2_clean", "Drop missing hours and QC failures (real events kept)", clean, t)
    log_decision(STAGE, "Rows with no usable value (never sent, or blanked as a sensor failure)",
                 before - after, "Filtered out in Spark before aggregating",
                 "An empty or failed reading must not pull averages towards zero")
    return clean


def stage_resample(clean):
    """
    Resample to exactly one value per station x parameter x hour.
    date_trunc('hour') puts every reading on the start of its hour; avg()
    combines anything that lands in the same hour. Our OpenAQ data is already
    hourly, so the row count should not change: that is a check, and this is
    the step where 15-minute CPCB files would be turned into hours.

    Careful: date_trunc returns a time-zone-AWARE timestamp, even when given a
    zone-free one. Saved to a file, that would shift every hour by 5.5 h when
    pandas reads it back. .cast("timestamp_ntz") keeps it zone-free (plain IST).
    """
    t = time.time()
    hourly = (clean
              .withColumn("ts_hour", F.date_trunc("hour", F.col("ts_ist")).cast("timestamp_ntz"))
              .groupBy("station_id", "parameter", "ts_hour")
              .agg(F.avg("value").alias("value"),
                   F.count("*").alias("n_readings"),
                   F.max(F.col("is_filled").cast("int")).alias("is_filled")))
    record("3_resample", "Resample to hourly (date_trunc + avg) per station x parameter", hourly, t)
    return hourly


def stage_join(spark, hourly):
    """PM2.5 station-hours ⋈ weather (on the IST hour) ⋈ calendar (on the date)."""
    t = time.time()
    pm25 = hourly.filter(F.col("parameter") == "pm25")
    record("4a_pm25", "PM2.5 station-hours only", pm25, t)

    weather = (spark.read.parquet(str(CLEAN / "weather_hourly.parquet"))
               .withColumnRenamed("ts_ist", "ts_hour"))

    calendar_file = MANUAL / "calendar_verified.csv"
    if not calendar_file.exists():
        calendar_file = MANUAL / "calendar_draft.csv"
    calendar = (spark.read.option("header", True).option("inferSchema", True).csv(str(calendar_file))
                .select(F.to_date("date").alias("date"), "is_holiday", "is_festival",
                        "is_long_weekend", "season", "holiday_name"))

    t = time.time()
    joined = (pm25
              .join(weather, on="ts_hour", how="left")
              .withColumn("date", F.to_date("ts_hour"))
              .join(calendar, on="date", how="left")
              .withColumn("hour", F.hour("ts_hour"))
              # Spark's dayofweek: Sunday=1 ... Saturday=7. We want Monday=0 ... Sunday=6.
              .withColumn("weekday_num", (F.dayofweek("ts_hour") + 5) % 7)
              .withColumn("weekday", F.date_format("ts_hour", "EEEE"))
              .withColumn("month", F.date_format("ts_hour", "yyyy-MM")))
    rows = record("4b_join", "PM2.5 ⋈ weather_hourly ⋈ calendar (left joins)", joined, t)

    no_weather = joined.filter(F.col("temp_c").isNull()).count()
    no_calendar = joined.filter(F.col("season").isNull()).count()
    log_decision(STAGE, "Joining PM2.5 hours to weather and calendar", no_weather + no_calendar,
                 f"Left joins keep all {rows:,} PM2.5 rows; rows_affected = rows that found no "
                 f"weather ({no_weather}) or no calendar day ({no_calendar})",
                 "A left join never silently drops air-quality hours; unmatched rows are counted")

    joined.write.mode("overwrite").parquet(str(CLEAN / "spark_pm25_station_hour"))

    # Check: the hour pandas sees in the saved file must equal the hour Spark computed.
    saved = pd.read_parquet(CLEAN / "spark_pm25_station_hour", columns=["ts_hour", "hour"])
    shifted = int((saved["ts_hour"].dt.hour != saved["hour"]).sum())
    if shifted:
        raise SystemExit(f"{shifted} rows changed hour when saved: time-zone bug, stop here")
    print("  Check passed: saved timestamps read back with the same IST hour")
    return joined


def stage_aggregate(joined):
    """The three tables the charts need."""
    results = {}

    t = time.time()
    hour_weekday = (joined.groupBy("weekday_num", "weekday", "hour")
                    .agg(F.round(F.avg("value"), 1).alias("mean_pm25"),
                         F.count("*").alias("n_station_hours"))
                    .orderBy("weekday_num", "hour"))
    record("5a_hour_weekday", "GROUP BY weekday x hour (heatmap)", hour_weekday, t)
    results["spark_pm25_hour_weekday.csv"] = hour_weekday

    t = time.time()
    month_hour = (joined.groupBy("month", "hour")
                  .agg(F.round(F.avg("value"), 1).alias("mean_pm25"),
                       F.count("*").alias("n_station_hours"))
                  .orderBy("month", "hour"))
    record("5b_month_hour", "GROUP BY month x hour", month_hour, t)
    results["spark_pm25_month_hour.csv"] = month_hour

    t = time.time()
    rain_hour = (joined.filter(F.col("is_rain_hour").isNotNull())
                 .groupBy("is_rain_hour", "hour")
                 .agg(F.round(F.avg("value"), 1).alias("mean_pm25"),
                      F.count("*").alias("n_station_hours"))
                 .orderBy("is_rain_hour", "hour"))
    record("5c_rain_hour", "GROUP BY rain/dry x hour", rain_hour, t)
    results["spark_pm25_rain_hour.csv"] = rain_hour

    for name, df in results.items():
        to_pandas_small(df).to_csv(TABLES / name, index=False)
    return results


def main():
    ensure_folders()
    reset_cleaning_log_for_stage(STAGE)
    spark = start_spark()
    print(f"Spark {spark.version}, {spark.sparkContext.defaultParallelism} cores")

    readings = stage_load(spark)
    clean = stage_clean(readings)
    hourly = stage_resample(clean)
    joined = stage_join(spark, hourly)
    stage_aggregate(joined)

    pd.DataFrame(ROW_COUNTS).to_csv(TABLES / "spark_row_counts.csv", index=False)
    print("\nRow counts saved to outputs/tables/spark_row_counts.csv")
    spark.stop()


if __name__ == "__main__":
    main()
