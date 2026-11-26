"""
00_spark_hello.py — the M3 check: can this laptop start Spark at all?

If this prints a small table and "Spark OK", Java and PySpark are installed
correctly and 08_spark_job.py will be able to run.

Run:  python src/00_spark_hello.py
"""

from pyspark.sql import SparkSession

# local[*] = run Spark on this laptop, using every CPU core. No cluster needed.
spark = SparkSession.builder.master("local[*]").appName("hello").getOrCreate()

# Three fake rows, only to prove Spark can build and count a DataFrame.
df = spark.createDataFrame([(1, "a"), (2, "b"), (3, "c")], ["n", "letter"])
df.show()
print("Rows:", df.count())
print("Spark version:", spark.version, "| Spark OK")

spark.stop()
