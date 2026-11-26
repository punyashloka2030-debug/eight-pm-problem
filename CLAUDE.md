# CLAUDE.md — project context for Claude Code

Read this first. It is the hand-over from the earlier build session (2026-11-26), which ran in a
sandbox without network access and passed files to the user as git patches. From now on Claude Code
runs on the user's laptop and can run everything directly.

## The assignment

Case Study B, "The 8 PM Problem", in a Data and Storytelling course (Module 1). The brief is
`docs/brief_case_B.pdf` and is the source of truth; the rubric (15 marks) is in its Section 7.
The user's original detailed prompt (phases, the AUTO/MANUAL STOP-block format, report order, slides,
QA_PREP) governs how to work. Its key rules:
- Split work into AUTO and MANUAL steps. At a MANUAL step, STOP, print the ═══ MANUAL STEP Mn ═══ block
  (WHY / DO THIS / PUT RESULT HERE / HOW I'LL CHECK / TIME) and wait for "done". Keep MANUAL_STEPS.md ticked.
- **Never fabricate data, numbers or findings.** Every number in the report comes from a pipeline file.
- Beginner-readable code: short functions, a "why" comment above each block, no clever one-liners.
  The user must explain every line in a viva.
- Commit after each logical step. Mark human gaps in the report as [[TODO-HUMAN: ...]].
- Never say "rain causes X". Name the confounders.

## The user's machine

- Arch-based (CachyOS) Linux, **fish shell** (activate with `source .venv/bin/activate.fish`, not `activate`).
- Python 3.14 in `.venv`; pandas 3.x; PySpark 4.3.0; Java 17 (`jdk17-openjdk`).
- MySQL 8.4 in Docker: container `eightpm-mysql`, **port 3307** (3306 was taken), DB/user `eightpm`.
  Start it with `sudo docker start eightpm-mysql` if it is stopped.
- The user is a beginner: give exact commands, one step at a time.
- GitHub: https://github.com/punyashloka2030-debug/eight-pm-problem (gh CLI logged in).

## Decisions already made (do not silently change them)

- City Bengaluru; dates 2025-10-01 to 2026-11-20; question: "Does rain delay, flatten or worsen
  Bengaluru's evening PM2.5 peak, and on which weekdays and months is the evening pollution rush worst?"
- 7 OpenAQ reference stations at >= 60% PM2.5 coverage (70% left only 5; team chose 60% at M5):
  data/manual/stations_approved.csv. Old 5-digit sensor ids are empty; the new 1223xxxx ids carry the data.
- OpenAQ NO2/CO arrive in ppb -> converted to µg/m³ / mg/m³ at 25 °C, 1 atm.
- OpenAQ hours start at :00 IST; Open-Meteo hours start at :30 IST -> aligned in 06 (instantaneous vars at
  the mid-hour label; rain split half/half).
- Gap rule: forward-fill <= 3 h (pollutants), interpolate <= 3 h (smooth weather), never fill rain;
  an evening (17-23 IST) is usable for peak timing only with >= 6 of 7 real hours.
- Outliers: sensor failures (sentinel, out-of-range, negative, zero, flat-line >= 6 h / CO >= 12 h,
  isolated spike) are blanked; real events (festival nights, heavy rain, city-wide) are kept.
  M11 human verdicts live in data/manual/outlier_verdicts.csv and apply to whole episodes.
- All parquet is saved with `save_parquet` (microsecond timestamps) because Spark cannot read pandas'
  nanosecond timestamps. In Spark, `date_trunc` must be cast back to `timestamp_ntz`.
- Avoid `df.toPandas()` in PySpark (pandas 3 not fully supported); collect rows instead.
- Weekday claims: festivals excluded + permutation test; only name a "worst weekday" if p < 0.05.

## Real results so far (from outputs/tables/analysis_summary.json — re-read it, it may have changed)

- 204,584 OpenAQ hourly rows; full grid 279,552; weather 9,984 h; cleaning log 38 entries.
- Rain (within month x day type, 409 rainy vs 1,027 dry station-evenings): peak ~29% lower
  (95% CI -43 to -13%) and ~0.8 h EARLIER (CI -1.3 to -0.4 h); FE regression agrees. Hypothesis of a
  delay was reversed. Rainy days are already cleaner at noon (confounding by weather systems).
- Typical interior peak 20:00 (IQR 19-21); 25% of evenings are edge peaks (17:00 or still rising at 23:00).
- Worst months Nov 26, Mar 26, Apr 26; cleanest Jun-Aug 26. Deepavali 2025 night +136% vs matched days.
- Weekday ranking: re-run 10_analysis.py after update_11 and check `weekday_check`.

## Where things stand (updated 2026-11-26, end of the laptop session)

Run order: `make all` (01..12, 14, 15), then `make zip` (16). `13_compare_spreadsheet.py` is run by hand.

Done: every AUTO item. Report builder (14: report.md/.docx/.pdf, body ends on page 10), slides (15:
report/slides.pptx + speaker_script.md), QA_PREP.md, README rerun guide, CONTRIBUTIONS.md template,
zip builder (16), SUBMISSION_CHECK.md (rubric table). Manual steps done: M1-M3, M5-M8, M10, M11.
M6 corrected 2 calendar dates (Mahavir Jayanti 31 Mar, Valmiki Jayanti 25 Oct 2026); M7 Trends exported.

Human inputs live in data/manual/ (team.csv, team_name.txt, m10_answers.csv, calendar_verified.csv,
trends_*.csv, outlier_verdicts.csv) and report/reflection.md, report/appendix_ai_use.md.

Open MANUAL steps: M4 (add teammates), M9 (one commit per teammate), M12 (contribution %),
M13 (rehearse), M14 (make report zip, submit).

Note: the GitHub repo is PUBLIC and the report/slides contain members' names and USNs; pushes from the
assistant are blocked for that reason, so the user pushes. Cleaning-log rows are looked up by their
problem_found text (re-running one stage reorders the log).
