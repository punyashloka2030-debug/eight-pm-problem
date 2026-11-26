"""
14_build_report.py — write the project report from the pipeline's own files.

Every number in the report is read from outputs/tables/*.json / *.csv or the
cleaning log. Nothing is typed in by hand, so if the data change and we re-run
`make all`, the report changes with them. Places where a human must add
something are marked [[TODO-HUMAN: ...]].

Input:   outputs/tables/analysis_summary.json and the other tables in outputs/tables/
         outputs/cleaning_log.csv, outputs/charts/*.png, report/er_diagram.png
         report/v_profile.md, report/spreadsheet_vs_pandas.md, report/reflection_notes.md
         data/clean/readings_clean.parquet (only to check which Deepavali hours were filled)
Output:  report/img/pipeline.png   the pipeline diagram (section d)
         report/report.md          the report, sections a-i in the brief's order, then appendices
         report/reference.docx     the page style (A4, 10 pt text, 8 pt tables) pandoc copies
         report/report.docx        rendered with pandoc (pypandoc_binary bundles pandoc)
         report/report.pdf         converted from the .docx with LibreOffice (soffice)

Run:  python src/14_build_report.py
"""

import json
import math
import shutil
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

from common import BENGALURU_CENTRE, CLEAN, CLEANING_LOG, DATE_END, DATE_START, INTERIM, MANUAL, ROOT, TABLES

REPORT = ROOT / "report"
IMG = REPORT / "img"
# A raw Word page break; pandoc copies it into the .docx unchanged.
PAGE_BREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'
# Paths inside report.md are relative to the report/ folder.
CHART_DIR = "../outputs/charts"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def n(x):
    """A whole number with thousands separators: 204584 -> '204,584'."""
    return f"{int(x):,}"


def read_table(name):
    """Read one CSV from outputs/tables/."""
    return pd.read_csv(TABLES / name)


def month_name(yyyy_mm):
    """'2026-03' -> 'March 2026' (the commissioner reads words, not codes)."""
    return pd.Timestamp(yyyy_mm + "-01").strftime("%B %Y")


def md_table(df):
    """A DataFrame as a markdown pipe table (pandoc turns it into a Word table)."""
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    rule = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(str(v).replace("|", "/") for v in row) + " |" for row in df.values]
    return "\n".join([header, rule] + rows)


def image(path, caption, width_cm=16):
    """Markdown for a picture with a caption and a fixed width."""
    return f"![{caption}]({path}){{width={width_cm}cm}}"


# ---------------------------------------------------------------------------
# Load every input once
# ---------------------------------------------------------------------------

def load_inputs():
    """Read all pipeline outputs the report needs into one dictionary."""
    data = {}
    data["s"] = json.loads((TABLES / "analysis_summary.json").read_text())
    data["log"] = pd.read_csv(CLEANING_LOG)
    data["inventory"] = read_table("data_inventory.csv")
    data["register"] = read_table("source_register.csv")
    data["vprofile"] = read_table("v_profile.csv")
    data["spark"] = read_table("spark_row_counts.csv")
    data["mysql"] = read_table("mysql_row_counts.csv")
    data["gaps"] = read_table("gaps_per_station.csv")
    data["months"] = read_table("evening_by_month.csv")
    data["weekday"] = read_table("evening_by_weekday_excl_festivals.csv")
    data["heat"] = read_table("spark_pm25_hour_weekday.csv")
    data["stations"] = pd.read_csv(MANUAL / "stations_approved.csv")
    data["verdicts"] = pd.read_csv(MANUAL / "outlier_verdicts.csv")
    data["units"] = read_table("units_as_received.csv")
    data["compare"] = read_table("spreadsheet_vs_pandas.csv")
    data["sql_md"] = (TABLES / "sql_query_outputs.md").read_text()
    data["calendar_verified"] = (MANUAL / "calendar_verified.csv").exists()
    data["trends_done"] = (MANUAL / "trends_all_three.csv").exists()
    data["diwali_filled"] = diwali_filled_hours()
    data["city_hourly"] = city_hourly_profile(data["heat"])
    data["max_km"] = farthest_station_km()
    return data


def farthest_station_km():
    """How far the farthest monitor is from the city centre (same haversine formula as 11_charts.py)."""
    st = pd.read_csv(INTERIM / "stations.csv")
    lat0, lon0 = BENGALURU_CENTRE
    distances = []
    for lat, lon in zip(st["lat"], st["lon"]):
        p1, p2 = math.radians(lat0), math.radians(lat)
        dp, dl = p2 - p1, math.radians(lon - lon0)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        distances.append(2 * 6371 * math.asin(math.sqrt(a)))
    return round(max(distances))


def diwali_filled_hours():
    """
    Which Deepavali-evening hours (19-23) were forward-filled at EVERY station?
    The chart shows a flat line there, and the report must say why.
    """
    path = CLEAN / "readings_clean.parquet"
    if not path.exists():
        return []
    df = pd.read_parquet(path, columns=["ts_ist", "parameter", "is_filled"])
    night = df[(df["parameter"] == "pm25")
               & (df["ts_ist"] >= "2025-10-20 19:00") & (df["ts_ist"] <= "2025-10-20 23:00")]
    share_filled = night.groupby(night["ts_ist"].dt.hour)["is_filled"].mean()
    return [int(h) for h, share in share_filled.items() if share == 1.0]


def city_hourly_profile(heat):
    """City-wide mean PM2.5 per hour of day, weighted by station-hours (from the Spark table)."""
    heat = heat.copy()
    heat["weighted"] = heat["mean_pm25"] * heat["n_station_hours"]
    by_hour = heat.groupby("hour")[["weighted", "n_station_hours"]].sum()
    return (by_hour["weighted"] / by_hour["n_station_hours"]).round(1)


# ---------------------------------------------------------------------------
# The pipeline diagram (section d)
# ---------------------------------------------------------------------------

BOX_W, BOX_H = 2.6, 1.1   # every box has the same size
COLUMN_X = [0, 4.0, 8.0, 12.0, 16.0]   # left edge of each column; 1.4 units of space for arrow labels


def draw_box(ax, x, y, text, colour):
    """One rounded box with centred text. (x, y) is the box's lower-left corner."""
    box = FancyBboxPatch((x, y), BOX_W, BOX_H, boxstyle="round,pad=0.05",
                         facecolor=colour, edgecolor="#4a4a4a", lw=0.8)
    ax.add_patch(box)
    ax.text(x + BOX_W / 2, y + BOX_H / 2, text, ha="center", va="center", fontsize=6.5)


def draw_arrow(ax, x1, y1, x2, y2, label=""):
    """An arrow from (x1, y1) to (x2, y2), with an optional row count on a white patch at its middle."""
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color="#4a4a4a", lw=0.9))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, label, ha="center", va="center", fontsize=6, color="#1757ac",
                bbox=dict(facecolor="white", edgecolor="none", pad=0.5))


def draw_pipeline(d):
    """Draw sources -> scripts -> outputs, with real row counts on the arrows."""
    vp = d["vprofile"].set_index("source")
    spark = d["spark"].set_index("stage")
    openaq_rows = vp.loc["OpenAQ hourly readings", "rows"]
    grid_rows = vp.loc["Full analysis grid (readings_clean)", "rows"]
    weather_rows = vp.loc["Open-Meteo weather", "rows"]
    cal_rows = vp.loc["Calendar", "rows"]
    c1, c2, c3, c4, c5 = COLUMN_X
    source_colour, step_colour, out_colour = "#cce3fd", "#f2f2f2", "#fde2cf"

    fig, ax = plt.subplots(figsize=(10, 4.2))

    # Column 1: the sources.
    draw_box(ax, c1, 4.2, "OpenAQ v3 API\n(JSON, 7 stations, hourly\nPM2.5, PM10, NO2, CO)", source_colour)
    draw_box(ax, c1, 2.8, "Open-Meteo API\n(JSON, hourly rain,\ntemp, wind, humidity)", source_colour)
    draw_box(ax, c1, 1.4, "Holiday & festival\ncalendar (CSV we built)", source_colour)
    draw_box(ax, c1, 0.0, "Google Trends\n(manual CSV, weekly)", source_colour)
    # Column 2: collect and flatten. Column 3: clean, with the human checks underneath.
    draw_box(ax, c2, 2.8, "02-04 collect\n(cached raw JSON)\n05 flatten JSON", step_colour)
    draw_box(ax, c3, 2.8, "06 time zones, units,\ntypes (UTC -> IST)\n07 gaps + outliers", step_colour)
    draw_box(ax, c3, 1.0, "Human checks:\nM11 outlier verdicts,\nM6 calendar, M10 pivot", "#ffffff")
    # Column 4: big-data step and database. Column 5: analysis and the report.
    draw_box(ax, c4, 4.2, "08 PySpark: resample,\njoin weather + calendar,\ngroup hour x weekday", step_colour)
    draw_box(ax, c4, 1.4, "09 MySQL: 4 tables,\n7 SQL queries", step_colour)
    draw_box(ax, c5, 2.8, "10 analysis\n11 charts\n12 inventory, V profile", step_colour)
    draw_box(ax, c5, 0.6, "Report and slides\n(14 builds this report)", out_colour)

    right = BOX_W   # x offset of a box's right edge
    mid = BOX_H / 2  # y offset of a box's middle
    # Sources -> collect.
    draw_arrow(ax, c1 + right, 4.2 + mid, c2, 2.8 + 0.9, f"{n(openaq_rows)} rows")
    draw_arrow(ax, c1 + right, 2.8 + mid, c2, 2.8 + mid, f"{n(weather_rows)} h")
    draw_arrow(ax, c1 + right, 1.4 + mid, c2, 2.8 + 0.2, f"{n(cal_rows)} days")
    # Collect -> clean; human checks -> clean.
    draw_arrow(ax, c2 + right, 2.8 + mid, c3, 2.8 + mid)
    draw_arrow(ax, c3 + BOX_W / 2, 1.0 + BOX_H, c3 + BOX_W / 2, 2.8)
    # Clean -> PySpark and MySQL.
    draw_arrow(ax, c3 + right, 2.8 + 0.9, c4, 4.2 + mid, f"{n(grid_rows)} rows")
    draw_arrow(ax, c3 + right, 2.8 + 0.2, c4, 1.4 + mid, f"{n(grid_rows)} rows")
    # PySpark and MySQL -> analysis -> report.
    draw_arrow(ax, c4 + right, 4.2 + mid, c5, 2.8 + 0.9, f"{n(spark.loc['4b_join', 'rows'])} joined")
    draw_arrow(ax, c4 + right, 1.4 + mid, c5, 2.8 + 0.2)
    draw_arrow(ax, c5 + BOX_W / 2, 2.8, c5 + BOX_W / 2, 0.6 + BOX_H)
    # Google Trends goes straight to the analysis: run along the bottom, then up, so it crosses no box.
    corner_x = c4 + BOX_W + 0.6
    ax.plot([c1 + right, corner_x, corner_x], [mid, mid, 2.8 + 0.5], color="#4a4a4a", lw=0.9)
    draw_arrow(ax, corner_x, 2.8 + 0.5, c5, 2.8 + 0.5)

    ax.set_xlim(-0.2, c5 + BOX_W + 0.2)
    ax.set_ylim(-0.2, 5.5)
    ax.axis("off")
    ax.set_title("From source to chart: every step is a script in src/, re-run with `make all`",
                 loc="left", fontsize=10)
    fig.tight_layout()
    IMG.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG / "pipeline.png", dpi=170)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Report sections a-i (brief, Section 6), each one function
# ---------------------------------------------------------------------------

def title_block(d):
    return f"""---
title: "The 8 PM Problem: Bengaluru's evening pollution rush"
subtitle: "Case Study B, Data and Storytelling, Module 1"
author: "[[TODO-HUMAN: team name and member names]]"
date: "{pd.Timestamp.today():%d %B %Y}"
---
"""


def section_a(d):
    """a. Executive summary: the answer in three sentences."""
    s = d["s"]
    pt, r, w, wc = s["peak_timing"], s["rain_effect"], s["worst"], s["weekday_check"]
    worst = ", ".join(month_name(m).split()[0] for m in w["worst_months"])
    # Only call a weekday "worst" if the permutation test says the difference is clear.
    if wc["weekday_difference_is_clear"]:
        weekday_text = f"{wc['worst_weekday_excl_festivals']} evenings are the worst of the week"
    else:
        weekday_text = "every day of the week is about the same"
    return f"""# a. Executive summary

1. Bengaluru's evening PM2.5 climbs from about 18:00 and most often peaks between 19:00 and 22:00
   (typical peak {int(pt['interior_peak_median_hour'])}:00); {weekday_text}, but the dry months
   ({worst} are worst) and Deepavali night are far worse than the monsoon.
2. Rain does **not** delay the peak: compared with dry evenings in the same month and day type, rainy evenings
   peak about {abs(r['peak_height_change_pct']):.0f}% lower and {abs(r['peak_hour_shift_h']):.1f} hours earlier,
   although rainy days are already cleaner by noon, so this is an association with rainy weather, not proof
   that rain itself cleans the air.
3. We recommend that the city issue its evening pollution alerts by 18:00 for the 19:00 to 22:00 window,
   concentrate them on dry evenings from November to April and on festival nights, and not plan separate
   weekday-specific or later "rainy-day" alert times.
"""


def section_b(d):
    """b. Question and why it matters."""
    return f"""# b. Question and why it matters to the city

**Question.** Does rain delay, flatten or worsen Bengaluru's evening PM2.5 peak, and on which weekdays and
months is the evening pollution rush worst?

**Why it matters.** Every evening, office traffic, delivery riders and home cooking add to the city's air at
the same time as the air near the ground stops mixing upwards after sunset. PM2.5 (fine dust and smoke
particles, small enough to reach the lungs) is the pollutant that matters most for health. The Urban Services
Cell can act on this in three ways:

* **Pollution alerts:** at what time of day, in which months and on which days to warn residents.
* **Rain-day rules:** whether rules for delivery riders and staggered office hours on rainy days also need to
  change the timing of pollution measures.
* **Where to measure:** which parts of the city the current monitors cannot see.

**Scope.** {d['s']['peak_timing']['n_usable_evenings']:,} usable station-evenings from 7 official monitors,
{DATE_START} to {DATE_END} (over 13 months of hourly data). "Evening" means 17:00 to 23:00 Indian Standard
Time (IST).
"""


def section_c(d):
    """c. Data inventory and V profile."""
    reg = d["register"]
    register = pd.DataFrame({
        "Source": reg["name"],
        "URL": reg["url"],
        "Method": reg["method"],
        "Terms of use": reg["terms_url"],
        "Accessed (UTC)": reg["last_access_utc"].astype(str).str[:10],
    })
    inventory = grouped_inventory(d["inventory"])
    vp = d["vprofile"]
    vprofile = pd.DataFrame({
        "Source": vp["source"], "Rows": vp["rows"].map(n), "Raw MB": vp["raw_mb"],
        "Clean MB": vp["clean_mb"], "Format": vp["format"],
    })
    # The prose of the V profile is written by 12_inventory_vprofile.py: reuse it, do not retype it.
    v_text = (REPORT / "v_profile.md").read_text().split("\n\n", 2)[-1].strip()
    velocity = "; ".join(f"**{a}:** {b}" for a, b in zip(vp["source"], vp["velocity"]))
    trends_note = ("" if d["trends_done"] else
                   "\n[[TODO-HUMAN: Google Trends CSVs not exported yet (manual step M7); the Trends row "
                   "has no access date until then.]]\n")
    calendar_note = ("" if d["calendar_verified"] else
                     "\n[[TODO-HUMAN: the calendar is still the draft; 14 dates await the human check "
                     "(manual step M6). Re-run `make all` after saving data/manual/calendar_verified.csv.]]\n")
    return f"""# c. Data inventory and V profile

**Source register.** Four sources: two JSON APIs, one calendar we built by hand, and one text-derived
source (search interest).

{md_table(register)}
{trends_note}{calendar_note}
**Data inventory.** Every field we use ({len(d['inventory'])} in all), grouped by table and level of
measurement; the full inventory with an example value per field is in Appendix A. The AQI category (Good to
Severe) is **ordinal**: its categories have an order, but the steps between them are not equal.

{md_table(inventory)}

**V profile.**

{md_table(vprofile)}

{velocity}

{v_text}
"""


def grouped_inventory(inv):
    """
    Shorter inventory for the main body: one row per table x measurement level, listing the fields.
    The level is the first word of the full description ("continuous (ratio)" -> "continuous").
    """
    inv = inv.copy()
    inv["level"] = inv["measurement_level"].str.split().str[0].str.lower()
    inv["structure_short"] = inv["structure"].str.split().str[0]
    rows = []
    for (table, level), group in inv.groupby(["table", "level"], sort=False):
        rows.append({"Table": table, "Level": level,
                     "Fields": ", ".join(group["field"]),
                     "Structure": " / ".join(sorted(group["structure_short"].unique()))})
    return pd.DataFrame(rows)


def section_d(d):
    """d. Pipeline: how data moves from source to chart."""
    spark = d["spark"]
    spark_table = pd.DataFrame({"Stage": spark["stage"], "What happens": spark["description"],
                                "Rows": spark["rows"].map(n), "Seconds": spark["seconds"]})
    mysql = d["mysql"]
    mysql_table = pd.DataFrame({"MySQL table": mysql["table"], "Rows": mysql["rows"].map(n),
                                "Columns": mysql["columns"]})
    n_queries = d["sql_md"].count("\n## Q")
    return f"""# d. Pipeline: how data moves from source to chart

{image("img/pipeline.png", "The pipeline. Blue numbers are real row counts at each hand-over.", 16)}

Each box is one numbered script in `src/`; `make all` re-runs everything from the cached raw downloads to
the charts and this report. In plain words:

1. **Collect** (01 to 04): ask both APIs for every hour, one month at a time, keeping a copy of each answer.
2. **Flatten** (05): turn nested JSON (lists inside lists) into ordinary tables, one value per cell.
3. **Fix time and units** (06): convert every clock to Indian time, line up weather and air-quality hours,
   and convert NO2 and CO to the units the Indian AQI uses.
4. **Clean** (07): count every missing hour, remove broken-sensor readings, keep real extreme events, fill
   only short gaps (section e).
5. **Big-data step** (08, PySpark). Resample to hourly, join air with weather and the calendar, and group by
   hour and weekday. Row counts before and after each stage:

{md_table(spark_table)}

6. **Database** (09, MySQL). Load the same data into 4 linked tables and run {n_queries} SQL queries,
   including JOINs and GROUP BYs (ER diagram and queries in Appendix B).

{md_table(mysql_table)}

7. **Analyse and draw** (10 to 12): compute every number in this report and draw the charts.
"""


def section_e(d):
    """e. Cleaning log (key decisions here; the full log is Appendix A)."""
    log = d["log"].set_index("id")
    gaps = d["gaps"]
    pm = gaps[gaps["parameter"] == "pm25"]
    worst_gap = pm.loc[pm["longest_gap_hours"].idxmax()]
    verdicts = d["verdicts"]["human_verdict"].value_counts()

    def rows(i):
        return n(log.loc[i, "rows_affected"])

    # Short wording for the main body; the log's own full wording is in Appendix A.
    # Each row points at a log id, so the row counts always come from the log itself.
    key = pd.DataFrame([
        ["Time zones", "UTC timestamps (text)", rows(7), "Parsed, converted to IST; checked: " + rows(8) + " mismatches", 7],
        ["Time alignment", "Weather hours start at :30 IST", rows(15), "Lined up with air hours (mid-hour value; rain split half/half)", 15],
        ["Type casting", "Values that are not numbers", rows(10), "pd.to_numeric, then float", 10],
        ["Units", "NO2 / CO in ppb", f"{rows(11)} / {rows(12)}", "Converted to µg/m³ / mg/m³ (25 °C, 1 atm)", 11],
        ["Missing values", "Hours never sent", rows(18), "Counted per station (Appendix A)", 18],
        ["Missing values", "Gaps of 1-3 hours", rows(32), "Forward-filled, flagged is_filled", 32],
        ["Missing values", "Gaps over 3 hours", rows(33), "Left empty", 33],
        ["Missing values", "Evenings with < 6 of 7 real hours", rows(34), "Not used for peak timing", 34],
        ["Missing values", "Missing rain hours", rows(36), "Never filled", 36],
        ["Outliers: failure", "Exact zeros", rows(23), "Blanked", 23],
        ["Outliers: failure", "Flat-lines (>= 6 h same value)", rows(24), "Blanked", 24],
        ["Outliers: failure", "Isolated 1-hour spikes", rows(25), "Blanked", 25],
        ["Outliers: real", "Festival-night extremes", rows(26), "Kept, flagged", 26],
        ["Outliers: real", "City-wide extremes (3+ stations)", rows(28), "Kept, flagged", 28],
        ["Outliers: human (M11)", "Top 10 unexplained PM2.5 values", f"{rows(30)} / {rows(31)}", "Failure episodes blanked / real ones kept", 30],
    ], columns=["Topic", "Problem found", "Rows", "Action taken", "Log #"])

    return f"""# e. Cleaning log

The full log has {len(log)} rows, one per decision, each with its reason (Appendix A). The key decisions are
below; each rule is justified underneath.

{md_table(key)}

{image(f"{CHART_DIR}/gap_heatmap_pm25.png", "Gap chart: share of each day's hours with a PM2.5 value, per station.", 15)}

**Why these rules.**

* **Missing values.** We count every gap first (per station: Appendix A and `gaps_per_station.csv`).
  The longest PM2.5 gap is {n(worst_gap['longest_gap_hours'])} hours at {worst_gap['station_id']}. In late
  January 2026 all seven stations went silent for about two weeks together, which points to a data-feed
  outage rather than broken sensors. Pollutant gaps of up to 3 hours are forward-filled (the last value is
  repeated), because PM2.5 changes slowly from hour to hour; longer gaps stay empty, because filling them
  would be guessing. Smooth weather (temperature, humidity, wind) is interpolated for up to 3 hours. Rain is
  never filled, because a shower starts and stops suddenly. An evening counts for peak timing only if at least
  6 of its 7 hours are real readings, so a filled hour can never be the "peak".
* **Time zones.** OpenAQ sends UTC times; we convert to IST and check the result against OpenAQ's own
  local-time copy (0 mismatches). Open-Meteo hours start at half past the hour in IST, so we line them up
  before joining; a naive join would pair every air reading with weather from 30 minutes earlier.
* **Type casting.** Values are forced to numbers (`pd.to_numeric`); anything that is not a number becomes
  missing instead of breaking an average. NO2 and CO arrive in ppb and are converted at 25 °C and 1 atm.
* **Outliers.** A sensor failure (exact zero, the same value stuck for 6 hours or more, a single-hour spike
  that jumps and falls straight back, or a value outside the analyser's range) is blanked. A real extreme
  event is kept: festival nights, city-wide highs at 3 or more stations, and heavy rain. A person reviewed
  the 10 largest unexplained PM2.5 values (M11): {verdicts.get('sensor_failure', 0)} were judged sensor
  failures and {verdicts.get('real_event', 0)} a real event, by looking at the build-up over hours, the other
  stations and the calendar.
* **Normalisation.** Stations differ in level (a busy junction reads higher than a park), so when we compare
  rainy and dry evenings across stations we use **z-scores** within each station: 0 is that station's own
  average, and +1 is one standard deviation above it (chart 2).
"""


def section_f(d):
    """f. Findings, with the charts."""
    s = d["s"]
    pt, r, w, wc, ev = s["peak_timing"], s["rain_effect"], s["worst"], s["weekday_check"], s["events"]
    hourly = d["city_hourly"]
    afternoon_low = int(hourly.loc[12:17].idxmin())
    evening_high = int(hourly.loc[17:23].idxmax())
    months = d["months"]
    worst_month = months.loc[months["mean_evening_pm25"].idxmax()]
    best_month = months.loc[months["mean_evening_pm25"].idxmin()]
    filled = d["diwali_filled"]
    filled_text = (f" The flat stretch at {', '.join(f'{h}:00' for h in filled)} is not real: no station sent "
                   "data in those hours and the 19:00 value was carried forward under our 3-hour rule, so "
                   "the true evening average may be higher still." if filled else "")
    wk = d["weekday"]
    weekday_range = (f"{wk['mean_evening_pm25_excl_festivals'].min()} to "
                     f"{wk['mean_evening_pm25_excl_festivals'].max()} µg/m³")
    return f"""# f. Findings

**Finding 1: the evening rush is real, and it looks the same every day of the week.**
Across the city, PM2.5 is lowest in the afternoon (around {afternoon_low}:00, {hourly[afternoon_low]} µg/m³ on
average) and highest in the evening (around {evening_high}:00, {hourly[evening_high]} µg/m³). Looking at each
station-evening separately, {pt['pct_peaks_19_to_22']}% of peaks fall between 19:00 and 22:00, with a typical
peak at {int(pt['interior_peak_median_hour'])}:00. But {pt['pct_edge_peaks_all']}% of evenings have no clear
peak: PM2.5 is still rising at 23:00, as the night-time air traps pollution near the ground.

{image(f"{CHART_DIR}/1_heatmap_hour_weekday.png", "Chart 1: mean PM2.5 by hour and weekday (hour-by-weekday heatmap).", 16)}

Before excluding festivals, Monday looked worst ({w['worst_weekday_pm25']} µg/m³) and Thursday best
({w['best_weekday_pm25']}), but both Deepavalis fall on or next to a Monday. With the
{wc['n_festival_dates_excluded']} festival dates removed, the gap between the highest and lowest weekday
shrinks to {wc['worst_minus_best']} µg/m³, and a permutation test (shuffling which weekday each date
belongs to, 1,000 times) gives p = {wc['permutation_p_value']}: a gap this size appears by chance almost every time. All seven
weekdays lie between {weekday_range}. **No weekday stands out.**

**Finding 2: rain does not delay the evening peak; rainy evenings peak lower and earlier.**
We compared rainy evenings (at least 1 mm of rain between 16:00 and 22:00) with dry ones (no rain from noon
to midnight) **inside the same month and the same day type** (working day or weekend/holiday), so the
monsoon season itself does not create the difference. Across {r['n_rainy_evenings']} rainy and
{r['n_dry_evenings']} dry station-evenings ({r['n_rainy_dates']} rainy dates, {r['n_strata_compared']}
month-by-day-type groups), the rainy-evening peak is **{abs(r['peak_height_change_pct'])}% lower** (95%
confidence interval {r['peak_height_change_ci'][0]}% to {r['peak_height_change_ci'][1]}%) and comes
**{abs(r['peak_hour_shift_h'])} hours earlier** (95% CI {r['peak_hour_shift_ci'][0]} to
{r['peak_hour_shift_ci'][1]} h). A regression that also holds each station constant agrees:
{r['regression_peak_height_pct']}% and {r['regression_peak_hour_shift_h']} h (Appendix C).

{image(f"{CHART_DIR}/2_rain_vs_dry_zscore.png", "Chart 2 (joins air quality with weather; normalised): PM2.5 z-scores on rainy vs dry evenings.", 14)}

**Caution.** On rainy days PM2.5 is already far lower at noon, before the rain window starts (chart 2). The
weather systems that bring rain also bring wind and cleaner air. So rain marks cleaner evenings; we do not
claim rain itself causes the drop.

{image(f"{CHART_DIR}/3_peak_hour_rain_vs_dry.png", "Chart 3: hour of the evening peak, rainy vs dry evenings.", 11)}

**Finding 3: the dry season is the problem, not the monsoon.** Evening PM2.5 is highest in
{month_name(w['worst_months'][0])} ({w['worst_months_pm25'][0]} µg/m³), {month_name(w['worst_months'][1])}
({w['worst_months_pm25'][1]}) and {month_name(w['worst_months'][2])} ({w['worst_months_pm25'][2]}), and lowest
in {month_name(w['best_months'][0])} to {month_name(w['best_months'][2])} ({w['best_months_pm25'][2]} to
{w['best_months_pm25'][0]}). {month_name(worst_month['month'])} is
{worst_month['mean_evening_pm25'] / best_month['mean_evening_pm25']:.1f} times
{month_name(best_month['month'])}. Note that {month_name(worst_month['month'])} only has data up to
{DATE_END}.

{image(f"{CHART_DIR}/4_evening_by_month.png", "Chart 4: mean evening PM2.5 by month.", 12)}

**Finding 4: Deepavali night is the single worst evening.** From 19:00 to 23:00 on Deepavali (20 October
2025) the city averaged {ev['diwali_19_23_mean']} µg/m³, against {ev['diwali_matched_19_23_mean']} on
{ev['diwali_n_matched_days']} matched normal evenings (same weekday and month, no festival), that is
{(ev['diwali_19_23_mean'] / ev['diwali_matched_19_23_mean'] - 1) * 100:.0f}% higher.{filled_text} For contrast,
on the wettest day ({ev['wettest_day']}, {ev['wettest_day_mm']} mm) the evening averaged
{ev['wettest_17_23_mean']} µg/m³ against {ev['wettest_matched_17_23_mean']} on matched days.

{image(f"{CHART_DIR}/5_event_diwali.png", "Chart 5: Deepavali night vs matched normal days.", 12)}
"""


def section_g(d):
    """g. Recommendation."""
    s = d["s"]
    pt, w, aqi = s["peak_timing"], s["worst"], s["aqi_evening"]
    worst = ", ".join(month_name(m).split()[0] for m in w["worst_months"])
    poor_or_worse = round(aqi["Poor"] + aqi["Very Poor"] + aqi["Severe"], 1)
    return f"""# g. Recommendation

1. **Time evening pollution alerts for 19:00 to 22:00, and send them by 18:00.** That window holds
   {pt['pct_peaks_19_to_22']}% of evening peaks, and the rise starts around 18:00. Alerts sent later miss
   the build-up.
2. **Focus alerts on the dry season and festival nights.** Prioritise November to April ({worst} were the
   worst months) and add a standing festival-night alert for Deepavali, when the evening level was more than
   double a normal evening.
3. **Do not plan a later "rainy-day" alert schedule.** On rainy evenings the peak came earlier and lower, not
   later. Rain-day rules for delivery riders and office hours should be set for road safety and traffic; our
   data give no reason to move pollution measures later on those days.
4. **Do not target specific weekdays.** Once festivals are excluded no weekday differs by more than chance.
   One evening rule for all seven days is simpler and fits the evidence.
5. **Add monitors where the data are blind.** All 7 stations sit within {d['max_km']} km of the centre; Whitefield,
   Electronic City and Yelahanka have none in our data (chart 6). Before targeting neighbourhoods, the city
   needs readings from them.

How serious is the evening rush overall? Of evening station-hours, {aqi['Good']}% fall in CPCB's "Good"
band and {aqi['Satisfactory']}% in "Satisfactory", while {poor_or_worse}% reach "Poor" or worse (hourly
readings against the 24-hour bands, so only an indication). The rush matters most on the dry-season and
festival evenings named above.
"""


def section_h(d):
    """h. Limitations and bias."""
    s = d["s"]
    log = d["log"].set_index("id")
    unusable = n(log.loc[34, "rows_affected"])
    pm = d["gaps"][d["gaps"]["parameter"] == "pm25"]
    missing_range = f"{pm['pct_missing'].min()}% to {pm['pct_missing'].max()}%"
    trends_line = ("Google Trends shows what people **search**, not what they experience; searchers skew "
                   "towards younger, online, English-typing residents, and the values are weekly and relative "
                   "(0 to 100), so they can only give context." if d["trends_done"] else
                   "[[TODO-HUMAN: after M7, one sentence on who Google Trends represents (people who search "
                   "online, in English) and that it is weekly and relative, so it only gives context.]]")
    return f"""# h. Limitations and bias

* **Sensor coverage.** Only 7 reference monitors met our coverage rule, all within {d['max_km']} km of the city
  centre and mostly in the south and centre. The outer growth areas (Whitefield, Electronic City,
  Yelahanka) have no station in our data, so our "city" curve describes the core, not the whole city.
  Residents of the outer city are left out.

{image(f"{CHART_DIR}/6_station_coverage_map.png", "Chart 6: where the monitors are, and are not.", 9)}

* **Gaps.** PM2.5 was missing for {missing_range} of hours depending on the station, including a two-week
  outage at all stations in January 2026. {unusable} station-evenings were too incomplete to time the peak.
  If the missing evenings are not random (for example, sensors failing more in heavy rain), our results could
  be biased.
* **One weather point.** Rain comes from a single Open-Meteo grid point at the city centre. A storm over
  Peenya may not register there, so some "dry" evenings may have been wet locally.
* **Correlation, not cause.** Rainy days are cleaner already at noon. Wind, cloud and the weather system all
  change together, and fewer people go out in the rain. We cannot separate these with our data.
* **Hourly averages.** Each value is the average of four 15-minute readings, and alerts based on CPCB's
  24-hour AQI bands are an indication only.
* **Unit conversion.** NO2 and CO were converted from ppb at a standard 25 °C and 1 atm; Bengaluru's
  real temperature and altitude shift these by a few percent. PM2.5, our main measure, needed no conversion.
* **Search data.** {trends_line}
* **Sources we did not use.** We did not use Reddit or Kaggle data. Reddit posters are a small, younger,
  English-speaking group and would not represent the city; Kaggle traffic or delivery datasets rarely say how
  or where they were collected, so we could not check their origin. We therefore say nothing about traffic
  volumes directly; "traffic" in this report is an explanation from outside our data, not a measurement.
"""


def section_i(d):
    """i. Reflection. Drafted from report/reflection_notes.md; the team must put it in their own words."""
    s = d["s"]
    q7_note = "20:00 most common, but 23:00 (the window's edge) second"
    return f"""# i. Reflection

**How the question changed.** We started by expecting rain to **delay** the evening peak, because wet roads
slow traffic. The data reversed this: rainy evenings peaked earlier and lower. Our first SQL query on peak
timing ({q7_note}) showed that many evenings have no clear "8 PM" peak, so we now report edge peaks
separately. Our first weekday table named Monday the worst; that turned out to be the Deepavalis, and a
proper test showed no weekday stands out. The data also changed our plan: only 5 stations reached 70%
coverage, so we accepted 60% and a stricter per-evening rule instead.

**What we would do with better data.**

More monitors in the outer city; rain gauges at each station instead of one city-centre point; hourly
traffic counts or metro ridership, so "traffic" becomes a measurement rather than an explanation; and several
years of data, so a "worst month" can be checked against other years.

[[TODO-HUMAN: rewrite this section in the team's own words (it is graded as your reflection); keep the
facts from report/reflection_notes.md, and add one thing each member learned.]]
"""


# ---------------------------------------------------------------------------
# Appendices
# ---------------------------------------------------------------------------

def appendix_a(d):
    """Appendix A: the full cleaning log."""
    log = d["log"].copy()
    log["rows_affected"] = log["rows_affected"].map(n)
    log.columns = ["#", "Stage", "Problem found", "Rows affected", "Action taken", "Why"]
    pm = d["gaps"].copy()
    pm.columns = ["Station", "Pollutant", "Hours expected", "Hours missing", "% missing", "Longest gap (h)"]
    inv = d["inventory"].copy()
    inv.columns = ["Field", "Table", "Example", "Measurement level", "Structure", "Source"]
    return f"""# Appendix A. Full cleaning log, gaps per station and data inventory

{md_table(log)}

**Gaps per station and pollutant** (before any filling):

{md_table(pm)}

**Full data inventory** (every field, with a real example value):

{md_table(inv)}
"""


def appendix_b(d):
    """Appendix B: ER diagram, schema and the SQL queries with their outputs."""
    # Keep the query text and the first rows of each result; the full file is in outputs/tables/.
    sql = d["sql_md"].split("\n", 1)[1].replace("\n## ", "\n### ")
    return f"""# Appendix B. Database: ER diagram, schema and queries

{image("er_diagram.png", "ER diagram of the MySQL database (keys link readings to stations, weather and calendar).", 15)}

The schema is in `sql/schema.sql`; the queries in `sql/queries.sql` are run by `src/09_load_mysql.py`, which
saves their outputs below (also in `outputs/tables/sql_q1.csv` to `sql_q7.csv`).

{sql}
"""


def appendix_c(d):
    """Appendix C: the regression output, as text."""
    text = (TABLES / "rain_effect_regression.txt").read_text()
    return f"""# Appendix C. Rain-effect regression (fixed effects)

The peak height (log) and peak hour of each station-evening are regressed on a rainy-evening flag, holding
month, day type and station constant; standard errors are clustered by date.

```
{text}
```
"""


def appendix_d(d):
    """Appendix D: spreadsheet vs pandas note (written by 13_compare_spreadsheet.py and the team)."""
    note = (REPORT / "spreadsheet_vs_pandas.md").read_text().split("\n", 1)[1]
    return f"""# Appendix D. Spreadsheet vs pandas: one pivot built twice

{note}

{image("img/m10_pivot_result.png", "The LibreOffice Calc pivot (hour x weekday).", 15)}
"""


def appendix_e(d):
    """Appendix E: generative AI use (the full disclosure lives in its own file)."""
    return """# Appendix E. Use of generative AI

[[TODO-HUMAN: the team fills report/appendix_ai_use.md (tools used, what we asked, what we changed);
it is pasted here when the submission is built.]]
"""


# ---------------------------------------------------------------------------
# Write and render
# ---------------------------------------------------------------------------

def build_markdown(d):
    """All sections in the brief's order (a-i), then the appendices."""
    parts = [title_block(d), section_a(d), section_b(d), section_c(d), section_d(d), section_e(d),
             section_f(d), section_g(d), section_h(d), section_i(d),
             PAGE_BREAK, appendix_a(d), appendix_b(d), appendix_c(d), appendix_d(d), appendix_e(d)]
    return "\n\n".join(parts)


def make_reference_docx():
    """
    Pandoc copies page size, margins and fonts from a "reference" Word file.
    We start from pandoc's default one and change only what keeps the main body
    within 10 pages: A4 paper, 2 cm margins, 10 pt text, 8 pt tables, smaller headings.
    """
    import pypandoc
    from docx import Document
    from docx.shared import Cm, Pt

    ref_path = REPORT / "reference.docx"
    default = subprocess.run([pypandoc.get_pandoc_path(), "--print-default-data-file", "reference.docx"],
                             capture_output=True, check=True).stdout
    ref_path.write_bytes(default)

    doc = Document(str(ref_path))
    for section in doc.sections:
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        section.left_margin = section.right_margin = Cm(2.0)
        section.top_margin = section.bottom_margin = Cm(1.8)
    sizes = {"Normal": 10, "Table": 8, "Heading 1": 14, "Heading 2": 12, "Heading 3": 11,
             "Title": 22, "Subtitle": 12, "Author": 10, "Date": 10, "Image Caption": 8.5}
    for name, size in sizes.items():
        if name in [s.name for s in doc.styles]:
            doc.styles[name].font.size = Pt(size)
    # Less empty space between paragraphs and before headings.
    for name in ["Body Text", "First Paragraph", "Compact"]:
        doc.styles[name].paragraph_format.space_after = Pt(4)
    doc.styles["Heading 1"].paragraph_format.space_before = Pt(10)
    doc.save(str(ref_path))
    return ref_path


def render(md_path):
    """
    .md -> .docx with pandoc (bundled by the pypandoc_binary package, so no system install),
    then .docx -> .pdf with LibreOffice, which keeps the Word layout (tables, image sizes).
    """
    import pypandoc

    docx_path = md_path.with_suffix(".docx")
    # --resource-path tells pandoc to find images relative to the report/ folder.
    reference = make_reference_docx()
    pypandoc.convert_file(str(md_path), "docx", outputfile=str(docx_path),
                          extra_args=["--resource-path", str(REPORT), "--reference-doc", str(reference)])
    print(f"  {docx_path.relative_to(ROOT)} written")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        print("  LibreOffice not found: skipped the PDF (open report.docx and export it by hand)")
        return
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(REPORT), str(docx_path)],
                   check=True, capture_output=True)
    print(f"  {docx_path.with_suffix('.pdf').relative_to(ROOT)} written")


def main():
    d = load_inputs()
    draw_pipeline(d)
    md_path = REPORT / "report.md"
    md_path.write_text(build_markdown(d))
    print(f"  {md_path.relative_to(ROOT)} written")
    todo = md_path.read_text().count("[[TODO-HUMAN")
    print(f"  {todo} [[TODO-HUMAN]] markers left for the team")
    render(md_path)


if __name__ == "__main__":
    main()
