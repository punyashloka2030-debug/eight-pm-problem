"""
04_build_calendar.py — build the DRAFT day-by-day calendar for our date range:
holidays, festivals, Sundays/second-and-fourth Saturdays, long weekends, season.

Output:  data/manual/calendar_draft.csv     one row per date, for a human to verify (M6)

After M6, the team saves the checked file as data/manual/calendar_verified.csv,
and later scripts use the verified file only.

Where the holiday dates come from (also listed in the source register):
  2025  Government of Karnataka, Notification-I, No. DPAR 16 HHL 2024
        (general holidays for 2025; copy hosted by CAG).            -> confidence "official"
  2026  Central Government offices in Karnataka, Annexure I 2026 (CAG).
        The Karnataka STATE list for 2026 was only found on secondary
        websites (e.g. keka.com), which disagree on some dates.      -> confidence "secondary"
  Rows where two sources disagree get needs_check = "yes" and a note.

Run:  python src/04_build_calendar.py
"""

from datetime import date, timedelta

import pandas as pd

from common import DATE_END, DATE_START, MANUAL, ensure_folders

SRC_KA_2025 = "Karnataka Notification-I 2025 (DPAR 16 HHL 2024)"
SRC_CENTRAL_2026 = "Central Govt offices in Karnataka 2026, Annexure I"
SRC_SECONDARY_2026 = "Karnataka 2026 general list via secondary site (keka.com)"

# ---------------------------------------------------------------------------
# Holidays and festivals inside our range, typed in from the sources above.
# Columns: date, name, is_general_holiday, is_festival, source, needs_check, note
#   is_general_holiday = Karnataka government offices closed (or would be, if the
#                        day were not already a Sunday / 2nd Saturday)
#   is_festival        = a festival or event that may change evening activity
#                        (fireworks, travel, shopping), holiday or not
# ---------------------------------------------------------------------------
EVENTS = [
    # ---- 2025 (official Karnataka notification) ----
    ("2025-10-01", "Mahanavami / Ayudha Pooja", 1, 1, SRC_KA_2025, "no", ""),
    ("2025-10-02", "Gandhi Jayanti / Vijayadashami", 1, 1, SRC_KA_2025, "no", ""),
    ("2025-10-07", "Maharshi Valmiki Jayanti", 1, 0, SRC_KA_2025, "no", ""),
    ("2025-10-20", "Naraka Chaturdashi (Deepavali)", 1, 1, SRC_KA_2025, "no",
     "Diwali night 1: fireworks expected"),
    ("2025-10-21", "Deepavali (Lakshmi Pooja / Amavasya)", 0, 1, "festival date, not in notification",
     "yes", "Not a Karnataka general holiday; some lists show it as a bank holiday. Fireworks expected"),
    ("2025-10-22", "Balipadyami, Deepavali", 1, 1, SRC_KA_2025, "no", "Diwali night 3"),
    ("2025-11-01", "Kannada Rajyotsava", 1, 1, SRC_KA_2025, "no", "Fell on a Saturday"),
    ("2025-11-08", "Kanakadasa Jayanti", 1, 0, SRC_KA_2025, "no",
     "Second Saturday, listed in the notification's note"),
    ("2025-12-25", "Christmas", 1, 1, SRC_KA_2025, "no", ""),
    ("2025-12-31", "New Year's Eve", 0, 1, "event, not a holiday", "no",
     "Large evening crowds in central Bengaluru"),
    # ---- 2026 ----
    ("2026-01-01", "New Year's Day", 0, 1, SRC_CENTRAL_2026 + " (restricted)", "no", "Restricted holiday only"),
    ("2026-01-15", "Makara Sankranti", 1, 1, SRC_SECONDARY_2026, "yes",
     "Central list says 14 Jan; Karnataka list (secondary) says 15 Jan"),
    ("2026-01-26", "Republic Day", 1, 0, SRC_CENTRAL_2026, "no", ""),
    ("2026-02-15", "Maha Shivaratri", 1, 1, SRC_SECONDARY_2026, "no", "Falls on a Sunday"),
    ("2026-03-19", "Ugadi", 1, 1, SRC_CENTRAL_2026, "no", "Both sources agree"),
    ("2026-03-21", "Khutub-e-Ramzan (Id-ul-Fitr)", 1, 1, SRC_CENTRAL_2026, "yes",
     "Moon-dependent; check the actual date"),
    ("2026-03-30", "Mahavir Jayanti", 1, 0, SRC_SECONDARY_2026, "yes",
     "Central list says 31 Mar; Karnataka list (secondary) says 30 Mar"),
    ("2026-04-03", "Good Friday", 1, 0, SRC_CENTRAL_2026, "no", ""),
    ("2026-04-14", "Dr. B.R. Ambedkar Jayanti", 1, 0, SRC_SECONDARY_2026, "no", ""),
    ("2026-04-20", "Basava Jayanti / Akshaya Tritiya", 1, 0, SRC_SECONDARY_2026, "yes",
     "Only secondary source found"),
    ("2026-05-01", "May Day / Buddha Purnima", 1, 0, SRC_CENTRAL_2026, "no", ""),
    ("2026-05-28", "Bakrid (Id-ul-Zuha)", 1, 1, SRC_SECONDARY_2026, "yes",
     "Central list says 27 May; Karnataka list (secondary) says 28 May; moon-dependent"),
    ("2026-06-26", "Last day of Muharram", 1, 0, SRC_CENTRAL_2026, "yes", "Moon-dependent"),
    ("2026-08-15", "Independence Day", 1, 0, SRC_CENTRAL_2026, "no", ""),
    ("2026-08-26", "Eid-e-Milad", 1, 0, SRC_CENTRAL_2026, "yes", "Moon-dependent"),
    ("2026-09-14", "Varasiddhi Vinayaka Vrata (Ganesh Chaturthi)", 1, 1, SRC_CENTRAL_2026, "no",
     "Both sources agree"),
    ("2026-10-02", "Gandhi Jayanti", 1, 0, SRC_CENTRAL_2026, "no", ""),
    ("2026-10-10", "Mahalaya Amavasye", 1, 0, SRC_SECONDARY_2026, "yes",
     "Second Saturday; reported in news coverage of the 2026 notification"),
    ("2026-10-20", "Mahanavami / Ayudha Pooja", 1, 1, SRC_SECONDARY_2026, "yes",
     "Central list puts Dussehra on 20 Oct; Karnataka list (secondary) has Ayudha Pooja 20 Oct"),
    ("2026-10-21", "Vijayadashami", 1, 1, SRC_SECONDARY_2026, "yes",
     "Central list says Dussehra 20 Oct; Karnataka list (secondary) says 21 Oct"),
    ("2026-10-26", "Maharshi Valmiki Jayanti", 1, 0, SRC_SECONDARY_2026, "yes",
     "Sources say 25 Oct (Sunday) or 26 Oct (Monday)"),
    ("2026-11-01", "Kannada Rajyotsava", 1, 1, SRC_SECONDARY_2026, "no", "Falls on a Sunday"),
    ("2026-11-08", "Naraka Chaturdashi / Deepavali", 1, 1, SRC_CENTRAL_2026, "no",
     "Falls on a Sunday; Central list has Diwali 8 Nov. Fireworks expected"),
    ("2026-11-09", "Deepavali (Lakshmi Pooja / Govardhan Puja)", 0, 1, SRC_CENTRAL_2026 + " (restricted)",
     "yes", "Not a Karnataka general holiday. Fireworks expected"),
    ("2026-11-10", "Balipadyami, Deepavali", 1, 1, SRC_SECONDARY_2026, "yes",
     "Only secondary source found"),
]


def season_for(day):
    """
    IMD's four Indian seasons, by month:
      Jan-Feb winter, Mar-May pre-monsoon (summer), Jun-Sep SW monsoon,
      Oct-Dec post-monsoon (NE monsoon). Season is a NOMINAL category here.
    """
    if day.month in (1, 2):
        return "winter"
    if day.month in (3, 4, 5):
        return "pre_monsoon"
    if day.month in (6, 7, 8, 9):
        return "sw_monsoon"
    return "post_monsoon"


def saturday_number(day):
    """1 for the first Saturday of the month, 2 for the second, and so on."""
    return (day.day - 1) // 7 + 1


def main():
    ensure_folders()

    # 1. One row for every date in our range.
    start = date.fromisoformat(DATE_START)
    end = date.fromisoformat(DATE_END)
    days = [start + timedelta(n) for n in range((end - start).days + 1)]
    cal = pd.DataFrame({"date": days})
    cal["weekday"] = [d.strftime("%A") for d in days]
    cal["season"] = [season_for(d) for d in days]

    # 2. Weekly off-days. Karnataka government offices close on Sundays and on
    #    the 2nd and 4th Saturday. Most Bengaluru private offices close every
    #    Saturday, so we keep both flags and say which one we use.
    cal["is_sunday"] = [d.weekday() == 6 for d in days]
    cal["is_govt_saturday_off"] = [d.weekday() == 5 and saturday_number(d) in (2, 4) for d in days]
    cal["is_weekend"] = [d.weekday() >= 5 for d in days]

    # 3. Join the holiday and festival list by date.
    events = pd.DataFrame(EVENTS, columns=["date", "holiday_name", "is_general_holiday",
                                           "is_festival", "source", "needs_check", "note"])
    events["date"] = pd.to_datetime(events["date"]).dt.date
    cal = cal.merge(events, on="date", how="left")
    cal["is_general_holiday"] = cal["is_general_holiday"].fillna(0).astype(int) == 1
    cal["is_festival"] = cal["is_festival"].fillna(0).astype(int) == 1
    cal["needs_check"] = cal["needs_check"].fillna("no")
    cal["holiday_name"] = cal["holiday_name"].fillna("")
    cal["source"] = cal["source"].fillna("")
    cal["note"] = cal["note"].fillna("")

    # is_holiday = a day most offices are closed: weekend OR general holiday.
    cal["is_holiday"] = cal["is_weekend"] | cal["is_general_holiday"]

    # 4. Long weekend rule (stated so it can be checked): a run of 3 or more
    #    consecutive is_holiday days. We mark every day in such a run.
    cal["is_long_weekend"] = False
    run_start = None
    for i, off in enumerate(list(cal["is_holiday"]) + [False]):  # sentinel ends the last run
        if off and run_start is None:
            run_start = i
        if not off and run_start is not None:
            if i - run_start >= 3:
                cal.loc[run_start:i - 1, "is_long_weekend"] = True
            run_start = None

    # 5. School breaks are left for the human check (M6): we did not find an
    #    official Karnataka school calendar for both years, so we do not guess.
    cal["school_break"] = ""

    out = MANUAL / "calendar_draft.csv"
    cal.to_csv(out, index=False)

    print(f"Wrote {out.relative_to(MANUAL.parent.parent)}: {len(cal)} days, "
          f"{cal['is_general_holiday'].sum()} general holidays, "
          f"{cal['is_festival'].sum()} festival days, "
          f"{cal['is_long_weekend'].sum()} long-weekend days, "
          f"{(cal['needs_check'] == 'yes').sum()} rows marked needs_check")


if __name__ == "__main__":
    main()
