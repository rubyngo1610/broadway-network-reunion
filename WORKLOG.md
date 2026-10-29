# Work log

Newest entries at the bottom. Record every full run, every code change that affects outputs, and every manual edit to a review file. Findings and next steps are in `../Pipeline Findings.md`.

## 2026-10-26: Pipeline built and tested

- Built steps 01–07 and 04b, plus `config.py`, `src/` and the README. Every step was tested with `--limit 20` and ran cleanly end to end.
- Bugs fixed during testing:
  - The section splitter missed headings nested in unclosed tags (*Camelot*: 4 of 25 found). Now uses a regex on heading lines.
  - A regex for stripping leading lowercase words backtracked catastrophically and hung step 04b.
  - Later Broadway columns in cast tables were flagged as the original cast.
  - "directed and choreographed by" produced only the director credit.
  - "Sir [[Name]]" was parsed as the name "Sir".
- Wikidata's query service was in outage mode during development (1 request per minute). The HTTP client honors `Retry-After`.

## 2026-10-26: First full run

- **Setup:**
  - venv at `~/venvs/broadway`
  - `BROADWAY_DATA_DIR=~/broadway-data`, which keeps the data outside Google Drive
  - contact email `hn2589@nyu.edu`, set in `config.py`
- **Results by step:**

  | Step | Result |
  |---|---|
  | 01 | 1,622 candidate shows. One 2-minute wait after an HTTP 429, then recovered. ~4 min |
  | 02 | 3,600 Wikidata credits, 1,383 people |
  | 03 | 1,509 articles, none missing |
  | 04 | 12,212 Wikipedia credit rows (4,449 infobox, 7,763 from article sentences) |
  | 04b | Cast table |
  | 05 | 12,553 credits, 1,503 shows, 5,562 people (2,956 with a Wikidata ID); 3,677 unresolved names written for review. ~2.5 min |
  | 06 | Coverage tables and heatmap |

- `~/broadway-data` is about 40 MB.

## 2026-10-26: Core show set added to step 06

- New file `src/filters.py` defines the **core show set**. It excludes:
  - pages found only in a per-show Wikipedia subcategory (166)
  - shows with a known year before `CORE_MIN_YEAR` (new in `config.py`, set to 1900): 96 shows

  Shows with an unknown year are kept (338).
- Step 06 now reports `core` (1,360 shows) and `all_candidates` side by side, with a `show_set` column in every table.
- New output `outputs/tables/show_set.csv` gives the exclusion reason for each show.
- The heatmap now shows the core set. The old all-candidates version is saved as `coverage_heatmap_all_candidates.png`.
- Step 06 was rerun on the full data.

## 2026-10-26: Findings written

- Wrote `../Pipeline Findings.md`.

## 2026-10-27: Spotcheck (step 07)

- Ran `07_spotcheck_sample.py --force` on the full data: 50 credits, seed 42.
- **Checking:**
  - An AI assistant (Claude) checked each credit against the downloaded articles. Those notes are tagged `[AI]`.
  - Ruby reviewed the results in Numbers, filled the 3 Wikidata-only rows from IBDB, and added sources in `notes`.
- **Rule:** `correct` = the person held this role on this show in any production. Problems with the original-production flag are recorded in `notes`.
- **Result: 7/50 wrong = 14.0% (95% Wilson CI 7.0–26.2%).** The answered file is `outputs/tables/spotcheck.csv`. Don't regenerate it.
- **Fix to step 07:** `--score` now skips the extra table-name line that Numbers adds above the header when it exports CSV (`read_answers()`).
- **Manual correction:** the Numbers edit had changed row 1's `person_id` (*Eubie!* / Billy Wilson) to the show's ID (`Q5405380`). It was restored to `name:billy wilson`.

## 2026-10-27: Findings updated

- `../Pipeline Findings.md` now uses core-set numbers and includes the spotcheck results.

## 2026-10-28: Version control

- Ran `git init` and made the first commit of the code, README, review tables and this log. `.gitignore` excludes `data/` and the figures.
