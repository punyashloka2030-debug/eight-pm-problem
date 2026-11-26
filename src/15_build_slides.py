"""
15_build_slides.py — the 10-slide deck for the 7-minute talk, built from the pipeline's own files.

Like the report (14), every number on a slide is read from outputs/tables/ or the cleaning log,
so a re-run of `make all` updates the slides too. Each slide has speaker notes; the full
speaker script with timings is report/speaker_script.md (also written here).

Story order (the brief: "opens with the answer, then the evidence"):
  1 title + answer   2 the answer in numbers   3 question and data   4 pipeline
  5 cleaning         6-8 findings              9 recommendation      10 limits

Input:   outputs/tables/*.json/*.csv, outputs/cleaning_log.csv, outputs/charts/*.png,
         report/img/pipeline.png, data/manual/team.csv, data/manual/team_name.txt
Output:  report/slides.pptx, report/slides.pdf (LibreOffice), report/speaker_script.md

Run:  python src/15_build_slides.py
"""

import importlib
import json
import shutil
import subprocess

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from common import CHARTS, CLEANING_LOG, MANUAL, ROOT, TABLES

REPORT = ROOT / "report"
# Reuse two helpers from the report builder so slides and report compute these numbers the same way.
# (importlib is needed because a module name cannot start with a digit in a normal import line.)
report_builder = importlib.import_module("14_build_report")

# Colours (hex). Night navy dominates the dark slides; amber is the one accent and is the
# same orange as "rainy" in the charts; blue is "dry" in the charts.
NIGHT = "14213D"
AMBER = "F47230"
BLUE = "257DE0"
INK = "191919"
MUTED = "5F6B7A"
CARD = "EEF2F7"
WHITE = "FFFFFF"
FONT = "Arial"  # Arial ships with Office and LibreOffice has a same-width copy, so layout checks are reliable

# Slide size: 16:9 widescreen, 13.33 x 7.5 inches.
SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.6


# ---------------------------------------------------------------------------
# Small drawing helpers (positions and sizes are in inches)
# ---------------------------------------------------------------------------

def rgb(hex_colour):
    return RGBColor.from_string(hex_colour)


def add_text(slide, x, y, w, h, text, size=16, bold=False, colour=INK, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, italic=False):
    """One text box. `text` may be a string or a list of strings (one paragraph each)."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    frame.margin_left = frame.margin_right = Inches(0)
    paragraphs = text if isinstance(text, list) else [text]
    for i, line in enumerate(paragraphs):
        para = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        para.alignment = align
        para.space_after = Pt(6)
        run = para.add_run()
        run.text = line
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = rgb(colour)
    return box


def add_card(slide, x, y, w, h, fill=CARD):
    """A rounded rectangle with no outline: the background of a stat or action card."""
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    card.adjustments[0] = 0.08
    card.fill.solid()
    card.fill.fore_color.rgb = rgb(fill)
    card.line.fill.background()
    card.shadow.inherit = False
    return card


def stat_card(slide, x, y, w, h, number, label, number_colour=AMBER, fill=CARD, label_colour=INK):
    """The deck's visual motif: a big number with a short label under it, on a tinted card."""
    add_card(slide, x, y, w, h, fill)
    add_text(slide, x + 0.3, y + 0.2, w - 0.6, 1.0, number, size=40, bold=True, colour=number_colour)
    add_text(slide, x + 0.3, y + 1.2, w - 0.6, h - 1.35, label, size=14, colour=label_colour)


def add_picture(slide, path, x, y, w=None, h=None):
    """A chart image; give either the width or the height so the image keeps its shape."""
    kwargs = {}
    if w is not None:
        kwargs["width"] = Inches(w)
    if h is not None:
        kwargs["height"] = Inches(h)
    return slide.shapes.add_picture(str(path), Inches(x), Inches(y), **kwargs)


def background(slide, colour):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb(colour)


def content_slide(prs, title):
    """A white slide with the finding-style title in the same place every time."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # layout 6 = blank
    background(slide, WHITE)
    add_text(slide, MARGIN, 0.4, SLIDE_W - 2 * MARGIN, 1.2, title, size=30, bold=True, colour=NIGHT,
             anchor=MSO_ANCHOR.TOP)
    return slide


def source_line(slide, text, colour=MUTED):
    """Small source note at the bottom-left of a slide."""
    add_text(slide, MARGIN, SLIDE_H - 0.55, SLIDE_W - 2 * MARGIN, 0.35, text, size=10, colour=colour)


# ---------------------------------------------------------------------------
# Load the numbers
# ---------------------------------------------------------------------------

def load():
    d = {"s": json.loads((TABLES / "analysis_summary.json").read_text())}
    d["log"] = pd.read_csv(CLEANING_LOG)
    d["vprofile"] = pd.read_csv(TABLES / "v_profile.csv").set_index("source")
    d["spark"] = pd.read_csv(TABLES / "spark_row_counts.csv").set_index("stage")
    d["months"] = pd.read_csv(TABLES / "evening_by_month.csv")
    d["team"] = pd.read_csv(MANUAL / "team.csv") if (MANUAL / "team.csv").exists() else None
    name_file = MANUAL / "team_name.txt"
    d["team_name"] = name_file.read_text().strip() if name_file.exists() else "[[TODO-HUMAN: team name]]"
    trends = TABLES / "trends_correlation.csv"
    d["trends"] = (pd.read_csv(trends).set_index(["term", "measure"])["spearman_rho"]
                   if trends.exists() else None)
    d["max_km"] = report_builder.farthest_station_km()
    d["diwali_filled"] = report_builder.diwali_filled_hours()
    return d


def log_rows(d, text):
    """Rows affected for the cleaning-log entry whose problem starts with `text` (found by words, not number)."""
    match = d["log"][d["log"]["problem_found"].str.startswith(text)]
    if len(match) != 1:
        raise ValueError(f"expected one cleaning-log row starting with {text!r}, found {len(match)}")
    return int(match["rows_affected"].iloc[0])


def month_short(yyyy_mm):
    return pd.Timestamp(yyyy_mm + "-01").strftime("%b %Y")


# ---------------------------------------------------------------------------
# The ten slides. Each returns its speaker notes so the script file can collect them.
# ---------------------------------------------------------------------------

def slide_1_title(prs, d):
    s = d["s"]
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background(slide, NIGHT)
    add_text(slide, MARGIN, 0.9, 11, 0.6, "THE 8 PM PROBLEM · BENGALURU", size=16, bold=True, colour=AMBER)
    add_text(slide, MARGIN, 1.6, 12, 2.4,
             f"Evening pollution peaks between 19:00 and 22:00, and rain makes it lower and earlier, not later",
             size=40, bold=True, colour=WHITE)
    if d["team"] is not None:
        members = "   ·   ".join(f"{r.name} ({r.usn})" for r in d["team"].itertuples())
    else:
        members = "[[TODO-HUMAN: members]]"
    add_text(slide, MARGIN, 5.2, 12, 0.5, f"Team {d['team_name']}", size=18, bold=True, colour=WHITE)
    add_text(slide, MARGIN, 5.75, 12.1, 0.9, members, size=13, colour="C9D3E3")
    add_text(slide, MARGIN, 6.75, 12, 0.4, "Case Study B · Data and Storytelling, Module 1", size=12,
             colour="C9D3E3")
    return (f"Good morning. Our question was simple: when does Bengaluru's evening pollution rush really "
            f"happen, and does rain make it worse? Here is the answer first. PM2.5 peaks between 19:00 and "
            f"22:00, and on rainy evenings the peak is lower and earlier, not later as we expected. The next "
            f"slide gives the three numbers behind that, and what the city should do with them.")


def slide_2_answer(prs, d):
    s = d["s"]
    pt, r, w = s["peak_timing"], s["rain_effect"], s["worst"]
    # Same definition as chart 4's title: mean of the 3 worst months / mean of the 3 cleanest.
    ratio = (sum(w["worst_months_pm25"]) / len(w["worst_months_pm25"])) / \
            (sum(w["best_months_pm25"]) / len(w["best_months_pm25"]))
    slide = content_slide(prs, "The answer: alert by 18:00, focus on dry months and festival nights")
    card_w, gap, y = 3.85, 0.3, 1.9
    stat_card(slide, MARGIN, y, card_w, 2.6, f"{pt['pct_peaks_19_to_22']:.0f}%",
              "of evening peaks fall between 19:00 and 22:00, on every day of the week alike")
    stat_card(slide, MARGIN + card_w + gap, y, card_w, 2.6,
              f"{r['peak_height_change_pct']:.0f}%",
              f"lower peak on rainy evenings, and {abs(r['peak_hour_shift_h']):.1f} h earlier "
              f"(same month, same day type)")
    stat_card(slide, MARGIN + 2 * (card_w + gap), y, card_w, 2.6, f"{ratio:.1f}×",
              "evening PM2.5 in the three worst dry-season months against the three cleanest "
              "monsoon months")
    add_text(slide, MARGIN, 4.9, 12.1, 1.6,
             ["Our question: does rain delay, flatten or worsen the evening PM2.5 peak, and on which weekdays "
              "and months is it worst?",
              "Decision it serves: when to send pollution alerts, and whether rain-day rules need different timing."],
             size=16, colour=INK)
    source_line(slide, f"{s['peak_timing']['n_usable_evenings']:,} usable station-evenings, 7 official monitors, "
                       "Oct 2025 – Nov 2026. Sources: OpenAQ (CPCB/KSPCB), Open-Meteo.")
    return (f"Three numbers. First, {pt['pct_peaks_19_to_22']:.0f} percent of evening peaks fall between 7 and 10 "
            f"PM, and that is true on every weekday. Second, rainy evenings peak about "
            f"{abs(r['peak_height_change_pct']):.0f} percent lower and {abs(r['peak_hour_shift_h']):.1f} hours "
            f"earlier, compared with dry evenings in the same month. Third, the three worst months are "
            f"{ratio:.1f} times the three cleanest. So the city should alert by 6 PM, focus on dry months and festival "
            f"nights, and keep one rule for all weekdays.")


def slide_3_data(prs, d):
    vp, s = d["vprofile"], d["s"]
    readings = vp.loc["OpenAQ hourly readings", "rows"]
    grid = vp.loc["Full analysis grid (readings_clean)", "rows"]
    weather = vp.loc["Open-Meteo weather", "rows"]
    raw_mb = vp.loc["OpenAQ hourly readings", "raw_mb"]
    slide = content_slide(prs, f"{readings:,} hourly readings from 4 sources, over 14 months")
    tiles = [
        (f"{readings:,}", "hourly air-quality readings, 7 stations, PM2.5, PM10, NO2, CO (OpenAQ JSON API)"),
        (f"{weather:,}", "hours of rain, temperature and wind (Open-Meteo JSON API)"),
        (f"{vp.loc['Calendar', 'rows']:,}", "days in our holiday and festival calendar, checked against the government notification"),
        (f"{raw_mb:.0f} MB", "of raw JSON; Variety and time zones, not Volume, took most of the work"),
    ]
    tile_w, tile_h, gap = 5.9, 1.95, 0.3
    for i, (number, label) in enumerate(tiles):
        x = MARGIN + (i % 2) * (tile_w + gap)
        y = 1.75 + (i // 2) * (tile_h + gap)
        stat_card(slide, x, y, tile_w, tile_h, number, label, number_colour=NIGHT)
    add_text(slide, MARGIN, 6.15, 12.1, 0.6,
             f"Plus Google Trends (weekly search interest) as our text source. Largest table: {grid:,} rows "
             "(every station × pollutant × hour), loaded into MySQL and processed with PySpark.",
             size=14, colour=INK)
    return (f"Our data: {readings:,} hourly readings from seven official monitors through the OpenAQ API, "
            f"hourly weather from Open-Meteo, a holiday calendar we built and checked against the Karnataka "
            f"government notification, and Google Trends. The full grid is {grid:,} rows. Honestly, volume was "
            f"not the hard part; it fits on a laptop. Variety was: two JSON shapes and three different clocks.")


def slide_4_pipeline(prs, d):
    spark = d["spark"]
    slide = content_slide(prs, "Lining up \"the same hour\" across sources was most of the work")
    # The diagram as wide as the slide allows while leaving room for one row of cards.
    add_picture(slide, ROOT / "report" / "img" / "pipeline.png", 1.9, 1.45, w=9.5)
    notes = [
        ("UTC → IST", f"checked against OpenAQ's own local time: {log_rows(d, 'Need proof that our UTC')} mismatches"),
        (":30 vs :00", "weather hours start at half past; aligned before every join"),
        ("ppb → µg/m³", "NO2 and CO converted to the units the Indian AQI uses"),
        ("PySpark", f"{spark.loc['1_load', 'rows']:,} rows in, {spark.loc['4b_join', 'rows']:,} PM2.5 hours "
                    "joined with weather and calendar"),
    ]
    card_w, gap = 2.8, 0.3
    for i, (head, text) in enumerate(notes):
        x = MARGIN + i * (card_w + gap)
        add_card(slide, x, 5.55, card_w, 1.4)
        add_text(slide, x + 0.2, 5.63, card_w - 0.4, 0.45, head, size=18, bold=True, colour=AMBER)
        add_text(slide, x + 0.2, 6.1, card_w - 0.4, 0.85, text, size=13, colour=INK)
    return ("This is the pipeline: every box is one script. The hard part was time. OpenAQ sends UTC, we convert "
            f"to Indian time and check it against OpenAQ's own local timestamp: {log_rows(d, 'Need proof that our UTC')} "
            "mismatches. Weather hours "
            "start at half past the hour, air-quality hours on the hour, so we line them up before joining. "
            "PySpark then resamples and joins the big table, and one make command rebuilds it all.")


def slide_5_cleaning(prs, d):
    grid = d["vprofile"].loc["Full analysis grid (readings_clean)", "rows"]
    missing = log_rows(d, "Hours the API never sent")
    filled = log_rows(d, "Short gaps (<= 3")
    flat = log_rows(d, "Flat-lines")
    zeros = log_rows(d, "Exact zero readings")
    festival = log_rows(d, "Extreme values (above each station's 99.5th percentile): real_event_festival")
    slide = content_slide(prs, f"{missing / grid:.0%} of hours never arrived: every gap counted, only short ones filled")
    add_picture(slide, CHARTS / "gap_heatmap_pm25.png", MARGIN, 1.55, w=12.1)
    tiles = [
        (f"{filled:,}", "short gaps (≤ 3 h) forward-filled and flagged"),
        (f"{flat + zeros:,}", "sensor failures blanked: flat-lines and exact zeros"),
        (f"{festival:,}", "festival-night extremes kept: real pollution, not errors"),
        ("10", "largest unexplained values judged by a person (M11)"),
    ]
    tile_w, gap = 2.8, 0.3
    for i, (number, label) in enumerate(tiles):
        x = MARGIN + i * (tile_w + gap)
        add_card(slide, x, 5.3, tile_w, 1.55)
        add_text(slide, x + 0.2, 5.38, tile_w - 0.4, 0.6, number, size=26, bold=True, colour=AMBER)
        add_text(slide, x + 0.2, 5.98, tile_w - 0.4, 0.85, label, size=13, colour=INK)
    return (f"{missing:,} of {grid:,} station-hours never arrived. The white bands are days a station sent "
            f"nothing; the full-width band in January is a feed outage at all stations. Our rules: fill gaps of "
            f"up to 3 hours only, never fill rain, blank broken sensors such as {flat:,} flat-line hours, but "
            f"keep real extremes like Deepavali. A person reviewed the ten largest unexplained values.")


def slide_6_heatmap(prs, d):
    s = d["s"]
    pt, wc = s["peak_timing"], s["weekday_check"]
    slide = content_slide(prs, "PM2.5 climbs from 18:00 and peaks 19:00–22:00 on every day of the week")
    add_picture(slide, CHARTS / "1_heatmap_hour_weekday.png", MARGIN, 1.5, w=12.1)
    add_card(slide, MARGIN, 5.85, 5.9, 1.05)
    add_text(slide, MARGIN + 0.25, 5.95, 5.4, 0.9,
             f"No weekday stands out once festivals are removed: gap {wc['worst_minus_best']} µg/m³, "
             f"permutation test p = {wc['permutation_p_value']}",
             size=14, colour=INK, anchor=MSO_ANCHOR.MIDDLE)
    add_card(slide, MARGIN + 6.2, 5.85, 5.9, 1.05)
    add_text(slide, MARGIN + 6.45, 5.95, 5.4, 0.9,
             f"{pt['pct_edge_peaks_all']:.0f}% of evenings have no clear peak: PM2.5 is still rising at 23:00",
             size=14, colour=INK, anchor=MSO_ANCHOR.MIDDLE)
    return (f"Our hour-by-weekday heatmap. Every row goes dark after 18:00 and is darkest around 20 to 21:00. "
            f"Monday looked worst at first, but both Deepavalis fall on Mondays; with festivals removed the gap "
            f"is {wc['worst_minus_best']} micrograms and a permutation test gives p = "
            f"{wc['permutation_p_value']}, pure chance. Also, one evening in four is still rising at 11 PM, "
            f"because the night air traps pollution near the ground.")


def slide_7_rain(prs, d):
    r = d["s"]["rain_effect"]
    slide = content_slide(prs, f"Rain does not delay the peak: rainy evenings peak "
                               f"{abs(r['peak_height_change_pct']):.0f}% lower and "
                               f"{abs(r['peak_hour_shift_h']):.1f} h earlier")
    add_picture(slide, CHARTS / "2_rain_vs_dry_zscore.png", MARGIN, 1.6, w=8.2)
    add_card(slide, 9.15, 1.6, 3.58, 2.15)
    add_text(slide, 9.4, 1.72, 3.1, 1.95,
             [f"{r['n_rainy_evenings']} rainy vs {r['n_dry_evenings']:,} dry station-evenings",
              f"Same month, same day type",
              f"95% CI: {r['peak_height_change_ci'][0]}% to {r['peak_height_change_ci'][1]}%"],
             size=14, colour=INK)
    add_card(slide, 9.15, 3.95, 3.58, 2.15, fill="FDE3D6")
    add_text(slide, 9.4, 4.07, 3.1, 0.45, "Not a cause", size=18, bold=True, colour=AMBER)
    add_text(slide, 9.4, 4.55, 3.1, 1.5,
             "Rainy days are already cleaner at noon, before the rain. Rain marks cleaner weather; "
             "we do not claim rain cleans the air.", size=13, colour=INK)
    source_line(slide, "Chart joins two sources: air quality (OpenAQ) and rain (Open-Meteo). "
                       "z-score: 0 = each station's own average.")
    return (f"This chart joins air quality with rain, in z-scores so busy and quiet stations compare fairly. "
            f"We expected rain to push the peak later. Instead, comparing like with like, same month and same "
            f"kind of day, rainy evenings peak {abs(r['peak_height_change_pct']):.0f} percent lower and "
            f"{abs(r['peak_hour_shift_h']):.1f} hours earlier. But look at noon: the orange line is already low "
            f"before any rain. So we say rain goes with cleaner evenings, not that rain causes it.")


def slide_8_season(prs, d):
    s = d["s"]
    w, ev = s["worst"], s["events"]
    diwali_pct = (ev["diwali_19_23_mean"] / ev["diwali_matched_19_23_mean"] - 1) * 100
    slide = content_slide(prs, "Dry-season evenings and Deepavali night are the worst of the year")
    add_picture(slide, CHARTS / "4_evening_by_month.png", MARGIN, 1.6, w=5.95)
    add_picture(slide, CHARTS / "5_event_diwali.png", MARGIN + 6.15, 1.6, w=5.95)
    stat_card(slide, MARGIN, 4.3, 5.95, 2.3, f"{w['worst_months_pm25'][0]} µg/m³",
              f"evening mean in {month_short(w['worst_months'][0])}, the worst month; "
              f"{min(w['best_months_pm25'])} in {month_short(w['best_months'][-1])}")
    stat_card(slide, MARGIN + 6.15, 4.3, 5.95, 2.3, f"+{diwali_pct:.0f}%",
              f"Deepavali night 2025, 19:00–23:00: {ev['diwali_19_23_mean']:.0f} vs "
              f"{ev['diwali_matched_19_23_mean']:.0f} µg/m³ on {ev['diwali_n_matched_days']} matched normal evenings")
    return (f"When is it worst? The dry months, November to April. {month_short(w['worst_months'][0])} averaged "
            f"{w['worst_months_pm25'][0]} micrograms in the evening, the monsoon months "
            f"{min(w['best_months_pm25'])} to {max(w['best_months_pm25'])}. And one night beats them all: on "
            f"Deepavali the evening was {diwali_pct:.0f} percent above matched normal evenings."
            + (f" {len(d['diwali_filled'])} of those hours were missing at every station and filled, so the true "
               f"peak may be higher still." if d["diwali_filled"] else ""))


def slide_9_recommendation(prs, d):
    s = d["s"]
    pt, w = s["peak_timing"], s["worst"]
    trends = d["trends"]
    slide = content_slide(prs, "What the city can do before the next festive season")
    actions = [
        ("1", "Alert by 18:00", f"for the 19:00–22:00 window, which holds {pt['pct_peaks_19_to_22']:.0f}% of peaks"),
        ("2", "Focus on Nov–Apr", "and add a standing alert for Deepavali and other festival nights"),
        ("3", "One rule, every day", "no later rainy-day schedule and no weekday-specific rules"),
        ("4", "Measure the outer city", "Whitefield, Electronic City and Yelahanka have no monitor in our data"),
    ]
    card_w, card_h, gap = 5.9, 2.0, 0.3
    for i, (num, head, text) in enumerate(actions):
        x = MARGIN + (i % 2) * (card_w + gap)
        y = 1.7 + (i // 2) * (card_h + gap)
        add_card(slide, x, y, card_w, card_h)
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.3), Inches(y + 0.35), Inches(0.8), Inches(0.8))
        circle.fill.solid()
        circle.fill.fore_color.rgb = rgb(NIGHT)
        circle.line.fill.background()
        add_text(slide, x + 0.3, y + 0.35, 0.8, 0.8, num, size=24, bold=True, colour=WHITE,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        add_text(slide, x + 1.35, y + 0.3, card_w - 1.6, 0.5, head, size=20, bold=True, colour=NIGHT)
        add_text(slide, x + 1.35, y + 0.85, card_w - 1.6, 1.05, text, size=14, colour=INK)
    if trends is not None:
        rho = trends[("AQI bangalore", "evening_pm25_week")]
        add_text(slide, MARGIN, 6.35, 12.1, 0.6,
                 f"People already look for this: weekly searches for \"AQI bangalore\" rise with evening PM2.5 "
                 f"(Spearman rho = {rho:+.2f}, Google Trends).", size=14, italic=True, colour=MUTED)
    return ("Four things the city can do. One: send evening pollution alerts by 6 PM for the 7 to 10 window. "
            "Two: concentrate them on the dry season, November to April, and make Deepavali a standing alert. "
            "Three: keep it simple, one rule for every day; no later rainy-day schedule, rain-day rules for "
            "riders should be about road safety. Four: put monitors where we are blind, in the outer city. "
            "And residents already search for AQI in bad weeks, so alerts will find an audience.")


def slide_10_limits(prs, d):
    s = d["s"]
    unusable = log_rows(d, "Station-evenings with fewer")
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background(slide, NIGHT)
    add_text(slide, MARGIN, 0.4, 12.1, 1.2, "What our data cannot see", size=30, bold=True, colour=WHITE)
    add_card(slide, 8.0, 1.5, 4.73, 4.4, fill=WHITE)
    add_picture(slide, CHARTS / "6_station_coverage_map.png", 8.15, 1.6, h=4.2)
    limits = [
        f"7 monitors, all within {d['max_km']} km of the centre: the outer city is invisible",
        "One weather point for the whole city; local storms can be missed",
        f"{unusable:,} station-evenings too incomplete to time the peak",
        "Rain goes with cleaner weather; we cannot separate cause from correlation",
        "No traffic counts: \"traffic\" is an explanation, not a measurement",
    ]
    y = 1.6
    for text in limits:
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(MARGIN), Inches(y + 0.12), Inches(0.18), Inches(0.18))
        dot.fill.solid()
        dot.fill.fore_color.rgb = rgb(AMBER)
        dot.line.fill.background()
        add_text(slide, MARGIN + 0.4, y, 6.8, 0.8, text, size=16, colour=WHITE)
        y += 0.85
    add_text(slide, MARGIN, 6.3, 7, 0.7, "Thank you. Questions?", size=26, bold=True, colour=AMBER)
    return (f"To be honest about the limits: all seven monitors sit within {d['max_km']} kilometres of the "
            f"centre, so the outer city is invisible to us. We have one weather point for the whole city. "
            f"{unusable:,} station-evenings were too incomplete to time. And because rainy days are cleaner overall, we "
            f"cannot prove rain is the cause. With traffic counts and more monitors we could go further. "
            "Thank you, we are happy to take questions.")


# ---------------------------------------------------------------------------
# Speaker script and rendering
# ---------------------------------------------------------------------------

SLIDE_SECONDS = [30, 45, 40, 45, 45, 45, 50, 45, 50, 25]  # 7 minutes = 420 s in total


def speaker_script(notes, d):
    """report/speaker_script.md: who says what, and for how long. Suggested speakers: two slides each."""
    names = list(d["team"]["name"]) if d["team"] is not None else [f"Member {i + 1}" for i in range(5)]
    lines = ["# Speaker script (7 minutes, 10 slides)", "",
             "Generated by `src/15_build_slides.py` from the same numbers as the slides. "
             "Suggested split: two slides per member so every member presents (rubric: team participation). "
             "Change the speakers if your team prefers.", "",
             "| Slide | Speaker (suggested) | Time | Clock |", "|---|---|---|---|"]
    clock = 0
    for i, seconds in enumerate(SLIDE_SECONDS):
        start = clock
        clock += seconds
        lines.append(f"| {i + 1} | {names[i // 2 % len(names)]} | {seconds} s | "
                     f"{start // 60}:{start % 60:02d} – {clock // 60}:{clock % 60:02d} |")
    lines.append("")
    for i, note in enumerate(notes):
        lines += [f"## Slide {i + 1} — {names[i // 2 % len(names)]} ({SLIDE_SECONDS[i]} s)", "", note, ""]
    (REPORT / "speaker_script.md").write_text("\n".join(lines))
    print(f"  report/speaker_script.md written ({sum(SLIDE_SECONDS)} s in total)")


def main():
    d = load()
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SLIDE_W), Inches(SLIDE_H)
    builders = [slide_1_title, slide_2_answer, slide_3_data, slide_4_pipeline, slide_5_cleaning,
                slide_6_heatmap, slide_7_rain, slide_8_season, slide_9_recommendation, slide_10_limits]
    notes = []
    for build in builders:
        note = build(prs, d)
        prs.slides[len(notes)].notes_slide.notes_text_frame.text = note
        notes.append(note)
    out = REPORT / "slides.pptx"
    prs.save(str(out))
    print(f"  {out.relative_to(ROOT)} written ({len(prs.slides)} slides)")
    speaker_script(notes, d)

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(REPORT), str(out)],
                       check=True, capture_output=True)
        print("  report/slides.pdf written")


if __name__ == "__main__":
    main()
