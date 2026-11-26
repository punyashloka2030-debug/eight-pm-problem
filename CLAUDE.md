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

## Where things stand

Run order: `make all` (see Makefile) = 01..12 scripts. Phase 1-3 code is done. MANUAL_STEPS.md has status.

Done manual steps: M1, M2, M3, M5, M10 (168/168 cells MATCH; screenshots in report/img/), M11.
Pending MANUAL steps: M4 (add teammates), M6 (verify calendar -> calendar_verified.csv, then re-run
07 onwards), M7 (Google Trends CSVs), M9 (one commit per teammate), M12 (contribution split),
M13 (rehearse), M14 (submit).

Pending AUTO work, in order:
1. Look at every chart in outputs/charts/ (render check: label collisions, titles).
   Weekday result: NO weekday stands out once festivals are excluded (gap 2.4 µg/m³, permutation p = 0.992).
2. M10 is done (src/13_compare_spreadsheet.py, report/spreadsheet_vs_pandas.md).
3. Google Trends loader exists (src/05b_load_trends.py + chart_trends in 11); it skips until M7 files exist.
4. Report: plan was src/14_build_report.py that fills every number from outputs/tables/*.json/*.csv, draws a
   pipeline diagram, and writes `report/report.md` in the brief's exact order (a-i), <= 10 pages + appendices, written for a
   non-technical commissioner, numbers only from pipeline files; render to .docx/.pdf (pandoc; PDF may
   need LibreOffice: `soffice --headless --convert-to pdf`). Use report/reflection_notes.md for section i.
5. Slides `report/slides.md` (<= 10, finding titles, speaker notes) -> .pptx; speaker script with timings.
6. QA_PREP.md (per script: what, 3 key lines, what breaks; 25 viva Q&As), README (full rerun guide),
   report/appendix_ai_use.md, contribution template, zip builder for TeamName_FinalSubmission.zip.
7. Final rubric table (15 marks) with files and ✅/⚠️, open manual steps, all [[TODO-HUMAN]] markers.
