# The 8 PM Problem — Bengaluru (Case Study B)

**Question:** Does rain delay, flatten or worsen Bengaluru's evening PM2.5 peak, and on which weekdays and months is the evening pollution rush worst?

**Decision it serves:** when the city should issue evening pollution alerts, and whether rain-day rules (delivery riders, staggered office hours) need different timing.

**Repository:** https://github.com/punyashloka2030-debug/eight-pm-problem

> Status: **Phase 1 (Frame)**. This README grows each phase. Manual steps are tracked in [MANUAL_STEPS.md](MANUAL_STEPS.md).

## Setup

```bash
# 1. Python environment
python -m venv .venv
source .venv/bin/activate          # fish shell: source .venv/bin/activate.fish
                                   # Windows: use WSL2 (see M3)
pip install -r requirements.txt

# 2. Secrets
cp .env.example .env               # then fill in the values (M1 OpenAQ key, M2 MySQL)

# 3. Java 17 for PySpark (M3), then check:
python src/00_spark_hello.py
```

## Phase 1 checks

```bash
make smoke       # 1 day x 1 station from OpenAQ and Open-Meteo
make stations    # all Bengaluru monitors + PM2.5 coverage for the date range
```

## Run everything (filled in as phases are built)

```bash
make all
```

## Data sources

| Source | Method | Needs |
|---|---|---|
| OpenAQ v3 API (hourly PM2.5, PM10, NO2, CO) | `src/01_find_stations.py`, `src/02_collect_openaq.py` | free API key (M1) |
| Open-Meteo Historical Weather API | `src/03_collect_weather.py` | nothing (no key) |
| Karnataka holiday and festival calendar | `src/04_build_calendar.py` draft + human check (M6) | — |
| Google Trends (search interest) | manual CSV export (M7) | browser |
| CPCB CCR portal | manual download, only if OpenAQ is thin (M8) | browser (captcha) |

## Folder map

See the structure in `MANUAL_STEPS.md` and the comments at the top of each script in `src/`.
