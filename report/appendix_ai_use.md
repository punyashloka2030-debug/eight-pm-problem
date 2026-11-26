The brief allows generative AI with disclosure. This is what we used, what we asked for, and what we decided or
did ourselves.

**Tool.** Claude by Anthropic, used through Claude Code (a coding assistant that can read our files, run our
scripts and commit to git). It was used in two sessions: a first build session in a sandbox without internet
access (code passed to us as git patches), then a session on our own laptop (model: Claude Opus 5.5) that
could run the pipeline directly. Commits written by the assistant are marked "Co-Authored-By: Claude" in the
git history.

**What we asked it to do.**

* Plan the project in phases and split every step into automatic steps (code) and manual steps that a person
  has to do, stopping at each manual step with instructions.
* Write the pipeline scripts in `src/` (collection, JSON flattening, time zones and units, gaps and outliers,
  the PySpark job, MySQL loading and queries, analysis, charts, and `14_build_report.py`), with a comment above
  every block so we can explain each line.
* Draft the report text, filled automatically from the pipeline's own tables, and check every chart for
  layout problems.
* Check the 14 uncertain calendar dates against the official Karnataka 2026 holiday notification and news
  reports (manual step M6), and export the Google Trends CSVs in a browser (manual step M7), at our request.
* Draft this reflection (section i) from the dated notes in `report/reflection_notes.md`.

**Rules we gave it.** Never invent data, numbers or findings: every number in the report must come from a
pipeline file. Never say "rain causes X". Keep code beginner-readable. Mark anything a person has to supply.

**What we decided and did ourselves.**

* Chose the city, dates and question, and approved the station list; we lowered the coverage rule from 70% to
  60% when only 5 stations passed (M5).
* Created the OpenAQ key, installed MySQL and Java, and ran the pipeline on our laptop (M1 to M3).
* Built the hour-by-weekday pivot by hand in LibreOffice Calc and wrote the comparison note (M10).
* Judged the 10 largest unexplained PM2.5 readings as sensor failures or real events (M11).
* Corrected team details the assistant could not know (names, USNs, team name).

**What changed because of checks along the way.** A first weekday check named a "worst weekday" even in fake
data with no weekday effect, so it was replaced with a permutation test. The holiday calendar the assistant
drafted from a website had two wrong dates, found when it was checked against the government notification.
The Deepavali chart showed two hours that had been filled under our gap rule, and the report now says so. In
every case the number in the report comes from the re-run pipeline, not from the chat.

**How we check our understanding.** Before the viva, QA_PREP.md will list for every script what it does,
its key lines and what breaks, and each member rehearses explaining any step (manual step M13).
