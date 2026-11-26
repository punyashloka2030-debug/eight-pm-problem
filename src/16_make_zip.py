"""
16_make_zip.py — build the submission folder TeamName_FinalSubmission.zip (brief, Section 6).

The brief asks for six items in one zipped folder:
  1 report   2 slides   3 code (pandas, SQL, PySpark)   4 data (cleaned, or a sample if > 50 MB,
  with raw-data download steps in the README)   5 README   6 team contribution split

The team name comes from data/manual/team_name.txt, so the zip is already named correctly
(spaces removed: "Sata and Dory Letting" -> SataAndDoryLetting_FinalSubmission.zip).

Never included: .env (API key and passwords), data/raw/ (re-downloadable, ~190 MB), the .venv.

Run:  python src/16_make_zip.py
"""

import zipfile

from common import MANUAL, ROOT

DATA_LIMIT_MB = 50

# (what the brief calls it, files or folders to include)
CONTENTS = [
    ("1 report", ["report/report.pdf", "report/report.docx", "report/report.md"]),
    ("2 slides", ["report/slides.pptx", "report/slides.pdf", "report/speaker_script.md"]),
    ("3 code", ["src", "sql", "notebooks", "Makefile", "requirements.txt", ".env.example"]),
    ("4 data", ["data/clean", "data/manual", "outputs"]),
    ("5 README", ["README.md", "MANUAL_STEPS.md", "QA_PREP.md"]),
    ("6 contribution split", ["CONTRIBUTIONS.md"]),
]

# Files that must never go into the zip, whatever folder they are in.
NEVER = {".env"}
SKIP_FOLDERS = {"__pycache__", ".ipynb_checkpoints"}


def team_folder_name():
    path = MANUAL / "team_name.txt"
    name = path.read_text().strip() if path.exists() else "TeamName"
    # Keep letters and digits only, capitalising each word: "Sata and Dory Letting" -> "SataAndDoryLetting".
    return "".join(word[:1].upper() + word[1:] for word in name.split() if word.isalnum()) or "TeamName"


def files_under(path):
    """Every file under a folder (or the file itself), skipping caches and secrets."""
    if path.is_file():
        return [path]
    return sorted(f for f in path.rglob("*")
                  if f.is_file() and f.name not in NEVER and not SKIP_FOLDERS & set(f.parts))


def main():
    folder = f"{team_folder_name()}_FinalSubmission"
    out = ROOT / f"{folder}.zip"
    missing, total_bytes, data_bytes = [], 0, 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item, paths in CONTENTS:
            for rel in paths:
                path = ROOT / rel
                if not path.exists():
                    missing.append(rel)
                    continue
                for f in files_under(path):
                    zf.write(f, f"{folder}/{f.relative_to(ROOT)}")
                    size = f.stat().st_size
                    total_bytes += size
                    if item == "4 data":
                        data_bytes += size
    print(f"  {out.name}: {total_bytes / 1e6:.1f} MB before compression, {out.stat().st_size / 1e6:.1f} MB zipped")
    print(f"  data: {data_bytes / 1e6:.1f} MB (limit {DATA_LIMIT_MB} MB before a sample is needed)")
    if data_bytes / 1e6 > DATA_LIMIT_MB:
        print("  !! data is over the limit: include samples instead of the full tables")
    if missing:
        print(f"  !! missing (build them first, e.g. `make report`): {', '.join(missing)}")


if __name__ == "__main__":
    main()
