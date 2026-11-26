"""
common.py — small helpers that every numbered script shares.

Why a shared file? Every script needs the same three things:
  1. the folder paths and study settings (city, dates),
  2. a polite, cached way to call web APIs,
  3. a way to append rows to the cleaning log and the source register.
Putting them here means each rule is written once, so it is also explained once.
"""

import csv
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths. Everything is relative to the repo root, so the project runs the same
# on every teammate's laptop.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
CLEAN = ROOT / "data" / "clean"
MANUAL = ROOT / "data" / "manual"
TABLES = ROOT / "outputs" / "tables"
CHARTS = ROOT / "outputs" / "charts"
CLEANING_LOG = ROOT / "outputs" / "cleaning_log.csv"
SOURCE_LOG = INTERIM / "source_access_log.csv"

# Read secrets and settings from .env (never hard-code keys in code).
load_dotenv(ROOT / ".env")

CITY = os.getenv("CITY", "Bengaluru")
DATE_START = os.getenv("DATE_START", "2025-10-01")
DATE_END = os.getenv("DATE_END", "2026-11-20")

# Bengaluru bounding box: min lon, min lat, max lon, max lat.
# It covers the BBMP area plus the outskirts (Kengeri, Whitefield, Yelahanka,
# Electronic City). OpenAQ expects exactly this order for `bbox`.
BENGALURU_BBOX = (77.40, 12.80, 77.80, 13.15)

# City-centre point used for the single city-wide weather series.
BENGALURU_CENTRE = (12.9716, 77.5946)  # (lat, lon)


def ensure_folders():
    """Create the output folders if a fresh clone does not have them yet."""
    for folder in [RAW, INTERIM, CLEAN, MANUAL, TABLES, CHARTS]:
        folder.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Cached, polite HTTP GET.
# Why cache? The brief says we have no time to collect twice. If a response is
# already saved in data/raw/, we read the file instead of calling the API again.
# Why sleep and retry? OpenAQ allows 60 requests/minute and 2,000/hour and
# answers 429 when we go faster. We pause between calls and back off on errors.
# ---------------------------------------------------------------------------
MIN_SECONDS_BETWEEN_CALLS = 1.1
_last_call_time = 0.0


def cache_path(source, url, params):
    """Build a stable file name from the URL and its parameters."""
    key_text = url + json.dumps(params or {}, sort_keys=True)
    digest = hashlib.sha1(key_text.encode("utf-8")).hexdigest()[:16]
    folder = RAW / source
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}.json"


def get_json(source, url, params=None, headers=None, max_retries=5):
    """
    Return the JSON body for url+params, from cache if we have it.
    `source` is a short name like "openaq" or "openmeteo"; it decides the
    data/raw/<source>/ folder and appears in the source access log.
    """
    global _last_call_time
    path = cache_path(source, url, params)

    # 1. Cache hit: no network call at all.
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)["body"]

    # 2. Cache miss: call the API, retrying on rate limits and server errors.
    for attempt in range(1, max_retries + 1):
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call_time)
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.time()

        response = requests.get(url, params=params, headers=headers, timeout=60)

        if response.status_code == 200:
            body = response.json()
            # Save the request details next to the body, so the raw file
            # explains itself. We never store the API key.
            record = {
                "url": url,
                "params": params,
                "accessed_utc": datetime.now(timezone.utc).isoformat(),
                "status": response.status_code,
                "body": body,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f)
            log_source_access(source, response.url, len(response.content))
            return body

        if response.status_code in (429, 500, 502, 503, 504):
            # Back off: 5 s, 10 s, 20 s, ... so we stop hammering the server.
            pause = 5 * (2 ** (attempt - 1))
            print(f"  {source}: HTTP {response.status_code}, retry {attempt} in {pause}s")
            time.sleep(pause)
            continue

        # Any other error (401 bad key, 404, 422 bad parameters) will not fix
        # itself, so stop and show the message instead of hiding it.
        raise RuntimeError(
            f"{source} returned HTTP {response.status_code} for {response.url}\n"
            f"{response.text[:500]}"
        )

    raise RuntimeError(f"{source}: gave up after {max_retries} retries on {url}")


def log_source_access(source, full_url, n_bytes):
    """Append one line per real download; the source register is built from this."""
    SOURCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    is_new = not SOURCE_LOG.exists()
    with open(SOURCE_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["source", "url", "accessed_utc", "bytes"])
        writer.writerow([source, full_url, datetime.now(timezone.utc).isoformat(), n_bytes])


# ---------------------------------------------------------------------------
# Cleaning log: one row per decision, with real row counts.
# Every script calls log_decision(...) instead of writing to the CSV directly,
# so the columns always match what the brief asks for.
# ---------------------------------------------------------------------------
CLEANING_LOG_COLUMNS = ["id", "stage", "problem_found", "rows_affected", "action_taken", "why"]


def log_decision(stage, problem_found, rows_affected, action_taken, why):
    """Append one decision to outputs/cleaning_log.csv and print it."""
    CLEANING_LOG.parent.mkdir(parents=True, exist_ok=True)
    is_new = not CLEANING_LOG.exists()

    # Next id = number of existing data rows + 1.
    next_id = 1
    if not is_new:
        with open(CLEANING_LOG, encoding="utf-8") as f:
            next_id = sum(1 for _ in f)  # header line counts as 1, so this is already +1

    with open(CLEANING_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(CLEANING_LOG_COLUMNS)
        writer.writerow([next_id, stage, problem_found, int(rows_affected), action_taken, why])

    print(f"  [log #{next_id}] {stage}: {problem_found} -> {action_taken} ({rows_affected} rows)")


def reset_cleaning_log_for_stage(stage):
    """
    Remove earlier rows for one stage before a script re-runs, so `make all`
    twice does not duplicate entries. Ids are renumbered afterwards.
    """
    if not CLEANING_LOG.exists():
        return
    with open(CLEANING_LOG, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    kept = [r for r in rows if r["stage"] != stage]
    with open(CLEANING_LOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CLEANING_LOG_COLUMNS)
        writer.writeheader()
        for new_id, row in enumerate(kept, start=1):
            row["id"] = new_id
            writer.writerow(row)


def openaq_headers():
    """OpenAQ v3 wants the key in the X-API-Key header on every request."""
    key = os.getenv("OPENAQ_API_KEY", "")
    if not key or key == "paste-your-key-here":
        raise SystemExit(
            "OPENAQ_API_KEY is missing. Do manual step M1 (see MANUAL_STEPS.md), "
            "then put the key in .env"
        )
    return {"X-API-Key": key}
