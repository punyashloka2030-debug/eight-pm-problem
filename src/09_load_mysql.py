"""
09_load_mysql.py — load the cleaned tables into MySQL, draw the ER diagram, and
run the queries in sql/queries.sql, saving every result.

Input:   data/interim/stations.csv, data/clean/readings_clean.parquet,
         data/clean/weather_hourly.parquet, data/manual/calendar_verified.csv (or draft)
         sql/schema.sql, sql/queries.sql
Output:  the MySQL database `eightpm` (4 tables)
         report/er_diagram.png                  (drawn with matplotlib, no extra tools)
         outputs/tables/mysql_row_counts.csv
         outputs/tables/sql_q1.csv ... sql_q7.csv + sql_query_outputs.md

Needs MySQL running (manual step M2) and its password in .env.

Run:  python src/09_load_mysql.py
"""

import os
import re
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine, text

from common import CLEAN, INTERIM, MANUAL, ROOT, TABLES, ensure_folders

REPORT = ROOT / "report"


def connect():
    """Build the connection from .env (never hard-code passwords)."""
    url = (f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}"
           f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '3306')}"
           f"/{os.getenv('MYSQL_DB')}?charset=utf8mb4&local_infile=1")
    engine = create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar()
    print(f"Connected to MySQL {version}")
    if not version.startswith("8."):
        print("!! Expected MySQL 8.x (window functions in Q7 need it)")
    return engine


def run_sql_file(engine, path):
    """Run every statement in a .sql file, in order (statements end with ';')."""
    sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))  # drop comments
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    print(f"Ran {len(statements)} statements from {path.name}")


# ---------------------------------------------------------------------------
# Prepare each table so its columns match schema.sql exactly
# ---------------------------------------------------------------------------
def stations_table():
    return pd.read_csv(INTERIM / "stations.csv")[
        ["station_id", "name", "lat", "lon", "operator", "openaq_location_id"]]


def readings_table():
    r = pd.read_parquet(CLEAN / "readings_clean.parquet")
    r["is_filled"] = r["is_filled"].astype(int)
    return r[["station_id", "ts_ist", "parameter", "value", "value_raw", "unit", "qc_flag", "is_filled"]]


def weather_table():
    w = pd.read_parquet(CLEAN / "weather_hourly.parquet")
    w["is_rain_hour"] = w["is_rain_hour"].astype("Int64")  # keeps the one missing hour as NULL
    return w[["ts_ist", "precip_mm", "rain_mm", "temp_c", "rh_pct", "wind_kmh", "blh_m", "is_rain_hour"]]


def calendar_table():
    path = MANUAL / "calendar_verified.csv"
    if not path.exists():
        print("!! calendar_verified.csv not found (M6 pending): loading calendar_draft.csv")
        path = MANUAL / "calendar_draft.csv"
    c = pd.read_csv(path, parse_dates=["date"])
    c["date"] = c["date"].dt.date
    for col in ["is_holiday", "is_long_weekend", "is_festival"]:
        c[col] = c[col].astype(int)
    c["holiday_name"] = c["holiday_name"].fillna("")
    return c[["date", "weekday", "is_holiday", "holiday_name", "is_long_weekend", "is_festival", "season"]]


def load_tables(engine):
    """
    Insert in an order that respects the foreign key: stations BEFORE readings.
    to_sql(if_exists='append') fills the tables that schema.sql created, so
    our keys and types are kept (to_sql would otherwise invent its own).
    """
    counts = []
    for name, build in [("stations", stations_table), ("weather_hourly", weather_table),
                        ("calendar", calendar_table), ("readings", readings_table)]:
        started = time.time()
        df = build()
        df.to_sql(name, engine, if_exists="append", index=False, chunksize=10_000, method="multi")
        with engine.connect() as conn:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
        print(f"  {name:15s} {n:>9,} rows  ({time.time() - started:.0f}s)")
        if n != len(df):
            raise SystemExit(f"{name}: loaded {n} rows but the file has {len(df)}")
        counts.append({"table": name, "rows": n, "columns": df.shape[1]})
    pd.DataFrame(counts).to_csv(TABLES / "mysql_row_counts.csv", index=False)


def run_queries(engine):
    """Run each '-- Qn:' block in queries.sql and save its result."""
    text_all = (ROOT / "sql" / "queries.sql").read_text(encoding="utf-8")
    blocks = re.split(r"(?=^-- Q\d+:)", text_all, flags=re.MULTILINE)
    report = ["# SQL query outputs (from sql/queries.sql, run by 09_load_mysql.py)", ""]

    for block in blocks:
        match = re.match(r"-- (Q\d+): ([^\n]*)", block)
        if not match:
            continue
        qid, title = match.groups()
        sql = re.sub(r"--[^\n]*", "", block).strip().rstrip(";")
        with engine.connect() as conn:
            result = pd.read_sql(text(sql), conn)
        result.to_csv(TABLES / f"sql_{qid.lower()}.csv", index=False)
        print(f"  {qid}: {len(result)} rows  ({title[:60]})")
        report += [f"## {qid}: {title}", "", "```sql", sql, "```", "",
                   result.head(30).to_markdown(index=False), ""]

    (TABLES / "sql_query_outputs.md").write_text("\n".join(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# ER diagram (matplotlib: no Graphviz or Mermaid install needed)
# ---------------------------------------------------------------------------
TABLE_BOXES = {
    # name: (x, y_top, [columns])  — PK / FK marked in the text
    "stations": (0.02, 0.80, ["PK station_id", "name", "lat", "lon", "operator", "openaq_location_id"]),
    "readings": (0.39, 0.88, ["PK,FK station_id", "PK ts_ist", "PK parameter", "value", "value_raw",
                              "unit", "qc_flag", "is_filled"]),
    "weather_hourly": (0.76, 0.97, ["PK ts_ist", "precip_mm", "rain_mm", "temp_c", "rh_pct",
                                    "wind_kmh", "blh_m", "is_rain_hour"]),
    "calendar": (0.76, 0.48, ["PK date", "weekday", "is_holiday", "holiday_name",
                              "is_long_weekend", "is_festival", "season"]),
}
LINE_H = 0.05
BOX_W = 0.22


def column_y(table, column_index):
    """Vertical middle of one column's row inside a table box."""
    _, top, _ = TABLE_BOXES[table]
    return top - LINE_H * (column_index + 1.5)


def draw_er_diagram():
    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # 1. One box per table: grey header with the name, one line per column.
    for name, (x, top, cols) in TABLE_BOXES.items():
        height = LINE_H * (len(cols) + 1)
        ax.add_patch(plt.Rectangle((x, top - height), BOX_W, height, fill=False, lw=1.2))
        ax.add_patch(plt.Rectangle((x, top - LINE_H), BOX_W, LINE_H, color="0.85"))
        ax.text(x + 0.01, top - LINE_H / 2, name, va="center", weight="bold", fontsize=10)
        for i, col in enumerate(cols):
            ax.text(x + 0.01, column_y(name, i), col, va="center", fontsize=8.5, family="monospace")

    # 2. Lines between the KEY COLUMNS themselves, with a short label in the gap.
    def link(table_a, col_a, table_b, col_b, label, dashed):
        xa = TABLE_BOXES[table_a][0] + BOX_W
        xb = TABLE_BOXES[table_b][0]
        ya, yb = column_y(table_a, col_a), column_y(table_b, col_b)
        ax.plot([xa, xb], [ya, yb], color="black", lw=1.2, ls="--" if dashed else "-")
        ax.text((xa + xb) / 2, (ya + yb) / 2 + 0.025, label, ha="center", va="bottom",
                fontsize=7.5, style="italic", linespacing=1.1,
                bbox=dict(facecolor="white", edgecolor="none", pad=1))

    link("stations", 0, "readings", 0, "1 : many\nFOREIGN KEY", dashed=False)
    link("readings", 1, "weather_hourly", 0, "many : 1\nsame ts_ist", dashed=True)
    link("readings", 1, "calendar", 0, "many : 1\nDATE(ts_ist) = date", dashed=True)

    ax.text(0.02, 0.03, "Solid line = enforced foreign key.  Dashed = join key without a constraint "
            "(a few reading hours have no weather row).", fontsize=8.5)
    ax.set_title("ER diagram: Bengaluru air quality database (MySQL 8)", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(REPORT / "er_diagram.png", dpi=150)
    plt.close(fig)
    print("ER diagram saved to report/er_diagram.png")


def main():
    ensure_folders()
    draw_er_diagram()
    engine = connect()
    run_sql_file(engine, ROOT / "sql" / "schema.sql")
    print("Loading tables:")
    load_tables(engine)
    print("Running queries:")
    run_queries(engine)


if __name__ == "__main__":
    main()
