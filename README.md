# Broadway creative-team network

**How Broadway creative teams form, disperse, and reunite over time.** This pipeline builds
the dataset behind that question. The unit of analysis is the *creative team* of each
Broadway musical: composer, lyricist, book writer, director, choreographer, orchestrator,
music director, designers and producers. Each person's origin (birthplace, citizenship,
birth year) is a secondary attribute, used for a map view and for filtering. Performers
are optional and kept in a separate table. IBDB is not available, so every record comes
from **Wikidata** (SPARQL endpoint) and **English Wikipedia** (MediaWiki API). The
pipeline pulls everything first and flags questionable records instead of dropping
them; filtering and cleaning decisions come later.

## Setup

Python 3.10 or newer.

```bash
cd broadway-network
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Before a full run, identify yourself to Wikimedia. Either edit `CONTACT_EMAIL` in
`config.py` or set:

```bash
export BROADWAY_CONTACT_EMAIL="you@nyu.edu"
```

> **Google Drive / Dropbox users:** a synced folder is slow with thousands of small
> files (we measured ~0.3 s per cached-file read in Google Drive). Keep the venv and
> the data outside the synced folder:
> ```bash
> python3 -m venv ~/venvs/broadway && source ~/venvs/broadway/bin/activate
> export BROADWAY_DATA_DIR=~/broadway-data     # data/raw, interim, processed go here
> ```
> `outputs/` (small CSVs and figures) stays in the project folder either way.

## Running the pipeline

Run the steps in order from the project root:

```bash
python scripts/01_build_show_list.py
python scripts/02_wikidata_credits.py
python scripts/03_fetch_wikitext.py
python scripts/04_parse_infoboxes.py
python scripts/04b_parse_casts.py          # optional: performers, separate table
python scripts/05_merge_resolve.py
python scripts/06_coverage_audit.py
python scripts/07_spotcheck_sample.py
```

Every script accepts:

| flag | effect |
|---|---|
| `--limit N` | only the first N shows (in `show_id` order); for quick tests |
| `--refresh` | ignore cached raw responses and re-download |
| `-v` | debug logging |

**Quick test:** run every step with `--limit 20` (about 2 minutes once the APIs respond).
In step 01, `--limit` also caps the Wikidata queries and the category crawl, so a test
run doesn't download the full show list. Later steps take the first N shows of
whatever `shows.parquet` contains.

**Re-runs are safe.** Every HTTP response is cached under `data/raw/`, so a re-run
makes no network requests unless you pass `--refresh` or the inputs changed. Outputs
are written atomically, so an interrupted run never leaves a half-written file.
`07_spotcheck_sample.py` will not overwrite a spot-check you have started filling in
(use `--force` to draw a new sample).

### Expected runtime and size (full run)

These are estimates. The small-sample runs were measured; the full-run figures are
extrapolated from them.

| step | requests (approx.) | time |
|---|---|---|
| 01 | ~5 SPARQL + ~30 MediaWiki | 2–5 min |
| 02 | ~15 credit + ~30 people SPARQL | 2–5 min |
| 03 | ~50 MediaWiki (50 articles each) | 2–4 min |
| 04, 04b | local parsing | 2–5 min each |
| 05 | ~200 MediaWiki + ~80 SPARQL | 5–15 min |
| 06, 07 | local | < 1 min |

Total is roughly **20–40 minutes** and **~200–300 MB** on disk (mostly article
wikitext). The Wikidata Query Service sometimes rate-limits clients hard (during this
project's development it allowed only 1 request per minute for a while). The client
honors `Retry-After` (capped at 10 min) and retries 6 times, so a throttled run takes
longer but still finishes. Re-running after a failure resumes from the cache.

## What each step reads and writes

| step | reads | writes |
|---|---|---|
| **01_build_show_list** | Wikidata, Wikipedia category tree | `data/interim/shows.parquet`, `data/interim/categories_visited.csv`, `data/interim/wikidata_ids_verified.csv` |
| **02_wikidata_credits** | `shows.parquet`, Wikidata | `data/interim/credits_wikidata.parquet`, `data/interim/people_wikidata.parquet` |
| **03_fetch_wikitext** | `shows.parquet`, MediaWiki API | `data/raw/wikitext/*.json` (one per article), `data/interim/wikitext_index.parquet` |
| **04_parse_infoboxes** | wikitext | `data/interim/credits_wikipedia.parquet`, `infobox_shows.parquet`, `productions_wikipedia.parquet`, `outputs/tables/infobox_parse_issues.csv` |
| **04b_parse_casts** | wikitext, Wikidata | `data/processed/cast_credits.parquet` |
| **05_merge_resolve** | all interim credit/people tables, MediaWiki + Wikidata for link → QID and new people | `data/processed/credits.parquet`, `people.parquet`, `shows.parquet`, `data/interim/credit_mentions.parquet`, `outputs/tables/unresolved_names.csv` |
| **06_coverage_audit** | processed tables | `outputs/tables/show_set.csv`, `coverage_by_role_decade.csv`, `people_coverage.csv`, `cast_coverage.csv` (each with a `show_set` column: `core` / `all_candidates`), `outputs/figures/coverage_heatmap.png` (core set), `coverage_heatmap_all_candidates.png` |

**Core show set** (step 06, `src/filters.py`): all candidates minus pages found only in a per-show Wikipedia subcategory (songs, albums, films, people) minus shows with a year before `CORE_MIN_YEAR` (1900, in `config.py`), and minus shows with no year from any source (mostly minor early shows with no Wikipedia article; they cannot be placed in a time window). Revues named by year ("Ziegfeld Follies of 1916") get their year from the title in step 05. This only selects rows for the audit; nothing is removed from `data/`. `outputs/tables/show_set.csv` lists every show with its `exclusion_reason`.
| **07_spotcheck_sample** | processed tables | `outputs/tables/spotcheck.csv`; `--score` prints error rates |

### How shows are found (step 01)

* **Wikidata A:** items with an IBDB show ID (P1219) that are typed as a musical
  (P31, P136 or P7937 pointing to Q2743 or a subclass), or as a dramatico-musical
  work (Q58483083). Few Broadway musicals carry `instance of: musical` directly.
  Most are "dramatico-musical work" or "literary work" with a musical genre.
* **Wikidata B:** musical-typed items whose first-performance location (P4647) or
  location (P276) is a Broadway theatre (Q235065) or has an IBDB venue ID (P1217).
* **Wikipedia:** `Category:Broadway musicals` plus one level of subcategories. The
  subcategories are per-show categories (Cats, Hamilton, …) that also hold songs and
  films, so pages found there are flagged with `wp_category_depth = 1`.
  Poster/image/song/album subcategories are skipped.
* Wikipedia titles are mapped to QIDs through the page's `wikibase_item` property, and
  all sources are deduplicated on the QID. Articles without a Wikidata item get
  `show_id = "enwiki:<Title>"`.
* Nothing is filtered. Columns `wd_is_musical`, `wd_dramatico_musical`,
  `wd_broadway_venue`, `in_wd_*_query`, `in_wp_category` and `wp_category_depth` let you
  filter later.

### How credits are extracted (step 04)

* **Infobox** (`extraction = "infobox"`): the person fields of `{{Infobox musical}}` /
  `{{Infobox play}}` (music, lyrics, book, writer, …). Lists (`plainlist`, `ubl`,
  `<br>`, commas, "and", "&") are split, refs and footnotes stripped, and wikilink
  targets kept. Unlinked names are kept with `is_linked = False`. Qualifiers such as
  "(additional lyrics)" or "revised by" are kept in `role_raw`.
* **Prose** (`extraction = "prose"`): sentences such as "orchestrations by [[X]]",
  "directed and choreographed by X", or "X serving as musical director". This is the
  only Wikipedia source for directors, choreographers, orchestrators, music directors
  and designers (the musical infobox has no fields for them). Prose often describes
  revivals, London runs or films, so each row carries `context_years`,
  `mentions_revival / tour / london / film_tv / original`, the section heading and the
  sentence itself.

### Person resolution (step 05)

1. A Wikidata credit uses its QID.
2. A wikilink is mapped to a QID through the linked article's Wikidata sitelink; a link
   to an article without an item becomes `enwiki:<Title>`.
3. Unlinked names are matched by exact normalized name (accents, punctuation and
   Jr./II stripped): first against people credited on the **same show** (catches
   `lyrics = Stephen Sondheim` when the name was linked a line above), then by
   **surname within the same show** (catches "directed by Lapine"), then against
   **everyone in the dataset**. A match must be unique.
4. Anything else becomes `name:<normalized name>` and is listed for review.

## Files for manual review

| file | what to do |
|---|---|
| `outputs/tables/unresolved_names.csv` | Names that couldn't be resolved (`unresolved`), matched several people (`ambiguous`), or don't look like names (`implausible_name`, e.g. "1956 version"; these are excluded from `credits.parquet`). `suggested_enwiki` / `suggested_qid` come from a Wikipedia title lookup and are **not applied automatically** (a same-name article may be someone else). Fill `resolved_qid_manual` to record decisions. |
| `outputs/tables/infobox_parse_issues.csv` | Articles with no infobox, templates the parser dropped, infobox fields it didn't recognise. |
| `outputs/tables/spotcheck.csv` | 50 random credits (seed 42) with source links and evidence. Fill `correct` with y/n, then run `python scripts/07_spotcheck_sample.py --score` for the error rate (with 95 % CI) by source, extraction and role. |

## Wikidata IDs used

Every ID was found by label search against the live endpoint, not guessed. Each run
re-checks the live English label of every ID it uses and aborts if one doesn't match
(`src/wikidata.py`; results in `data/interim/wikidata_ids_verified.csv`).

| ID | label | used for |
|---|---|---|
| P31 / P279 | instance of / subclass of | typing |
| P136 | genre | musical typing |
| P7937 | form of creative work | musical typing |
| P1219 | Internet Broadway Database show ID | show list, `ibdb_id` |
| P1217 | Internet Broadway Database venue ID | Broadway venue test |
| P1220 | Internet Broadway Database person ID | `ibdb_person_id` |
| P1191 | date of first performance | opening year |
| P4647 | location of first performance | Broadway venue test |
| P276 | location | Broadway venue test |
| P577 / P571 | publication date / inception | fallback year |
| P86 | composer | role |
| P676 | lyricist | role |
| P87 | librettist | role → book_writer |
| P57 | director | role |
| P1809 | choreographer | role |
| P10806 | orchestrator | role |
| P3300 | musical conductor | role → music_director (no "music director" property exists) |
| P4608 / P2554 | scenographer / production designer | role → scenic_designer |
| P2515 | costume designer | role |
| P5026 | lighting designer | role |
| P5028 | sound designer | role |
| P5880 / P5881 | video / projection designer | role → projection_designer |
| P6086 | dramaturge | role → other_creative |
| P162 / P1431 | producer / executive producer | role → producer |
| P272 | production company | role → production_company |
| P50 / P170 / P58 | author / creator / screenwriter | role → author_unspecified / creator_unspecified |
| P767 + P3831 | contributor + "object of statement has role" qualifier | role from the qualifier |
| P161 + P453 | cast member + character role | 04b cast |
| P19 | place of birth | birthplace |
| P625 | coordinate location | birthplace lat/lon |
| P27 | country of citizenship | citizenship |
| P569 | date of birth | birth year |
| Q2743 | musical | typing |
| Q58483083 | dramatico-musical work | typing |
| Q235065 | Broadway theatre | venue test |
| Q5 | human | `is_human` |

## Known limitations

* **The infobox describes the work and its original production.** It has no fields for
  directors, choreographers, orchestrators, music directors or designers, so those roles
  come only from prose, which is pattern-matched and mixes original, revival, tour,
  London and film credits. Use `is_original_production` and the context flags, and
  check `spotcheck.csv` error rates before relying on these roles.
* **Orchestrators and music directors are mostly only in article prose**, and often not
  even there; expect low coverage for them. Check `coverage_heatmap.png` before testing
  any hypothesis that depends on them.
* **Wikidata is thin for creative roles.** In test samples it held composer, lyricist and
  librettist, and almost no directors, choreographers or designers. Coverage is also
  thinner for older shows.
* **Birthplace is sparse for lesser-known people**: well-known creatives usually have it,
  but people known only from a red link or an unlinked name have no QID and so no
  origin data.
* **Cast data is messy**: tables vary in layout (colspan/rowspan, multi-row headers,
  "other notable performers" columns), and lists use either "Character – Actor" or
  "Actor as Character". `is_original_broadway` is a best guess from column or section
  labels and is often unknown.
* **Name matching is exact.** Spelling variants ("Alex. A. Aarons" vs "Alex A. Aarons")
  and pseudonyms are not merged automatically; they surface in `unresolved_names.csv`.
* **Show coverage is limited by what the sources record.** A musical with no IBDB ID on
  Wikidata, no Broadway-venue statement and no article in the category tree is missing.
* **Opening year** prefers the first Broadway line of the infobox's `productions` field,
  then the infobox premiere date, then Wikidata (first performance → publication →
  inception). The source is in `year_source`.

## Data dictionary

### `data/processed/credits.parquet`: one row per (show, person, role)

| column | type | description |
|---|---|---|
| show_id | str | Wikidata QID of the show, or `enwiki:<Title>` |
| title | str | show title |
| year | Int64 | opening year (see `shows.year_source`) |
| person_id | str | QID, `enwiki:<Title>` (article without Wikidata item), or `name:<normalized>` (unresolved) |
| person_name | str | Wikidata label if known, else the name as written |
| role | str | normalized role, one of: composer, lyricist, book_writer, playwright, conceived_by, director, choreographer, orchestrator, music_director, music_supervisor, arranger, scenic_designer, costume_designer, lighting_designer, sound_designer, projection_designer, producer, production_company, author_unspecified, creator_unspecified, other_creative |
| role_raw | str | all raw role strings merged into this row, `" \| "`-separated (e.g. `book (revised book)`, `prose: orchestrations by`, `librettist`) |
| source | str | `wikidata`, `wikipedia`, or `wikidata;wikipedia` |
| is_original_production | boolean | True / False / NA. True for authorship roles and infobox credits; for prose it is inferred from context (year near the original Broadway year, "original"/"premiere" wording; False for revival/tour/London/film context). True if any mention is True. |
| extraction | str | `wikidata`, `infobox`, `prose` (`;`-joined if several) |
| resolution | str | how person_id was obtained: `wikidata_qid`, `wikilink_qid`, `wikilink_no_qid`, `name_same_show`, `surname_same_show`, `name_exact_global`, `unresolved`, `ambiguous` |
| n_mentions | int | number of mentions merged into this row |

Every individual mention, with its sentence and context flags, is in
`data/interim/credit_mentions.parquet`.

### `data/processed/people.parquet`: one row per person_id

| column | type | description |
|---|---|---|
| person_id | str | as in credits |
| name | str | Wikidata label, or most common written form |
| qid | str | Wikidata QID (null for `enwiki:` / `name:` ids) |
| enwiki_title | str | English Wikipedia article |
| birthplace | str | place of birth label (first value if several, sorted by QID) |
| birthplace_qid | str | QID of that place |
| lat, lon | float | coordinates of that birthplace |
| citizenship | str | all countries of citizenship, `" \| "`-joined |
| birth_year | Int64 | year of birth (first date if several) |
| is_human | boolean | instance of human (False for duos like "Kander and Ebb", companies) |
| ibdb_person_id | str | IBDB person ID(s) from Wikidata |
| id_type | str | `qid`, `enwiki`, or `name` |
| n_shows | int | number of shows credited |
| roles | str | all roles held, `" \| "`-joined |
| n_birthplaces, citizenship_qids, birth_date | | raw detail for multi-valued fields |

### `data/processed/cast_credits.parquet`: one row per (show, character, performer, production)

| column | type | description |
|---|---|---|
| show_id | str | as in credits |
| character | str | character name as written |
| person_name | str | performer name as written |
| person_link | str | wikilink target, if linked |
| person_qid | str | QID (Wikidata cast statements only; not yet resolved for Wikipedia rows) |
| is_linked | bool | performer name was a wikilink |
| is_plausible_name | bool | heuristic: looks like a personal name |
| note | str | annotation next to the name, e.g. "replaced by" |
| production_label | str | table column header (e.g. "Broadway 1960") or section heading |
| is_original_broadway | boolean | True / False / NA, best guess from the label |
| extraction | str | `table`, `list (character – actor)`, `list (actor as character)`, `wikidata` |
| section | str | article section path |
| source | str | `wikipedia` or `wikidata` |

### `data/processed/shows.parquet`

`show_id, title, year, year_source, wikidata_qid, enwiki_title, ibdb_id, opening_year`
(Wikidata), `original_broadway_year` (infobox productions), `premiere_year`
(infobox), `has_infobox, n_credits, n_people`, plus the step-01 discovery flags
described above.

## Project layout

```
broadway-network/
  config.py              shared settings: User-Agent, endpoints, sleeps, batch sizes, paths
  requirements.txt
  src/
    http_client.py       cached, rate-limited, retrying client (only the two allowed hosts)
    wikidata.py          verified Wikidata IDs, SPARQL helpers, people fetch
    wikipedia.py         category crawl, title -> QID, batched wikitext
    wikitext.py          wikitext -> text with links, name splitting, section splitting
    names.py             name / title normalization
    roles.py             fixed role vocabulary + mapping
    common.py            CLI flags, logging, parquet I/O
  scripts/               01 ... 07 (see above)
  data/raw|interim|processed/
  outputs/figures|tables/
```
