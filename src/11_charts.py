"""
11_charts.py — the charts for the report and slides. Every title states a
FINDING built from the real numbers in outputs/tables/ (nothing is typed in by
hand), so if the data change, the titles change with them.

Charts (outputs/charts/):
  1_heatmap_hour_weekday.png    required hour x weekday heatmap (from the Spark output)
  2_rain_vs_dry_zscore.png      joins two sources (air + weather), NORMALISED (z-scores)
  3_peak_hour_rain_vs_dry.png   when the peak happens, rainy vs dry evenings
  4_evening_by_month.png        which months are worst
  5_event_diwali.png            event study: Deepavali night vs matched normal days
  6_station_coverage_map.png    where the monitors are (and are not)
  (gap_heatmap_pm25.png is drawn by 07_gaps_outliers.py)

Colours: blue #257de0 = dry, orange #f47230 = rainy (checked for colour-blind
separation with the dataviz validator). Orange is light on white, so every line is
also labelled directly and drawn with a different line style.

Run:  python src/11_charts.py
"""

import json
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from common import BENGALURU_CENTRE, CHARTS, INTERIM, TABLES, ensure_folders

DRY, RAINY = "#257de0", "#f47230"
INK, INK_2, GRID = "#191919", "#666666", "#e7e7e7"
BLUES = LinearSegmentedColormap.from_list("blues", ["#cce3fd", "#6aabf1", "#257de0", "#1757ac", "#0e3d7e"])
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": "#c2c2c2", "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.titlecolor": INK,
    "axes.spines.top": False, "axes.spines.right": False,
})


def summary():
    return json.loads((TABLES / "analysis_summary.json").read_text())


def finish(fig, ax, title, filename, note=None):
    """Same title position, light grid and footnote on every chart."""
    ax.set_title(title, loc="left", fontsize=11, wrap=True)
    if note:
        fig.text(0.01, 0.01, note, fontsize=8, color=INK_2)
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(CHARTS / filename, dpi=150)
    plt.close(fig)
    print(f"  {filename}: {title}")


def ci_text(ci):
    return f"95% CI {ci[0]:+g} to {ci[1]:+g}"


# ---------------------------------------------------------------------------
def chart_heatmap():
    hw = pd.read_csv(TABLES / "spark_pm25_hour_weekday.csv")
    grid = hw.pivot(index="weekday", columns="hour", values="mean_pm25").reindex(WEEKDAYS)

    evening = grid.loc[:, 17:23]
    worst_day = evening.mean(axis=1).idxmax()
    peak_hour = int(evening.mean(axis=0).idxmax())
    worst_cell = evening.stack().idxmax()
    title = (f"Evening PM2.5 climbs to its daily high around {peak_hour}:00; "
             f"{worst_day} evenings are the worst "
             f"(peak cell {worst_cell[0][:3]} {worst_cell[1]}:00 = {evening.max().max():.0f} µg/m³)")

    fig, ax = plt.subplots(figsize=(11, 3.8))
    image = ax.imshow(grid.values, aspect="auto", cmap=BLUES)
    ax.set_yticks(range(7))
    ax.set_yticklabels(WEEKDAYS)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}" for h in range(0, 24, 2)])
    ax.set_xlabel("Hour of day (IST)")
    ax.axvspan(16.5, 23.5, fill=False, edgecolor=INK, lw=1.2, ls="--")
    cbar = fig.colorbar(image, ax=ax, pad=0.01)
    cbar.set_label("mean PM2.5 (µg/m³)", color=INK_2)
    n = int(hw["n_station_hours"].sum())
    n_stations = len(pd.read_csv(INTERIM / "stations.csv"))
    finish(fig, ax, title, "1_heatmap_hour_weekday.png",
           f"Dashed box = evening window 17:00–23:00. Mean of {n:,} station-hours, {n_stations} stations, "
           "Oct 2025–Nov 2026. Source: OpenAQ (CPCB/KSPCB), aggregated in PySpark.")


def chart_rain_z(s):
    z = pd.read_csv(TABLES / "pm25_z_by_hour_rain.csv")
    r = s["rain_effect"]
    shift_ci, h_ci = r["peak_hour_shift_ci"], r["peak_height_change_ci"]
    timing = ("with no clear shift in timing" if shift_ci[0] <= 0 <= shift_ci[1]
              else f"and peaked {abs(r['peak_hour_shift_h']):.1f} h {'later' if r['peak_hour_shift_h'] > 0 else 'earlier'}")
    height = ("no clear change in peak height" if h_ci[0] <= 0 <= h_ci[1]
              else f"{abs(r['peak_height_change_pct']):.0f}% {'lower' if r['peak_height_change_pct'] < 0 else 'higher'} peak")
    title = (f"Same month, same day type: rainy evenings had a {height} {timing} "
             f"(n = {r['n_rainy_evenings']} rainy vs {r['n_dry_evenings']} dry station-evenings)")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for kind, colour, style in [("dry", DRY, "-"), ("rainy", RAINY, "--")]:
        d = z[z["evening_type"] == kind]
        ax.plot(d["hour"], d["mean"], color=colour, lw=2, ls=style)
        last = d.iloc[-1]
        ax.text(last["hour"] + 0.2, last["mean"], f"{kind} evenings", color=INK, va="center", fontsize=9)
    ax.axhline(0, color="#c2c2c2", lw=1)
    ax.axvspan(17, 23, color=GRID, alpha=0.5, lw=0)
    ax.set_xlim(12, 25)
    ax.set_xticks(range(12, 24, 2))
    ax.set_xlabel("Hour of day (IST)")
    ax.set_ylabel("PM2.5, z-score within each station")
    ax.grid(axis="y", color=GRID, lw=0.6)
    finish(fig, ax, title, "2_rain_vs_dry_zscore.png",
           f"Peak height {ci_text(h_ci)}%; timing {ci_text(shift_ci)} h (bootstrap by date). z = 0 is the "
           "station's own average. Air: OpenAQ; rain: Open-Meteo.")


def chart_peak_hours():
    peaks = pd.read_csv(TABLES / "evening_peaks.csv")
    peaks = peaks[peaks["evening_type"].isin(["rainy", "dry"])]
    share = (peaks.groupby("evening_type")["peak_hour"].value_counts(normalize=True)
             .mul(100).rename("pct").reset_index())
    pivot = share.pivot(index="peak_hour", columns="evening_type", values="pct").reindex(range(17, 24)).fillna(0)
    late = {k: pivot.loc[21:23, k].sum() for k in ["dry", "rainy"]}
    title = (f"Peaks at 21:00 or later: {late['rainy']:.0f}% of rainy evenings vs {late['dry']:.0f}% of dry ones "
             f"(23:00 = still rising at the window's edge)")

    fig, ax = plt.subplots(figsize=(9, 4.2))
    width = 0.38
    x = np.arange(17, 24)
    ax.bar(x - width / 2 - 0.01, pivot["dry"], width, color=DRY, label="dry evenings")
    ax.bar(x + width / 2 + 0.01, pivot["rainy"], width, color=RAINY, label="rainy evenings", hatch="//",
           edgecolor="white", lw=0)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}:00" for h in x])
    ax.set_xlabel("Hour of the evening peak (IST)")
    ax.set_ylabel("% of station-evenings")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=GRID, lw=0.6)
    n = peaks["evening_type"].value_counts()
    finish(fig, ax, title, "3_peak_hour_rain_vs_dry.png",
           f"Usable evenings only (>= 6 of 7 real hours). n = {n.get('dry', 0)} dry, {n.get('rainy', 0)} rainy. "
           "Not adjusted for month: see chart 2 for the like-for-like comparison.")


def chart_months(s):
    m = pd.read_csv(TABLES / "evening_by_month.csv")
    w = s["worst"]
    ratio = np.mean(w["worst_months_pm25"]) / np.mean(w["best_months_pm25"])
    names = [pd.Period(x).strftime("%b %y") for x in w["worst_months"]]
    title = (f"Evening PM2.5 is worst in {', '.join(names)}: about {ratio:.1f}x the cleanest monsoon months")

    fig, ax = plt.subplots(figsize=(10, 4))
    colours = [DRY if x not in w["worst_months"] else "#0e3d7e" for x in m["month"]]
    ax.bar(range(len(m)), m["mean_evening_pm25"], color=colours, width=0.7)
    ax.set_xticks(range(len(m)))
    ax.set_xticklabels([pd.Period(x).strftime("%b\n%y") for x in m["month"]], fontsize=8)
    ax.set_ylabel("mean PM2.5, 17:00–23:00 (µg/m³)")
    ax.axhline(60, color="#c2c2c2", lw=1, ls=":")
    ax.text(len(m) - 0.5, 61, "60 = upper limit of 'Satisfactory' (CPCB)", ha="right", fontsize=8, color=INK_2)
    ax.grid(axis="y", color=GRID, lw=0.6)
    finish(fig, ax, title, "4_evening_by_month.png",
           "Darker bars = the three worst months. Hourly values against the CPCB band; official AQI uses 24-h means.")


def chart_diwali(s):
    d = pd.read_csv(TABLES / "event_study_diwali.csv")
    e = s["events"]
    change = (e["diwali_19_23_mean"] / e["diwali_matched_19_23_mean"] - 1) * 100
    direction = "higher" if change > 0 else "lower"
    title = (f"Deepavali night: city PM2.5 averaged {e['diwali_19_23_mean']:.0f} µg/m³ from 19:00–23:00, "
             f"{abs(change):.0f}% {direction} than {e['diwali_n_matched_days']} matched normal evenings")

    fig, ax = plt.subplots(figsize=(9, 4.2))
    for kind, colour, style in [(k, RAINY if "matched" not in k else DRY, "-" if "matched" in k else "--")
                                for k in d["kind"].unique()]:
        part = d[d["kind"] == kind]
        ax.plot(part["hour"], part["value"], color=colour, lw=2, ls=style)
        last = part.iloc[-1]
        ax.text(last["hour"] + 0.2, last["value"], kind, fontsize=9, color=INK, va="center")
    ax.set_xlim(0, 30)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlabel("Hour of day (IST)")
    ax.set_ylabel("city-mean PM2.5 (µg/m³)")
    ax.grid(axis="y", color=GRID, lw=0.6)
    finish(fig, ax, title, "5_event_diwali.png",
           "Matched days: same weekday and month, not a festival. Fireworks hours are flagged real_event_festival, not "
           "removed.")


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def chart_coverage():
    st = pd.read_csv(INTERIM / "stations.csv")
    lat0, lon0 = BENGALURU_CENTRE
    st["km"] = [distance_km(lat0, lon0, a, b) for a, b in zip(st["lat"], st["lon"])]
    title = (f"All {len(st)} reference monitors sit within {st['km'].max():.0f} km of the city centre; "
             "the outer city (Whitefield, Electronic City, Yelahanka) has none in our data")

    fig, ax = plt.subplots(figsize=(7, 6.5))
    for radius in (5, 10, 15):
        circle = plt.Circle((lon0, lat0), radius / 111, fill=False, color="#c2c2c2", ls=":", lw=1)
        ax.add_patch(circle)
        ax.text(lon0 - radius / 111 - 0.002, lat0, f"{radius} km", fontsize=7, color=INK_2, ha="right")
    ax.scatter(st["lon"], st["lat"], s=60, color=DRY, edgecolor="white", lw=2, zorder=3)
    for _, row in st.iterrows():
        label = row["name"].split(",")[0]
        ax.text(row["lon"] + 0.004, row["lat"] + 0.003, label, fontsize=8, color=INK)
    ax.scatter([lon0], [lat0], marker="+", color=INK, s=80)
    ax.text(lon0 + 0.004, lat0 - 0.008, "city centre", fontsize=8, color=INK_2)
    for name, (la, lo) in {"Whitefield": (12.97, 77.75), "Electronic City": (12.84, 77.66),
                           "Yelahanka": (13.10, 77.60)}.items():
        ax.text(lo, la, name, fontsize=8, color=INK_2, style="italic", ha="center")
    ax.set_xlim(lon0 - 0.2, lon0 + 0.2)
    ax.set_ylim(lat0 - 0.18, lat0 + 0.18)
    ax.set_aspect(1 / math.cos(math.radians(lat0)))
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    finish(fig, ax, title, "6_station_coverage_map.png",
           "Station coordinates from OpenAQ. Grey italic names are reference places with no monitor in our data.")


def main():
    ensure_folders()
    s = summary()
    chart_heatmap()
    chart_rain_z(s)
    chart_peak_hours()
    chart_months(s)
    chart_diwali(s)
    chart_coverage()


if __name__ == "__main__":
    main()
