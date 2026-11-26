# Makefile — one command per pipeline stage. `make all` rebuilds raw -> charts.
# Scripts for later phases are added as we build them; a missing script means
# that phase has not been built yet.

PY ?= python

.PHONY: all smoke stations collect flatten clean spark mysql analysis charts report zip

all: collect clean spark mysql analysis charts report

# Phase 1 checks
smoke:
	$(PY) src/00_smoke_test.py

stations:
	$(PY) src/01_find_stations.py

# Phase 2: download (cached in data/raw/, so re-running costs nothing)
collect: stations
	$(PY) src/02_collect_openaq.py
	$(PY) src/03_collect_weather.py
	$(PY) src/04_build_calendar.py

# Phase 2-3: flatten JSON, fix time and types, gaps and outliers
clean:
	$(PY) src/05_flatten_json.py
	$(PY) src/06_time_and_types.py
	$(PY) src/07_gaps_outliers.py

# Phase 3: PySpark resample-and-join, plus the notebook with saved outputs
spark:
	$(PY) src/08_spark_job.py
	jupyter nbconvert --to notebook --execute --inplace notebooks/spark_job.ipynb

mysql:
	$(PY) src/09_load_mysql.py

analysis:
	$(PY) src/10_analysis.py
	$(PY) src/12_inventory_vprofile.py

charts:
	$(PY) src/11_charts.py

# Phase 4: report and slides via pandoc
report:
	cd report && pandoc report.md -o report.docx
	cd report && pandoc report.md -o report.pdf
	cd report && pandoc slides.md -o slides.pptx
