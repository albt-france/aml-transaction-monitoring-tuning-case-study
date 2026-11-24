"""Spark equivalent of two key aggregations, to show the pipeline is not tied to Dask/DuckDB.

    python src/spark_equivalent.py

Runs on Spark 3.5 (pip install pyspark==3.5.*) with Java 8, 11 or 17. It reads the same Parquet files written by
src/ingest_dask.py and checks that Spark gives the same numbers as the SQL layer:
  1. rows and laundering rows per payment format   (vs output/profile_formats.csv, IBM rows of the window)
  2. rows per day                                   (vs output/profile_daily.csv)
Result: output/spark_check.csv. If Spark cannot start, the script says so and exits without failing the pipeline.
On Windows without winutils.exe, Spark cannot read local Parquet directly: the script then loads the three needed
columns with pyarrow and hands them to Spark through Arrow (the aggregations still run in Spark).
"""
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"


def main():
    try:
        from pyspark.sql import SparkSession, functions as F
    except ImportError:
        print("pyspark is not installed: pip install pyspark==3.5.* (needs Java 8, 11 or 17)")
        return
    t0 = time.perf_counter()
    try:
        spark = (SparkSession.builder.master("local[*]").appName("aml-case-study")
                 .config("spark.driver.memory", "6g").config("spark.ui.enabled", "false")
                 .config("spark.sql.execution.arrow.pyspark.enabled", "true").getOrCreate())
    except Exception as e:  # Java missing or incompatible
        print("Spark could not start:", str(e).splitlines()[0])
        return
    spark.sparkContext.setLogLevel("ERROR")
    path = ROOT / "data" / "parquet" / "trans"
    try:
        df = spark.read.parquet(str(path))
        df.limit(1).count()
        source = "spark.read.parquet"
    except Exception:
        # Windows without winutils.exe / hadoop.dll: Spark cannot use the local Hadoop file system.
        # Load the three needed columns with pyarrow and hand them to Spark through Arrow instead.
        import pyarrow.dataset as ds
        tbl = ds.dataset(str(path), format="parquet", partitioning="hive").to_table(columns=["day", "payment_format", "is_laundering"])
        df = spark.createDataFrame(tbl.to_pandas())
        source = "pyarrow -> Spark (Arrow)"
    daily = df.groupBy("day").agg(F.count("*").alias("n_rows")).toPandas()
    daily["day"] = pd.to_datetime(daily.day).dt.strftime("%Y-%m-%d")
    po = pd.read_csv(OUT / "profile_overview.csv").iloc[0]
    first, last = str(po.first_day), str(po.last_complete_day)
    win = df.where((F.col("day") >= first) & (F.col("day") <= last))
    fmt = win.groupBy("payment_format").agg(F.count("*").alias("n_rows"), F.sum("is_laundering").alias("laundering_rows")).toPandas()
    secs = time.perf_counter() - t0
    spark.stop()
    ref_d = pd.read_csv(OUT / "profile_daily.csv")
    ref_d["day"] = pd.to_datetime(ref_d.day).dt.strftime("%Y-%m-%d")
    ref_f = pd.read_csv(OUT / "profile_formats.csv")
    m1 = daily.merge(ref_d[["day", "n_rows"]], on="day", suffixes=("_spark", "_sql"))
    m2 = fmt.merge(ref_f[["payment_format", "n_rows", "laundering_rows"]], on="payment_format", suffixes=("_spark", "_sql"))
    check = pd.DataFrame([
        {"aggregation": "rows per day", "groups": len(m1), "all_equal": bool((m1.n_rows_spark == m1.n_rows_sql).all())},
        {"aggregation": "rows and laundering rows per format (window)", "groups": len(m2),
         "all_equal": bool((m2.n_rows_spark == m2.n_rows_sql).all() and (m2.laundering_rows_spark == m2.laundering_rows_sql).all())},
    ])
    check["spark_seconds"] = round(secs, 1)
    check["input"] = source
    check.to_csv(OUT / "spark_check.csv", index=False)
    print(check.to_string(index=False))
    if not check.all_equal.all():
        sys.exit("Spark and SQL disagree")


if __name__ == "__main__":
    main()
