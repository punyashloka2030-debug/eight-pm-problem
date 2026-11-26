# Submission check — rubric (15 marks) against our files

Status on 2026-11-26. ✅ = evidence is in the repo; ⚠️ = something the team still has to do.

| Component | Criterion (marks) | Our evidence | Status |
|---|---|---|---|
| Report | Question and decision framing (1) | Report sections a and b; README top | ✅ |
| Report | Data sourcing and scale (2) | 4 sources, 2 JSON APIs (OpenAQ, Open-Meteo), 14 months of hourly data, 204,584 rows (grid 279,552); source register and V profile in section c (`outputs/tables/source_register.csv`, `report/v_profile.md`) | ✅ |
| Report | Representation and SQL (1.5) | `sql/schema.sql` (4 tables, primary and foreign keys), `report/er_diagram.png`, 7 queries with JOINs and GROUP BYs and their outputs (Appendix B, `outputs/tables/sql_query_outputs.md`) | ✅ |
| Report | Cleaning and preprocessing (2.5) | Cleaning log (40 decisions, `outputs/cleaning_log.csv`), gap chart, UTC→IST with a 0-mismatch check, type casting, outliers vs real events with human review (M11), z-scores (chart 2) — section e and Appendix A | ✅ |
| Report | Analysis, PySpark and reproducibility (1.5) | `src/08_spark_job.py` + `notebooks/spark_job.ipynb` with row counts per stage; `make all`; README rerun guide | ⚠️ commits from **every** member (M4, M9) |
| Report | Narrative, visuals and limitations (1.5) | Finding-style chart titles, recommendation from evidence (section g), "association, not cause" stated, limitations (section h) | ✅ |
| Presentation | Storyline and clarity (2) | `report/slides.pptx` opens with the answer; script fits 7 minutes (`report/speaker_script.md`) | ⚠️ rehearse with a timer (M13) |
| Presentation | Visuals (1) | 10 slides, one idea each, charts from the report | ✅ |
| Presentation | Q&A (1.5) | `QA_PREP.md`: every script's key lines and 25 questions | ⚠️ every member studies it (M13) |
| Presentation | Team participation (0.5) | Script gives each member two slides | ⚠️ on the day |

## Deliverables (brief, Section 6)

| # | Item | File | Status |
|---|---|---|---|
| 1 | Report, ≤ 10 pages + appendices, order a–i | `report/report.pdf` (body ends on page 10) | ✅ |
| 2 | Slides, ≤ 10 | `report/slides.pptx` | ✅ |
| 3 | Code: pandas, SQL, PySpark | `src/`, `sql/`, `notebooks/` | ✅ |
| 4 | Data (cleaned, < 50 MB) + raw download steps | `data/clean/`, `data/manual/`, `outputs/` (3.9 MB); README section 3 | ✅ |
| 5 | README with setup, full rerun and repo link | `README.md` | ✅ |
| 6 | Team contribution split | `CONTRIBUTIONS.md` (equal, 20% each; every member's work listed) | ✅ — each member checks their own row (M9) |
| — | GenAI disclosure appendix | Report Appendix F (`report/appendix_ai_use.md`) | ✅ — read it and edit in your own words |
| — | Zipped folder named TeamName_FinalSubmission | `make zip` → `SataAndDoryLetting_FinalSubmission.zip` | ✅ build it again last, after all edits |

## Still open (manual steps)

M4 add teammates as GitHub collaborators · M9 one commit per teammate ·
M13 study QA_PREP.md and rehearse · M14 rebuild the zip and submit. Details in `MANUAL_STEPS.md`.

Also decide whether the repository stays **public**: it now shows every member's name and USN.
