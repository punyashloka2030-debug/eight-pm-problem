# MANUAL_STEPS.md — living checklist

Steps a human has to do (sign-ups, installs, captchas, verifying facts, screenshots).
Claude ticks a box only after running the check in **HOW I'LL CHECK**.
Steps marked *(details added later)* depend on data we haven't pulled yet. Their exact instructions will be filled in when we reach them.

## Status

- [x] M1 Get an OpenAQ API key → `.env` (verified 2026-11-26: OpenAQ PASS, Open-Meteo PASS)
- [x] M2 Install MySQL 8 (Docker or native), create DB + user → `.env` (Docker container eightpm-mysql, port 3307)
- [x] M3 Install Java 17, verify with a tiny Spark job
- [ ] M4 Create the GitHub repo, add teammates, push (repo created and pushed 2026-11-26; teammates still to be added)
- [x] M5 Approve city, dates and station list (2026-11-26: Bengaluru, 2025-10-01 to 2026-11-20, 7 stations at >=60% PM2.5 coverage → data/manual/stations_approved.csv)
- [x] M6 Verify the holiday and festival calendar draft (2026-11-26: checked against DPAR 16 HHL 2025 via KEA circular 089/2025; 2 dates corrected → data/manual/calendar_verified.csv)
- [x] M7 Export Google Trends CSVs (2026-11-26: 4 files, 60 weekly rows each, Karnataka)
- [ ] M8 CPCB portal downloads *(only if OpenAQ coverage is thin; details added if needed)*
- [ ] M9 Each teammate makes one meaningful commit *(tasks assigned in Phase 2)*
- [x] M10 Build the hour-by-weekday pivot in LibreOffice Calc (2026-11-26: 168/168 cells MATCH, max diff 0.005)
- [x] M11 Review the top 10 flagged outliers (2026-11-26: 10 verdicts → 21 hours failure, 5 hours real; data/manual/outlier_verdicts.csv)
- [ ] M12 Fill in the team contribution split *(template added in Phase 4)*
- [ ] M13 Read QA_PREP.md and rehearse the 7-minute talk *(script added in Phase 4)*
- [ ] M14 Rename the final zip with the team name and submit

---

## M1 — Get an OpenAQ API key

```
════════ MANUAL STEP M1: Get an OpenAQ API key ════════
WHY:      Data sourcing and scale (2 marks): OpenAQ is our JSON API and our hourly PM2.5 source.
DO THIS:
  1. Open https://explore.openaq.org in a browser.
  2. Click "Sign up" (top right). Register with your email, then click the
     verification link OpenAQ emails you.
  3. Sign in, open your account page (click your name → "Account",
     or go to https://explore.openaq.org/account).
  4. Copy the API key shown there.
  5. In the repo root run:   cp .env.example .env
  6. Open .env and replace  paste-your-key-here  with your key:
        OPENAQ_API_KEY=<your key>
     Save. Do NOT commit .env (it is already in .gitignore).
  7. Run:   python src/00_smoke_test.py
     and paste the printed table back to me.
PUT RESULT HERE: .env  →  OPENAQ_API_KEY
HOW I'LL CHECK:  The smoke test calls /v3/locations for the Bengaluru box. If the key works it
                 returns HTTP 200 with ≥1 location, and the OpenAQ row says PASS (≥12 of 24
                 hours on 2025-10-01). A 401 means the key is wrong.
TIME:     ~5 minutes
═══════════════════════════════════════════
```

## M2 — Install MySQL 8 and create the database

```
════════ MANUAL STEP M2: Install MySQL 8, create DB and user ════════
WHY:      Representation and SQL (1.5 marks): schema with keys, ER diagram, 5+ queries.
DO THIS (choose ONE option):
  Option A — Docker (easiest, same on every OS):
    1. Install Docker Desktop: https://www.docker.com/products/docker-desktop/ and start it.
    2. Run (one line; choose your own passwords):
       docker run --name eightpm-mysql -e MYSQL_ROOT_PASSWORD=rootpass -e MYSQL_DATABASE=eightpm -e MYSQL_USER=eightpm -e MYSQL_PASSWORD=eightpmpass -p 3306:3306 -d mysql:8.4 --local-infile=1
       (The database and user are created automatically by those -e settings.)
    3. Wait about 30 s, then test:
       docker exec -it eightpm-mysql mysql -ueightpm -peightpmpass -e "SELECT VERSION();"
  Option B — Native install:
    macOS:   brew install mysql && brew services start mysql
    Ubuntu:  sudo apt update && sudo apt install mysql-server && sudo systemctl start mysql
    Windows: download the MySQL 8 Installer from https://dev.mysql.com/downloads/installer/
             and choose "Server only".
    Then create the DB and user (macOS/Linux: sudo mysql ; Windows: MySQL 8 Command Line Client):
       CREATE DATABASE eightpm;
       CREATE USER 'eightpm'@'%' IDENTIFIED BY 'eightpmpass';
       GRANT ALL PRIVILEGES ON eightpm.* TO 'eightpm'@'%';
       FLUSH PRIVILEGES;
  Both options:
    4. Put the same values in .env: MYSQL_HOST=127.0.0.1, MYSQL_PORT=3306, MYSQL_DB=eightpm,
       MYSQL_USER=eightpm, MYSQL_PASSWORD=<your password>
PUT RESULT HERE: .env  →  MYSQL_HOST, MYSQL_PORT, MYSQL_DB, MYSQL_USER, MYSQL_PASSWORD
HOW I'LL CHECK:  Connect with SQLAlchemy using .env and run SELECT VERSION(); it must start with "8."
TIME:     ~10–20 minutes
═══════════════════════════════════════════
```

## M3 — Install Java 17 and test Spark

```
════════ MANUAL STEP M3: Install Java 17, verify a tiny Spark job ════════
WHY:      Analysis, PySpark and reproducibility (1.5 marks): PySpark needs Java to run.
DO THIS:
  1. Install Java 17 (Java 21 also works with PySpark 4):
     macOS:   brew install openjdk@17
              then add it to your PATH as the brew message says, e.g.
              echo 'export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
     Ubuntu:  sudo apt update && sudo apt install openjdk-17-jdk
     Windows: winget install EclipseAdoptium.Temurin.17.JDK
              (Spark on plain Windows also needs winutils.exe for writing files, so we
              recommend running the project inside WSL2 Ubuntu instead and using the Ubuntu line.)
  2. Check:   java -version        → must say 17 (or 21)
  3. In the repo, with the venv active:
       python -m venv .venv && source .venv/bin/activate     (Windows WSL: same)
       pip install -r requirements.txt
  4. Run:     python src/00_spark_hello.py
PUT RESULT HERE: nothing to save. Paste the last line printed by step 4.
HOW I'LL CHECK:  The output ends with "Rows: 3" and "Spark version: 4.x | Spark OK".
TIME:     ~15 minutes
═══════════════════════════════════════════
```

## M4 — GitHub repo, teammates, first push

```
════════ MANUAL STEP M4: Create the GitHub repo, add teammates, push ════════
WHY:      Reproducibility (1.5 marks): repo with commits from every member, plus the README link.
DO THIS:
  1. On https://github.com click "+" → "New repository". Name: eight-pm-problem.
     Visibility: Private (or as your instructor asks). Do NOT tick "Add a README"
     (we already have one).
  2. Repo page → Settings → Collaborators → "Add people" → add each teammate's GitHub username.
     Each teammate accepts the email invite.
  3. In the repo folder on your laptop:
       git remote add origin https://github.com/<your-user>/eight-pm-problem.git
       git push -u origin main
  4. Tell me the repo URL.
PUT RESULT HERE: README.md → "Repository" line (I'll fill it in once you give me the URL)
HOW I'LL CHECK:  git remote -v shows origin, and git ls-remote origin main matches the local HEAD.
TIME:     ~10 minutes
═══════════════════════════════════════════
```

## M5 — Approve city, dates and station list

```
════════ MANUAL STEP M5: Approve city, dates and stations ════════
WHY:      Question and decision framing (1 mark) and data scale (2 marks): lock scope by end of Phase 1.
DO THIS:
  1. Run:  python src/01_find_stations.py
  2. Open outputs/tables/station_coverage.csv and data/interim/stations_proposed.csv.
  3. Reply with "approve" or the changes you want: city (default Bengaluru), dates
     (default 2025-10-01 to 2026-11-20), and which stations to add or drop.
PUT RESULT HERE: data/interim/stations_proposed.csv (I'll copy the approved list to data/manual/stations_approved.csv)
HOW I'LL CHECK:  6–10 approved stations, written to stations_approved.csv. (Rule changed to ≥60% at M5: only 5 passed 70%.)
TIME:     ~10 minutes (team discussion)
═══════════════════════════════════════════
```

## M6 — Verify the holiday and festival calendar draft

```
════════ MANUAL STEP M6: Verify the calendar draft ════════
WHY:      Data sources (2 marks): "a holiday and festival calendar you build"; it feeds every
          holiday/festival comparison, so a wrong date would quietly bias results.
DO THIS:
  1. Open data/manual/calendar_draft.csv in LibreOffice Calc (or Google Sheets).
  2. Filter the column needs_check = yes (14 rows). For each one, read the note column and
     check the date against an official source:
       2025: Karnataka Notification-I (DPAR 16 HHL 2024), copy hosted by CAG:
             https://cag.gov.in/uploads/media/Karnataka-State-Holidays-2025-067764409e26023-56493682.pdf
       2026: Central Govt offices in Karnataka, 2026 list (CAG):
             https://cag.gov.in/uploads/media/Holiday-List-2026-069521fe6f358d0-89936988.pdf
             For the Karnataka STATE 2026 list, search the web for
             "DPAR 2026 general holidays notification Karnataka pdf" and use a
             government (.gov.in / .kar.nic.in) copy, not a news or HR website.
       Moon-dependent Islamic holidays: use the date the government actually declared.
  3. Fix any wrong date or name directly in the file. In needs_check write "checked"
     and add your source to the note.
  4. Fill the school_break column with "yes" for Karnataka state-school vacation days
     (Dasara break 2025, summer vacation 2026, Dasara break 2026) from the Karnataka
     School Education Department academic calendar. Write the source in note.
  5. Save as CSV with a NEW name:  data/manual/calendar_verified.csv
PUT RESULT HERE: data/manual/calendar_verified.csv
HOW I'LL CHECK:  416 rows, the same columns, no needs_check = "yes" left, dates parse,
                 and a diff against the draft listing exactly what you changed.
TIME:     ~30–40 minutes
═══════════════════════════════════════════
```

## M7 — Google Trends CSV exports

```
════════ MANUAL STEP M7: Export Google Trends CSVs ════════
WHY:      Data sourcing (2 marks): our unstructured / text-derived source (search interest).
DO THIS (repeat for each of the three terms):
  1. Open https://trends.google.com/trends/explore
  2. Search term box: type the term exactly:
       a) bangalore traffic     b) bangalore rain     c) AQI bangalore
  3. Region dropdown: India → Karnataka.
  4. Time dropdown → "Custom time range" → From 2025-10-01 To 2026-11-20 → OK.
     (A range over ~9 months comes back as WEEKLY values. That is expected; we note it.)
  5. Category: All categories.  Search type: Web search.
  6. On the "Interest over time" chart, click the download arrow (⤓) → CSV.
  7. Rename and move the file:
       a) data/manual/trends_bangalore_traffic.csv
       b) data/manual/trends_bangalore_rain.csv
       c) data/manual/trends_aqi_bangalore.csv
  8. Also export one CSV with all three terms on the same chart (click "+ Compare"),
     so they share one 0–100 scale:  data/manual/trends_all_three.csv
PUT RESULT HERE: data/manual/trends_*.csv  (4 files)
HOW I'LL CHECK:  Each file parses, has ~60 weekly rows from Oct 2025 to Nov 2026, and the header names
                 the Karnataka region.
TIME:     ~10 minutes
═══════════════════════════════════════════
```

## M10 — Hour-by-weekday pivot in a spreadsheet

```
════════ MANUAL STEP M10: Spreadsheet pivot vs pandas ════════
WHY:      Spreadsheets and dataframes: "build one hour-by-weekday pivot in a spreadsheet, rebuild it in
          pandas, and compare" (side-by-side note).
DO THIS:
  0. Start a timer: the note asks how long it took.
  1. libreoffice --calc data/manual/spreadsheet_export_city_hourly.csv
     Text Import window: tick "Comma" only → OK.  (9,385 rows: date, weekday, hour, pm25_city_mean)
  2. Click any cell inside the data → menu Insert → Pivot Table… → "Current selection" → OK.
  3. In the Pivot Table Layout window, drag:
       hour            → Row Fields
       weekday         → Column Fields
       pm25_city_mean  → Data Fields
     Double-click "Sum - pm25_city_mean" in Data Fields → choose "Average" → OK.
  4. Screenshot this layout window → save as report/img/m10_pivot_layout.png
  5. Click OK. The pivot appears on a new sheet. Screenshot it → report/img/m10_pivot_result.png
  6. With the pivot sheet open: File → Save As… → file name  spreadsheet_pivot.csv
     in the folder  data/manual/  → file type "Text CSV (.csv)" → Save →
     "Use Text CSV Format!" → Field delimiter "," → OK. (Only the current sheet is saved: that's fine.)
  7. Stop the timer. Then run:   python src/13_compare_spreadsheet.py
  8. Open report/spreadsheet_vs_pandas.md and replace the two [[TODO-HUMAN]] markers with your minutes
     and one or two sentences in your own words.
PUT RESULT HERE: data/manual/spreadsheet_pivot.csv, report/img/m10_pivot_layout.png, report/img/m10_pivot_result.png
HOW I'LL CHECK:  13_compare_spreadsheet.py prints "168 cells … MATCH". If it says DIFFERENT, the usual cause is
                 Sum instead of Mean in step 3.
TIME:     ~20–30 minutes
═══════════════════════════════════════════
```

## M11 — Review the top 10 flagged PM2.5 outliers

```
════════ MANUAL STEP M11: Real event or sensor failure? ════════
WHY:      Cleaning and preprocessing (2.5 marks): outliers "detected separately from real extreme
          events", with a human check, not just a rule.
DO THIS:
  1. Run:   python src/07b_review_outliers.py
  2. For each of the 10 cases, look at three things:
       a) This station, ±3 h: does the value BUILD UP and fade over hours (real), or jump from
          normal to huge and straight back (failure)?
       b) Other stations: are they high too (real, city-wide air), or normal (one sensor)?
       c) Rain / festival: fireworks nights and storms explain real extremes.
     A real event usually has a build-up AND either other stations high or a festival.
  3. Save your 10 answers in order, e.g.:
       python src/07b_review_outliers.py --save "real,failure,real,real,failure,real,real,real,failure,real"
  4. Write one sentence per case explaining your decision in report/reflection_notes.md
     (the Q&A may ask "how did you tell a sensor failure from Diwali night?").
PUT RESULT HERE: data/manual/outlier_verdicts.csv (written by --save; 07 never overwrites it)
HOW I'LL CHECK:  10 verdicts saved, each real_event or sensor_failure; I then make 07 apply them
                 (failures blanked, real events kept) and log how many changed.
TIME:     ~20 minutes
═══════════════════════════════════════════
```

## M14 — Rename and submit

```
════════ MANUAL STEP M14: Rename the final zip and submit ════════
WHY:      Deliverables: one zipped folder named TeamName_FinalSubmission.
DO THIS:
  1. Rename TeamName_FinalSubmission.zip, replacing TeamName with your team's name.
  2. Upload it wherever your instructor asked.
PUT RESULT HERE: the course submission portal
HOW I'LL CHECK:  You reply "submitted". I can't see the portal.
TIME:     ~2 minutes
═══════════════════════════════════════════
```
