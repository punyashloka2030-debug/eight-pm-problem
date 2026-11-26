# The 8 PM Problem — Bengaluru (Case Study B)

**Question:** Does rain delay, flatten or worsen Bengaluru's evening PM2.5 peak, and on which weekdays and
months is the evening pollution rush worst?

**Decision it serves:** when the city should send evening pollution alerts, and whether rain-day rules need
different timing.

**Answer in one line:** PM2.5 peaks between 19:00 and 22:00 on every weekday alike; rainy evenings peak about
29% lower and 0.8 h earlier (not later); the dry months and Deepavali night are the worst.

**Repository:** https://github.com/punyashloka2030-debug/eight-pm-problem

| Deliverable | File |
|---|---|
| Report (sections a–i + appendices) | `report/report.pdf` (also `.docx`, `.md`) |
| Slides (10) and speaker script | `report/slides.pptx`, `report/speaker_script.md` |
| Code: pandas, SQL, PySpark | `src/`, `sql/`, `notebooks/spark_job.ipynb` |
| Cleaned data | `data/clean/` (rebuilt by `make clean`; samples committed) |
| Cleaning log | `outputs/cleaning_log.csv` |
| Viva preparation | `QA_PREP.md` |
| Team contribution split | `CONTRIBUTIONS.md` |

---

## 1. Set up (once)

You need: Python 3.12+ (we used 3.14), Java 17 or 21 (for PySpark), MySQL 8 (we used Docker), LibreOffice
(only to turn the report and slides into PDF), and git.

```bash
git clone https://github.com/punyashloka2030-debug/eight-pm-problem.git
cd eight-pm-problem

python -m venv .venv
source .venv/bin/activate          # fish shell: source .venv/bin/activate.fish
pip install -r requirements.txt     # includes pandoc (pypandoc_binary), so no system pandoc is needed

cp .env.example .env               # then fill in the values (next two steps)
```

**OpenAQ API key (free).** Sign up at https://explore.openaq.org, open Account, copy the key into `.env` as
`OPENAQ_API_KEY=...`.

**MySQL 8 in Docker.** Choose your own passwords. We used port 3307 because 3306 was taken; use the same port
in `.env` (`MYSQL_PORT=3307`).

```bash
docker run --name eightpm-mysql -e MYSQL_ROOT_PASSWORD=rootpass -e MYSQL_DATABASE=eightpm -e MYSQL_USER=eightpm -e MYSQL_PASSWORD=eightpmpass -p 3307:3306 -d mysql:8.4 --local-infile=1
```

Next time, just start it: `docker start eightpm-mysql` (with `sudo` if your user is not in the docker group).

**Check everything works:**

```bash
python src/00_smoke_test.py      # OpenAQ and Open-Meteo both PASS
python src/00_spark_hello.py     # ends with "Spark OK"
```

## 2. Run everything

```bash
make all
```

That runs, in order (each stage can also be run alone, e.g. `make charts`):

| make target | Scripts | What happens |
|---|---|---|
| `collect` | 01, 02, 03, 04 | find stations, download OpenAQ and Open-Meteo JSON (cached in `data/raw/`), draft calendar |
| `clean` | 05, 05b, 06, 07 | flatten JSON, load Trends, time zones / types / units, gaps and outliers |
| `spark` | 08 + notebook | PySpark resample, join and aggregate; re-executes `notebooks/spark_job.ipynb` |
| `mysql` | 09 | load 4 MySQL tables, ER diagram, run the 7 queries in `sql/queries.sql` |
| `analysis` | 10, 12 | every number (`outputs/tables/analysis_summary.json`), inventory, source register, V profile |
| `charts` | 11 | the charts in `outputs/charts/` |
| `report` | 14, 15 | `report/report.md/.docx/.pdf`, `report/slides.pptx/.pdf`, `report/speaker_script.md` |

The first `make collect` downloads about 190 MB in about 12 minutes (432 OpenAQ requests at most one per
1.1 s). Later runs read the cache in `data/raw/` and cost nothing. `src/13_compare_spreadsheet.py` (the M10
spreadsheet check) is run by hand: `python src/13_compare_spreadsheet.py`.

## 3. Raw data: where it comes from

The raw JSON (`data/raw/`, ~186 MB) is not in git; `make collect` downloads it again. Sources:

| Source | How | Notes |
|---|---|---|
| OpenAQ v3 API — hourly PM2.5, PM10, NO2, CO, 7 Bengaluru reference monitors | `src/01_find_stations.py`, `src/02_collect_openaq.py` | free API key; stations in `data/manual/stations_approved.csv` |
| Open-Meteo Historical Weather API — hourly rain, temperature, humidity, wind | `src/03_collect_weather.py` | no key |
| Karnataka holiday and festival calendar | `src/04_build_calendar.py` (draft) → checked by hand → `data/manual/calendar_verified.csv` | DPAR 16 HHL 2024 and 16 HHL 2025 notifications |
| Google Trends (Karnataka, weekly) | exported by hand from trends.google.com → `data/manual/trends_*.csv` | steps in `MANUAL_STEPS.md` (M7) |

Full URLs, access dates and terms of use: `outputs/tables/source_register.csv`.

## 4. Files written by people (not by code)

Everything in `data/manual/` is human input, and the pipeline never overwrites it:
`stations_approved.csv` (M5), `calendar_verified.csv` (M6), `trends_*.csv` (M7), `spreadsheet_pivot.csv` and
`m10_answers.csv` (M10), `outlier_verdicts.csv` (M11), `team.csv` and `team_name.txt`. The report's reflection
(`report/reflection.md`) and AI-use appendix (`report/appendix_ai_use.md`) are also edited by hand.
How each manual step was done: `MANUAL_STEPS.md`.

## 5. Folder map

```
src/            numbered scripts, run in order (common.py = shared helpers)
sql/            schema.sql (tables and keys), queries.sql (7 queries)
notebooks/      spark_job.ipynb (the PySpark job with its saved outputs)
data/raw/       cached API answers (not in git)
data/interim/   flattened and typed tables
data/clean/     cleaned tables used by the analysis (parquet; CSV samples in git)
data/manual/    human input (see section 4)
outputs/        cleaning_log.csv, tables/ (every number), charts/
report/         report, slides, speaker script, reflection notes, images
```

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `Illegal Parquet type: INT64 (TIMESTAMP(NANOS,false))` in Spark | save parquet with `save_parquet` from `common.py` (microseconds) |
| Spark cannot start | install Java 17 or 21 and check `java -version` |
| `Can't connect to MySQL server` | start the container; check `MYSQL_PORT` in `.env` |
| OpenAQ returns 401 | wrong or missing `OPENAQ_API_KEY` in `.env` |
| Google Trends shows "429 Too Many Requests" | open the Trends home page first, wait, then the explore page |
| fish warns about "Primary Device Attribute query" | harmless; the Claude app's terminal does not answer that query |

## 7. Team

See `CONTRIBUTIONS.md`. Generative AI use is disclosed in Appendix F of the report (`report/appendix_ai_use.md`).
