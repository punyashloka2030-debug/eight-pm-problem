# Team contribution split — Team Sata and Dory Letting

The team agreed an **equal split**. Each member owns one part of the project, presents that part in the talk
(`report/speaker_script.md`). Every piece of work is listed under exactly one member. Code was written with the help of generative AI, as disclosed in Appendix F of the report.

| Member | USN | Role | Slides | Contribution % |
|---|---|---|---|---|
| Punyashloka Mahapatra | 1RV23EC110 | Project lead and framing | 1–2 | 20% |
| Shubhaditya Bechan | 1RV23AI099 | Data sources and big-data pipeline | 3–4 | 20% |
| Manan Joshi | 1RV23CD029 | Cleaning and database | 5–6 | 20% |
| Tanikonda Sai Karan | 1RV23IS129 | Analysis and charts | 7–8 | 20% |
| Wangchen T | 1RV23CY060 | Calendar, recommendation and presentation | 9–10 | 20% |
| **Total** | | | | **100%** |

---

## Punyashloka Mahapatra — project lead and framing

- **Question and decision:** chose the city, dates and question, and tied them to the city's decision
  (report sections a and b).
- **Checking the sources work (Phase 1):** `src/00_smoke_test.py`, `src/00_spark_hello.py`.
- **Station choice:** `src/01_find_stations.py`, and the 60% coverage rule (70% left only 5 stations) — M5,
  `data/manual/stations_approved.csv`.
- **Setup:** OpenAQ API key (M1), MySQL in Docker on port 3307 (M2), Java 17 and Spark (M3).
- **Repository and reproducibility:** GitHub repository, `Makefile`, `README.md`, the report builder
  `src/14_build_report.py`, the submission zip `src/16_make_zip.py`.

## Shubhaditya Bechan — data sources and big-data pipeline

- **Collection from the JSON APIs:** `src/02_collect_openaq.py` (204,584 hourly readings, month by month,
  cached) and `src/03_collect_weather.py` (9,984 weather hours from Open-Meteo); shared API helper in
  `src/common.py`.
- **Flattening JSON into tables:** `src/05_flatten_json.py` (nested records and parallel arrays).
- **Text-derived source:** Google Trends export (M7) and `src/05b_load_trends.py`.
- **PySpark job:** `src/08_spark_job.py` and `notebooks/spark_job.ipynb` — resample, join with weather and
  calendar, group by hour and weekday, row counts after every stage (279,552 → 55,026 joined).
- **Source register and V profile:** `src/12_inventory_vprofile.py`, `report/v_profile.md`, report section c.

## Manan Joshi — cleaning and database

- **Time zones, types and units:** `src/06_time_and_types.py` — UTC → IST with a 0-mismatch check, the
  half-hour weather alignment, text → float, NO2/CO from ppb.
- **Gaps and outliers:** `src/07_gaps_outliers.py` — 75,136 missing hours counted, 3-hour fill rule,
  flat-lines and zeros blanked, real events kept, usable-evening rule; the gap chart.
- **Human outlier review (M11):** `src/07b_review_outliers.py`, `data/manual/outlier_verdicts.csv`.
- **Cleaning log:** `outputs/cleaning_log.csv`, report section e and Appendix A.
- **Database:** `sql/schema.sql` (4 tables, primary and foreign keys), `src/09_load_mysql.py`, the ER diagram,
  the 7 queries in `sql/queries.sql` (Appendix B).

## Tanikonda Sai Karan — analysis and charts

- **Analysis:** `src/10_analysis.py` — evening peaks, rainy vs dry evenings within month × day type,
  bootstrap confidence intervals, the fixed-effects regression, the weekday permutation test, z-scores,
  AQI categories, the Deepavali and wettest-day event studies.
- **Charts:** `src/11_charts.py` — the hour-by-weekday heatmap, the rain z-score chart (two sources joined),
  peak hours, months, Deepavali, station map and Trends chart, all with finding-style titles.
- **Spreadsheet vs pandas (M10):** the LibreOffice pivot, `src/13_compare_spreadsheet.py`
  (168/168 cells match), Appendix D.
- **Findings:** report section f.

## Wangchen T — calendar, recommendation and presentation

- **Holiday and festival calendar:** `src/04_build_calendar.py` and the check against the Karnataka
  government notification (M6) — two dates corrected, school breaks added
  (`data/manual/calendar_verified.csv`).
- **Recommendation and limitations:** report sections g and h.
- **Reflection:** report section i (`report/reflection.md`, from `report/reflection_notes.md`).
- **Presentation:** `src/15_build_slides.py`, `report/slides.pptx`, `report/speaker_script.md`.

---

Repository commits per member — see manual step M9.
