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

## 2026-10-29: Planning documents

- **User study plan.** Wrote `../User Study Plan.md`, a formative study with 10 participants (feedback point 3):
  - 5 participants with theater knowledge and 5 data-literate
  - each uses the animated cohort view and the small-multiples baseline, in counterbalanced order
  - case studies: Rodgers (Hart → Hammerstein) and Lerner & Loewe; the practice case is Comden, Green & Styne
  - the plan includes the recruitment message, consent script, tasks, note-taking template and analysis plan
- **Posthumous "reunions."** Recurring partnerships with the longest gaps turned out to be posthumous shows (the Gershwins in 2015, Kern & Wodehouse in 2003). Added a note to the findings: drop credits after a person's death (now done in step 08).
- **Timeline.** Drafted the timeline up to the deadlines: Nov 3 update, Dec 1/8 presentation, Dec 14 report.
- **Prediction test design (feedback point 4).** Added section 8 to the findings: repeated time splits with cutoffs every 5 years (1925–2010), a 10-year training window and a 10-year reunion window, fixed in advance. The date a user picks in the cohort view only selects which precomputed results to display.

## 2026-10-29 to 10-31: Cleaning tasks 3–6 (Trang)

- Added rules for the original-production flag in step 05: article section, a sole credit for the role, and agreement with a Wikidata director statement.
- Recovered more years in step 04: infobox, then the article's productions section, then the first paragraphs.
- Step 05 drops credits from sentences that mention a film or TV version.
- Hand-resolved recurring names; added `utils/` helpers. `utils/resolve_via_ibdb.py` queries Wikidata only, not the IBDB site.
- Note: this rerun wrote to the project's `data/` folder in Google Drive because `BROADWAY_DATA_DIR` wasn't set.

## 2026-11-02: Years, non-stage filter, step 08, full rerun

- **Data location:**
  - Copied the Oct 29–31 data from the project's `data/` folder to `~/broadway-data`.
  - The Oct 26 data is kept in `~/broadway-data-2026-10-26`.
  - Always run with `export BROADWAY_DATA_DIR=~/broadway-data`.
- **Step 05:** the year is read from the title as a last resort ("Ziegfeld Follies of 1916"), for 23 shows (`year_source = title`).
- **Core set (`src/filters.py`):**
  - Shows with no year are now excluded (`no_year`, 59 shows).
  - Finished the Task 5 non-stage filter. It handles multi-valued Wikidata types and applies only to pages *outside* the main Wikipedia category, because Wikidata mistypes some real musicals (*The Belle of Bohemia* is typed "film").
  - Two pages are dropped by ID in `MANUAL_EXCLUDE`: the *Ziegfeld Follies* series article and *American Dance Machine*.
- **Step 02:** removed the duplicate `fetch_people` call. The death-year block there is still a no-op, because the people query doesn't request P570.
- **New step 08 (`scripts/08_build_network.py`):**
  - Builds the person–show table and fetches death years (Wikidata P570, verified) to drop posthumous credits.
  - Builds edges and reunion labels for 18 cutoffs (1925–2010, W = H = 10 years) in strict and loose modes.
  - New settings in `config.py`: `NETWORK_*` and `POSTHUMOUS_GRACE_YEARS`.
- **Reran 05 → 06 → 08 on the full data:**
  - 1,272 core shows, 10,930 credits, 4,835 people.
  - Director 73% and choreographer 56% of core shows.
  - Strict-mode baseline: 4.2% of pairs reunite within 10 years (1.8–7.2% by cutoff).
  - 181 posthumous credits dropped.
- **Known issue:** `processed/cast_credits.parquet` is still from the 20-show test (Oct 26), so step 06's cast coverage is wrong. Rerun step 04b to fix it.

## 2026-11-02: Second spotcheck (after cleaning)

- Archived the Oct 27 answered sample as `outputs/tables/spotcheck_2026-10-27.csv`.
- Ran `07_spotcheck_sample.py --force` on the current data (seed 42, 50 credits). The answers were checked by an AI assistant (Claude) against the downloaded articles and are tagged `[AI]`; 1 row is left unverified. They still need a human review.
- **Results:**

  | Credits | Errors |
  |---|---|
  | All credits | 9/49 = 18.4% (95% CI 10–31%) |
  | Core shows | 5/44 = 11.4% (5–24%) |
  | Core shows and core network roles | 2/28 = 7.1% (2–23%) |

- **Kinds of error:**
  - 4 rows are films or TV films, all outside the core set.
  - 4 are parsing errors in sentences: "Tony Awards", "Larson's", "Co" from "Dazian & Co.", and Howard Bay recorded as choreographer.
  - 1 is a wrong role in Wikidata (Spialek as musical conductor).
- **Original-production flag:** wrong in 3 rows (Irene/Stein, Cradle Will Rock/Bernstein, Babes in Toyland, whose year is wrong). It's unknown but answerable from the article in 8 more.

## 2026-11-02: Spotcheck on the network scope

- Step 07 has a new `--scope` option, with `network` as the default: core shows and `NETWORK_ROLES`, which is what step 08 uses. `core` samples core shows with all roles; `all` is the old behavior.
- The previous all-credits sample, with its answers, is archived as `outputs/tables/spotcheck_2026-11-02_all.csv`.
- **Result (network scope, 50 credits, seed 42, AI-checked with notes tagged `[AI]`): 1/50 wrong = 2.0% (95% CI 0.4–10.5%).**
  - The one error: Paul Gemignani recorded as director of *Assassins*; he conducted the cast album.
- **Other findings from the sample:**
  - 8 rows have an "unknown" original flag that the article answers.
  - 1 surname-only name ("Robbins").
  - **3 shows shouldn't be in the core set:** *Tosca* and *Ariadne auf Naxos* (operas), and *High School Musical on Stage!* (never on Broadway). They come from Wikidata's IBDB query, where operas count as "dramatico-musical works".
  - 90 core shows are neither in the Wikipedia musicals category nor typed as a musical in Wikidata. They mix operas with real revues such as the Ziegfeld Follies, so this needs a team decision.

## 2026-11-02: Dropped shows that never ran on Broadway

- New `NEVER_ON_BROADWAY` list in `src/filters.py` (reason `never_on_broadway`) with 15 shows checked by hand:
  - **West End or US tour only:** *We Will Rock You*, *Martin Guerre*, *Doctor Dolittle*, *Copacabana*, *On the Record*, *Flashdance*, *The Bodyguard*, *Little House on the Prairie*, *The 101 Dalmatians Musical*, *Happy Days*
  - **Closed out of town:** *Whistle Down the Wind* (1996)
  - **Edinburgh Fringe:** *Love Birds* (2015 Sherman; the 1921 Romberg show stays)
  - **Off-Broadway only:** *Tick, Tick... Boom!*, *And the World Goes 'Round*
  - **Licensed stage version:** *High School Musical on Stage!*
- They got in through Wikidata IBDB IDs, which also cover US tours.
- No automatic rule worked. Infobox productions, Wikidata venue, IBDB ID and article text each either missed real Broadway shows (*Passing Strange*, *The Student Prince*, *The New Moon*) or kept tour-only ones.
- Operas that did play Broadway (*The Consul*, *Regina*, *The Medium*) stay in for now. Whether to keep operas at all is a team decision.
- **Reran 06 and 08:**
  - 1,257 core shows, 10,714 credits, 4,740 people
  - director 72%, choreographer 56%
  - strict baseline 4.2% (1.6–7.2% by cutoff); 25.4% among pairs where both people stay active; 43.1% for pairs with 3+ shows together
  - 167 posthumous credits dropped

## 2026-11-02: Reunion baseline explained

The 4.2% baseline looked low, so we broke it down (strict mode, current core set):

| Pairs | Reunite within 10 years |
|---|---|
| All co-credited pairs | 4.2% |
| Shared 1 show in the training window (95% of pairs) | ~3% |
| Shared 2 shows | 16.6% |
| Shared 3+ shows | 43.1% |
| Composer + lyricist | ~8% |
| Both people work on another show in the next 10 years | 25.4% |

- **Reasons it's low:**
  - Most pairs are incidental, and revues with many writers multiply them.
  - Only ~25% of people do another original show within 10 years.
  - ~72% of people have only one original credit in the data. This is partly real and partly missing credits, so 4.2% is a lower bound.
- H1 compares against the null model, which faces the same gaps, so the low absolute rate doesn't bias the test.

## 2026-11-02: Findings doc and mid-term update

- **`../Pipeline Findings.md` next-steps table:**
  - 6 done (by Trang)
  - 7 skipped (H2 narrowed to the core roles)
  - 8 done (step 08)
  - row 4 extended with the title-year fix and the `no_year` exclusion
- **Mid-term update (`../Midterm Update/`):**
  - Built `Team15.pdf` (one page) from `update.html` and styled it like the proposal: Arial, running header, centered title, bordered tables.
  - Also made `Team15.docx` for editing in Google Docs.
  - The content covers progress, a response to each of the 7 feedback points, the central claim, scope, timeline, an even division of labor and the GitHub link.
  - Ruby and Trang then edited the docx. We reviewed it against the five requirements and only suggested changes:
    - add "Team 15" back
    - get it back to one page
    - fix the Rodgers case-study wording
    - show the GitHub URL
    - update the numbers to the 1,257-show core set
- **Tooling notes:**
  - npm's cache in `~/.npm` has root-owned files. We used a temporary cache instead; fix with `sudo chown -R 501:20 ~/.npm`.
  - LibreOffice isn't installed, so Pages was used to check the Word layout. Pages ignores centered alignment in Word files.

## 2026-11-02: GitHub

- Ruby committed everything ("upload repo to git") and added the remote `https://github.com/rubyngo1610/broadway-network-reunion`.
- `git status` and `git push` failed with "mmap failed: Operation canceled". That's Google Drive cancelling reads of files it hasn't fully downloaded. `git fsck` found nothing wrong with the repository afterwards.
- **Recommendation:** clone the repo to a folder outside Drive (e.g. `~/code/broadway-network`) and work there. Share changes through GitHub, not Drive. Until then, mark the Drive folder "Available offline".
- Also noted: `utils/resolve_via_ibdb.py` queries Wikidata only, but it uses its own User-Agent without a contact email and bypasses the shared cache.

## 2026-11-09: Team decisions on the open items

- **Step 04b (cast):** moved to extensions; not rerun. The cast coverage in step 06 stays wrong until then and isn't used.
- **Operas dropped**, including those that played Broadway.
  - New `OPERAS` list in `src/filters.py` (reason `opera`) with 23 works.
  - They were found among the ~90 core shows that are neither in the Wikipedia musicals category nor typed as a musical in Wikidata. Each was checked by hand: the article uses `{{Infobox opera}}` or its lead calls the work an opera.
  - Examples: *Tosca*, *Ariadne auf Naxos*, *Gianni Schicchi*, Menotti's *The Consul*, *The Medium*, *The Telephone*, *The Saint of Bleecker Street* and *Maria Golovin*, Blitzstein's *Regina*, *Treemonisha*, *Trouble in Tahiti*.
  - **Kept:** operettas, comic operas (Gilbert & Sullivan) and revues, which are part of musical-theatre history. Works in the musicals category (*Porgy and Bess*, *Street Scene*, *Four Saints in Three Acts*) are also kept.
- **Original-production flag:** stays an open item (below).
- **Step 02:** deleted the death-year block, which never ran. Step 08 fetches death years (P570) itself. Step 02 wasn't rerun because its outputs don't change.
- **GitHub:** Ruby confirmed the push went through.
- **Reran 06 and 08:**
  - 1,234 core shows (excluded: 166 subcategory pages, 123 before 1900, 59 no year, 23 operas, 15 never on Broadway, 2 manual)
  - 7,734 core-role credits
  - person–show table: 6,351 rows, 1,145 shows, 3,208 people
  - 163 posthumous credits dropped
  - strict baseline unchanged at 4.2% (411 of 9,736 pairs over the 18 cutoffs)

## 2026-11-09: Step 09, opening theatre for each show (NYC show map)

The show map will show where teams worked within NYC as time passes, so each show needs its opening Broadway theatre and that theatre's coordinates. Before this step the pipeline had no venue data: `wd_broadway_venue` is only a true/false flag, and it's true for 6.5% of shows.

- **New `scripts/09_show_venues.py`:**
  1. Collects wikilinks from opening sentences in the cached articles ("opened at", "premiered at", "previews began at", "played at") and from the infobox premiere, venue and productions fields.
  2. Looks up each link's Wikidata item through the MediaWiki API. Redirects are followed, so old names land on today's article (Alvin → Neil Simon, Martin Beck → Al Hirschfeld, Biltmore → Samuel J. Friedman, Uris → Gershwin).
  3. Keeps only theatre-like items with coordinates inside Manhattan.
  4. Scores each candidate. Points for an "Original Broadway production" section, the show's year in the sentence, and "Broadway" just before the link. Penalties for revival, tour, London or Off-Broadway nearby; for "transferred to" or "moved to" (the second theatre of a run); and for headings or sentences that name only years well after the opening.
  5. Drops theatres that hadn't opened yet, or were already demolished, in the show's year. Wikidata P1619 and P576 supply the dates; 45 candidates were dropped this way, mostly revival theatres.
  6. Requires a minimum score, so a missing venue is preferred to a wrong one.
  7. Never chooses a theatre on the hand-checked `NON_BROADWAY_QIDS` list: Off-Broadway houses (Playwrights Horizons, NYTW, York, Lortel, 47th Street), the Apollo, nightclubs and Radio City.
  8. Applies `VENUE_OVERRIDES`, which fixes 6 shows by hand (*Porgy and Bess*, *Anything Goes* and *Wildcat* at the Alvin; *The Last Ship*; *Bring in 'da Noise*; *Love o' Mike*).
- New Wikidata IDs, verified at run time in `src/wikidata.py`: P1619 date of official opening, P576 demolished, Q24354 theatre building.
- **Outputs:**
  - `data/processed/venues/show_venues.parquet`: one row per core show, with venue QID and name, lat/lon, how the venue was found, the evidence sentence and its score
  - `data/processed/venues/theatres.parquet`: 86 theatres, with coordinates, opening and demolition years, and number of shows
  - `outputs/tables/show_venues_review.csv` and `venue_coverage.csv`
- **Result:** 988 of 1,234 core shows (80%) have an opening theatre with coordinates. For the 1,125 shows in the strict network the figure is 942 (84%).

  | Decade | 1900s | 1910s | 1920s | 1930s–50s | 1960s–2010s | 2020s |
  |---|---|---|---|---|---|---|
  | With a venue | 55% | 63% | 70% | 86–93% | 80–93% | 82% |

  - No venue: 196 shows (no qualifying sentence) and 49 with no article.
- **Accuracy (checked by an AI assistant, Claude, from the evidence sentences and its own knowledge of Broadway history; not yet checked against IBDB or reviewed by us):**
  - The last two random samples of 30 had 29/30 correct each.
  - 25 well-known shows were all correct: *Show Boat* at the Ziegfeld, *Oklahoma!* and *The King and I* at the St. James, *South Pacific* at the Majestic, *Guys and Dolls* at the 46th Street (Richard Rodgers), and others.
  - Remaining error types: an Off-Broadway house missing from the exclusion list, and a theatre from later in the run when the article doesn't link the first one.
- **Limits:** only the opening theatre is recorded, not later transfers. A show's `year` is sometimes the world premiere, not the Broadway opening (*Memphis* 2003, *Les Misérables* 1980). The map's legend must say "shows with a known opening theatre" and note the thinner coverage before 1930.

## 2026-11-10: Theatre coordinates checked and venue fixes

- **Every theatre has a location.** All 86 theatres in `venues/theatres.parquet` have latitude/longitude from Wikidata (P625). No street addresses are stored; Wikidata's street address (P6375) could be added to step 09 for map tooltips. The columns are documented in the README data dictionary.
- **All points are in Midtown Manhattan,** between about 28th and 65th Street (lat 40.746–40.774, lon −73.999 to −73.979).
  - 66 theatres are in the Theater District core (40th–54th Street, Sixth to Eighth Avenue).
  - The other 20 are real locations, and they show Broadway's move north:
    - early houses around Herald Square and lower Broadway: Daly's, Weber and Fields', the 1878 Bijou, Garrick, Herald Square, Knickerbocker, Casino, Princess, Maxine Elliott's, the Grand Opera House on 23rd Street
    - Columbus Circle and Lincoln Center: Century, New Century, International, Circle, Colonial, Vivian Beaumont
    - the Ziegfeld on Sixth Avenue
- **Precision is good enough for a street-level map.**
  - Most coordinates are given to the arcsecond, about 30 m. Values such as 40.76 or 40.7625 look rounded but are exact arcsecond values (40°45′36″, 40°45′45″).
  - Only the Center Theatre (−73.98) and possibly the Central and Victoria are rounded to about 100 m.
- **Fixes in step 09** (checked against each item's Wikidata description and street address):
  - **Bijou (1917–1982) had the wrong coordinates in Wikidata.**
    - There are two separate Bijou items: Q45103687 for the 1878–1915 theatre at 1239 Broadway, and Q4907254 for the 1917–1982 theatre at 209 W. 45th Street.
    - Q4907254 carried the 1878 theatre's point, about 1.3 km too far south.
    - New `VENUE_COORD_OVERRIDES` sets Q4907254 to 40.7584, −73.9862, on 45th Street just east of the Morosco (the Marquis is on the site today). This affects *A Kurt Weill Cabaret* (1979).
    - The Wikidata item itself isn't corrected; that would be a public edit.
  - **The Westside Theatre (Q7989720, Off-Broadway)** was added to `NON_BROADWAY_QIDS`. It had been chosen for 2 shows:
    - *Pump Boys and Dinettes* (1982) is now at the Princess Theatre, the Latin Quarter building, by override.
    - *Lady Day at Emerson's Bar and Grill*: its article year (1986) is the Off-Broadway run, and it reached Broadway only in 2014. **Team decision: keep it in the core set as a 2014 Broadway show.**
      - New `BROADWAY_YEAR_OVERRIDES` in `src/filters.py`, applied in step 05: year 2014, `year_source = manual`.
      - New `ORIGINAL_TEAM_OVERRIDES`, applied in step 05 with `original_basis = manual_team`: Lonny Price is the only original director. The 1986 directors (André Ernotte, Woodie King Jr., Reenie Upchurch, Lonette McKee) are now not original, so they drop out of the strict network. The designers (ESosa, Wierzel, Noone) were already the 2014 team, and the playwright (Lanie Robertson) stays original.
      - Venue override: Circle in the Square Theatre (Q2973328).
  - **The Latin Quarter (Q11983435) is no longer excluded.** At 200 W. 48th Street it was a Broadway house from 1979 to 1989, under the names 22 Steps, Princess Theatre and Latin Quarter.
    - *Mayor* (1985) and *My Old Friends* (1979) now get it automatically.
    - *The Madwoman of Central Park West* (1979) gets it by override, because its article says "transferred to … 22 Steps".
  - **No fix needed:** the 1903 Lyric (Q6710003) and the Apollo share one point, and the Times Square Theater is 4 m away. They stood side by side on W. 42nd Street, so the error is only 10–20 m.
- **Reran 05 → 06 → 08 → 09:**
  - 1,234 core shows (unchanged), 6,351 person–show rows, 164 posthumous credits dropped (Ernotte, who died in 1999, is now dated 2014)
  - strict baseline 4.2% (411 of 9,730 pairs)
  - 991 of 1,234 core shows (80%) have a venue, with 10 hand venue overrides in total
- **For the map:**
  - **Crowding:** 41 of 86 theatres have a neighbour within 40 m, because they're adjacent houses on the same block, e.g. Golden and Jacobs (21 m), Shubert and 44th Street (22 m). The 42nd Street trio is 14 shows on one point. Use small offsets, clustering, or one marker per block with a list.
  - **Historical names:** `venue_name` is today's name (the Alvin appears as Neil Simon). A historical map needs a small name-by-year table (for example Alvin 1927–1983, then Neil Simon).

## 2026-11-10: Web views set up (Ruby, views track)

- **Plan correction (from the proposal's "Linked views"):**
  - The NYC map is the **base layer** of the cohort view and the trajectory view, not a separate view. One map component serves three views.
  - The cohort view colours dots **by the show a person worked on at the start date**, not by community, so it doesn't depend on BigCLAM. It depends on the **null model** (step 10): only reunions above the randomized baseline glow. BigCLAM adds an optional "colour by community" mode and the deferred embedding view.
  - **Data gap:** shows have an opening year but **no closing date**, so "musicals running at a date" can't be computed yet. Stand-in: a show is active in its opening year. Closing dates could be read from the articles ("closed on … after N performances"), much like step 09.
- **Stack:** D3 v7 (pinned at `d3@7.9.0`, from jsDelivr) on a static page, with no build step. It's served locally with `python3 -m http.server` and published on GitHub Pages.
- **New `scripts/13_export_viz_data.py`** writes `viz/data/*.json` (2.6 MB in total) from steps 05, 08 and 09:
  - `meta.json` and `theatres.json` (86)
  - `shows.json` (1,234)
  - `people.json` (3,208; 1,531 with birthplace coordinates)
  - `credits.json` (6,351)
  - `reunions.json` (strict 9,730 and loose 17,059 pair rows)

  The views never read parquet. Rerun it after any rerun of 05, 08 or 09. Step numbers 10–12 stay reserved for the methods track.
- **New `viz/` folder** (structure and data contract in `viz/README.md`):
  - page shell and view navigation by URL hash
  - design tokens as CSS custom properties, with light and dark modes
  - `data.js`: one loader with lookup maps and helpers (`career`, `theatreOf`, `standing`)
  - `grid.js`: converts lat/lon to Manhattan grid units, so north is up and avenues are straight. This is the base of the stylized Theater District map. Checked on known theatres: within half a block in streets and about a quarter avenue in avenues.
  - a shared tooltip
  - placeholder pages for the five planned views
- **Data check view (`#data`):** counts and coverage notes, plus every theatre on the grid with a year slider (filled = standing). Checked by screenshot at desktop, phone and dark-mode widths. The Bijou fix shows: the 1917 Bijou now sits on 45th Street.
  - **Limit:** a theatre with no Wikidata opening date counts as standing from the year of its first show in our data. That's an upper bound; for example, the Adelphi opened in 1928, but our first show there is from 1939.
- **GitHub Pages:** `.github/workflows/pages.yml` publishes `viz/` on pushes to `main`. One-time step on GitHub: Settings → Pages → Source: **GitHub Actions**. Free Pages needs a public repository.

## 2026-11-10: Trang's name fixes restored; permanent fix file

- **Problem:** Trang's hand fixes from Oct 30 weren't in any file. The `unresolved_names.csv` committed on Nov 2 already had zero manual entries.
  - Step 05 rewrites that file on every run and keeps only names that are still unresolved. A name fixed by hand drops out of the file, so on the run after that the fix itself is lost.
- **Found:** her decisions survive in the Oct 31 run, which wrote to the project's own `data/interim/credit_mentions.parquet` in Drive. There are 51 decisions:
  - 10 linked to the right Wikidata entry (Pasek, Paul, Stroman ×2, Bennett, Spielberg, Anthony, Abbott, …)
  - 12 surname-only names completed (Alford → Larry Alford, Aborn → Milton Aborn, …)
  - 29 junk "names" removed ("Choreography", "Broadway's", "Disney", "Tony", "Boston", …)
- **Fix:** a new permanent file, `outputs/tables/manual_name_resolutions.csv` (show_id, person_name, resolved_qid_manual, resolved_name_manual, note). Step 05 reads it but never writes it, and its entries win over `unresolved_names.csv`.
  - All 51 of Trang's decisions are restored there. One correction: for "Anderson" a QID was typed into the name column, so it's recorded as QID Q7167225.
  - **Hammerstein fix:** *Wildflower* (1923) credited a name-only "Oscar Hammerstein II", which split him into two people and would have broken the Rodgers & Hammerstein case study. It now points to Q319693, so he has 26 credits.
- **Trang, please confirm:** a few of the removed names are real surnames ("Ashford", "Barry", "Sweeney", "Botelho", "Ariel"). Were those mentions fragments, not people?
- **Reran 05 → 06 → 08 → 09 → 13:**
  - 64 hand-resolved mentions applied
  - 6,335 person–show rows; 3,189 people in the network
  - strict baseline 4.3% (416 of 9,681 pairs)
  - venues unchanged at 991 of 1,234
- **Union Square:** almost absent from the data, because the core set starts in 1900 and the district had moved uptown by then. Only *The Errand Boy* (1904, Fourteenth Street Theatre) links a 14th Street house, and step 09 didn't select it.
  - Wallack's (Broadway and 30th) is named in 3 articles but not chosen. *The Sultan of Sulu* (1902) opened there but is placed at the Grand Opera House. **To check in step 09.**

## 2026-11-10: Zoomable Manhattan map, visual style, show map; community plan

- **Team decision (Ruby): BigCLAM communities get their own layer**, without changing the encodings of the trajectory or show map. There is only one colour meaning at a time:
  - **Cohort view: "Colour by: Show | Community" toggle.** Same dots, positions and animation; only the colour changes.
    - Community colours come from BigCLAM trained on [T−10, T).
    - People in two or more communities get a second colour as a ring.
    - Reunion links are solid if the pair shared a community before reuniting, dashed if not. This is H3 made visible.
    - Show colours stay the default, so the study tasks don't change.
  - **Community timeline panel** beside the cohort map: one band per tracked community (step 12) across the 5-year steps, showing continue, split and merge, with reunions marked on the bands.
    - Linked to the map: hovering a band highlights its members, and picking a year moves the map.
    - Includes a small within- vs across-community reunion bar against the null model. This takes over the deferred embedding view's question.
  - **Trajectory:** an optional thin grey strip under the career line shows the person's community memberships per window. No extra colours.
  - **Small multiples:** the same toggle, so the comparison with the animated view stays fair.
  - **Limits:** at most ~6 community colours per window, with the rest grey ("Other"). The panel needs step 11/12 outputs; until then it runs on stand-in communities in the agreed format.
- **Visual style (Ruby's choice: a blend of the three directions):**
  - Playbill / marquee for the page: cream paper, Playfair Display headings, Source Sans 3 text, a gold accent.
  - Vintage atlas for the map.
  - Transit-diagram lines for careers.
  - Tokens in `viz/css/style.css`, with a dark "marquee at night" mode.
- **Zoomable map (Ruby's choice: a D3 vector basemap, not historical tiles or the schematic grid):**
  - **New `scripts/14_build_basemap.py`** writes `viz/data/basemap.json` (530 KB), covering the Battery to about 100th St:
    - Manhattan shoreline and neighbouring boroughs, from NYC Open Data Borough Boundaries (gthc-hcne)
    - 249 named parks and about 6,700 street lines, from OpenStreetMap via Overpass
    - hand-placed labels for the squares and rivers

    Sources are cached in `data/raw/basemap/`. Lines are simplified with Ramer-Douglas-Peucker; park outlines stored in pieces are joined into closed shapes, and 40 that came back without geometry are fetched again by id. Attribution: OpenStreetMap (ODbL) and NYC DCP.
  - **New `viz/js/manhattanMap.js`**, shared by the show map, trajectory and cohort views:
    - rotated 29° to grid north, so avenues are vertical
    - zoom from 1× to 16× with drag, scroll or buttons
    - basemap strokes keep their width; views re-place their points on zoom, so dots keep their size and spread apart when zoomed in
    - default view from Union Square to Lincoln Center
  - **Show map (`#showmap`, now the start page):**
    - a year slider and a Play button
    - theatres with an opening that year are filled red, standing theatres are rings, and others are faint
    - the year's openings are listed with their theatre, or "theatre unknown"
    - theatre names appear when zoomed in

    Checked by screenshot: 1927 shows *Show Boat* and *Rio Rita* at the Ziegfeld, and Broadway's diagonal through the squares.
- **Next:** the trajectory view on the shared map (Rodgers as the test case), then the birthplace map, then the cohort view and small multiples on stand-in data.

## 2026-11-12: Step 11 (BigCLAM) started on credits.json; two-window check (Trang)

- **Setup on Trang's machine:**
  - The repo is a clone outside Google Drive.
  - The venv is at `~/venvs/broadway` and uses Homebrew Python 3.11 (the system Python is 3.9, too old for `src/`).
  - `BROADWAY_DATA_DIR=~/broadway-data`.
  - **No pipeline data yet:** `data/` is gitignored, so the parquet files exist only on Ruby's machine. Asked Ruby for her `~/broadway-data` folder.
- **Using `viz/data/credits.json` instead.** It holds the same 6,335 rows and `strict`/`loose` flags as step 08's `person_show.parquet` (Nov 10 run). Rebuilding the window graphs from it reproduces `outputs/tables/network_windows.csv` exactly: the edge and reunited-pair counts match for all 36 (mode, cutoff) windows.
- **New `scripts/11_bigclam.py`:**
  - BigCLAM in NumPy (dense matrices, since each window has ≤ ~400 people).
  - Fitted by projected gradient ascent with backtracking. The gradient was checked numerically.
  - Seeds are locally minimal ego networks.
  - K is chosen per window by held-out likelihood (20% of edges plus as many non-edges hidden, 3 folds; K from 2 to 130, capped at n/2).
  - Members have `F ≥ δ`, where δ = √(−log(1−density)).
  - Communities with identical members are merged by summing their F columns.
  - `--source auto|parquet|json` reads `person_show.parquet` when it exists, otherwise `credits.json`.
  - Edges are binary: the number of shared shows is not used.
  - **Outputs:**
    - `processed/communities/communities.parquet`, in the agreed format: mode, cutoff, community_id, person_id, strength
    - `affiliations.parquet` (full F, for H3)
    - `outputs/tables/bigclam_windows.csv`, `bigclam_k_selection.csv`, `bigclam_case_studies.csv`
- **Two-window check (strict, 1950 and 1980): BigCLAM mostly recovers single show teams.**

  | | 1950 | 1980 |
  |---|---|---|
  | people / edges / shows in window | 177 / 463 / 73 | 297 / 908 / 100 |
  | K chosen | 80 (the largest tried) | 130 (the largest tried) |
  | distinct communities after merging duplicates | 64 | 96 |
  | communities that fit inside one show's team | 92% | 98% |
  | people in 2+ communities | 26% | 21% |

  - Held-out likelihood rises almost steadily with K up to about one community per show. The optimiser converges (checked to 3,000 iterations), so this comes from the data: the co-credit graph is a union of cliques, one per show, and few people link them (only 21–28% of people have 2+ shows in a window).
  - **Case studies:** Rodgers falls in 5 communities in 1950. Each is one show's team (the *Oklahoma!* team, the *Pal Joey* team, …), not a "Rodgers & Hart" or "Rodgers & Hammerstein" group. Lerner & Loewe are the same. The one community that spans many shows (1980, 20 people, 9 shows) is a revue roster with many writers (Comden & Green, Sondheim, Kander & Ebb, …).
  - So, as written, the communities add little beyond "shared a show", which is the risk noted in the Nov 9 plan.
- **Junk names seen in communities**, to add to `manual_name_resolutions.csv`: "revue", "Gentlemen Prefer Blondes", "Sherrin", "Kidd".
- **Not yet run:** the full 36 windows (the outputs currently hold only strict 1950 and 1980). Decide on the open question below first.
- **Open question for the team:** how to get communities that reach beyond one show. Options:
  1. Fit on a graph of repeat collaborations (pairs with 2+ shared shows)
  2. Fit on the person–show bipartite graph, so communities group shows that share people
  3. Fix K below the number of shows (for example by AIC/BIC) instead of choosing it by held-out likelihood
  4. Accept show-level communities and use the overlap structure

## 2026-11-12: Step 11, K chosen by BIC (Trang)

- **Decision: option 3**, compared against the proposal and the Nov 3 update.
  - Every pair H3 scores already shared a show, so communities have to separate pairs within that group.
  - Show-level communities (option 4) can't add anything beyond the shared-shows baseline.
  - Option 1 builds the graph from the baseline feature itself and drops most people.
  - Option 2 changes the method the proposal and update describe.
- **Change to `scripts/11_bigclam.py`:** `--k-method bic` is now the default. For each K, the best of 5 seeded fits (`--restarts`) is kept, and K minimises BIC = −2 LL + p·log(number of pairs).
  - p counts the non-zero entries of F, because entries held at the F ≥ 0 boundary aren't free parameters.
  - Counting all n×K entries instead picks K = 2 in both windows, splitting the whole window into two halves of 40–90 people that span 25–30 shows each.
  - `--k-method heldout` is kept for comparison.
  - **This rule is fixed before any H3 result.**
- **Two-window check (strict):**

  | | 1950 held-out | 1950 BIC | 1980 held-out | 1980 BIC |
  |---|---|---|---|---|
  | K chosen | 80 | 50 | 130 | 65 |
  | distinct communities | 64 | 49 | 96 | 64 |
  | communities that fit inside one show's team | 92% | 80% | 98% | 72% |

  - **Better, not solved:** most communities are still one show's team.
  - **The BIC curve is noisy between neighbouring K values** (1980: 14,359 at K = 13, 6,804 at K = 16), because fits land in different local optima. Its minimum lies in a broad band (1950: K ≈ 30–65; 1980: K ≈ 30–80). An earlier exploratory run with different seeds picked K = 40 and 30.
  - **Case studies (1950):**
    - Rodgers's communities now separate the Hart circle (Hart, Alton, Logan, Abbott, O'Hara) from the Hammerstein circle (Hammerstein, de Mille, Mamoulian, Logan).
    - Lerner & Loewe share two communities that span 3 shows each.
    - Comden & Green share one community with Bernstein, Abbott and Robbins (4 shows).
  - **Case studies (1980):** Lerner's communities are single shows. The Comden & Green communities are revues and large multi-writer shows.
- **Reading:** the data has little multi-show structure. About 72% of people have one original credit, and only 21–28% have two or more shows in a window. Communities can only reach beyond a show through those repeat people, so mostly show-level communities partly reflect the data, not just the model.
- **Next:**
  1. Run all 36 windows.
  2. Raise `--restarts` if BIC stays this noisy.
  3. Let H3 decide whether F_u·F_v adds to the shared-shows count.
  4. Report the single-show share per window as a limitation.

## 2026-11-12: Step 11 full run, all 36 windows (Trang)

- Ran `python scripts/11_bigclam.py` with the defaults (BIC, 5 restarts) on `viz/data/credits.json`. It took about 2 minutes. No window chose the largest K on the grid.
- **Outputs:**
  - `~/broadway-data/processed/communities/communities.parquet` and `affiliations.parquet`
  - `outputs/tables/bigclam_windows.csv`, `bigclam_k_selection.csv`, `bigclam_case_studies.csv`
- **Results:**

  | | strict | loose |
  |---|---|---|
  | K chosen | 30–65 | 40–100 |
  | communities that fit inside one show's team | 53–84% | 58–94% |
  | people in 2+ communities | 6–23% | 9–29% |

- **The trend over time:**
  - Communities are most multi-show before WWII. In strict mode, 1925–1940 has 53–68% single-show communities, and the median community spans 2 shows.
  - They become more show-level after 1990: 77–84% single-show, and only 6–9% of people in 2+ communities.
  - This fits fewer repeat collaborators in later decades. Check it against step 08's per-window counts before stating it as a finding.
- **Checked against step 08 (same data, `credits.json`): repeat collaboration really does fall over time.**

  | strict, training window ending | 1925–1935 | 1950–1970 | 1990–2010 |
  |---|---|---|---|
  | people with 2+ shows in the window | 33–36% | 26–31% | 13–17% |
  | co-worker pairs who shared 2+ shows | 7–12% | 4–5% | 1–2% |
  | single-show BigCLAM communities | 52–68% | 72–80% | 77–84% |

  - Loose mode shows the same pattern.
  - Across the 18 windows, the share of single-show communities tracks the share of repeat pairs (correlation −0.70 strict, −0.84 loose). So the communities reflect a real feature of the data, not a fitting artefact.
  - **Not explained by role mix.** Early shows mostly list writers (staging roles are 21% of credits in the 1925 window, about 30% later), and writing teams repeat more. But the decline also appears within writers alone (2+ shows: 37% → 13%) and within directors and choreographers alone (30–38% → 9–13%).
  - **Not explained by the number of shows:** each window holds 64–111 shows throughout. Average team size is also stable, about 3–4 people in strict mode.
  - **Caveats before calling it a finding:**
    - The scope is original Broadway productions only. Since the 1980s, repeat work may happen in revivals, Off-Broadway, London or regional development, none of which is in the data.
    - Credits are thinner before 1930 (about 2–3 people per show, and 18–30% of shows with no confirmed original credit).
    - The reunion rate (step 08) doesn't fall steadily: it dips in the 1980s–1990s windows (1.7–2.6%) and recovers to 4–6% in 2000–2010.
- **Next (written before H3 was run):** step 12 (community tracking) and the H3 prediction test can read `communities.parquet` / `affiliations.parquet` now. When Ruby's data arrives, rerun with `--source parquet` to confirm the results are identical.

## 2026-11-12: H3 prediction test, step 15 (Trang)

- **New `scripts/15_h3_prediction.py`** (number 15 because 13 and 14 are taken).
  - Uses the same time splits as step 08. Candidates are the pairs who shared a show in [T−10, T); the label is whether they share a show again in [T, T+10).
  - Every score uses only the training window. The pair and reunion counts match `network_windows.csv` in all 36 windows.
  - **Scores:**
    - shows together (the heuristic H3 has to beat)
    - BigCLAM F_a·F_b (step 11)
    - shared communities
    - common neighbours and Adamic–Adar
    - activity: min(shows of a, shows of b) in the window
  - **Fixed before looking at results:**
    - primary test: strict mode, AUC pooled over the 18 cutoffs, BigCLAM vs shows together
    - secondary test: the same among pairs who shared exactly one show
    - 95% intervals by bootstrap over pairs within each cutoff. These are somewhat too narrow, because pairs share people and windows overlap.
  - Also new: `src/network.py`, the person-show loader and window graphs shared by steps 11 and 15. Step 11 now imports it; its outputs are unchanged.
- **Result: H3 is not supported.**

  | strict mode, AUC (0.5 = chance) | all 9,681 pairs (416 reunite) | 9,214 one-show pairs (302 reunite) |
  |---|---|---|
  | shows together | **0.620** | 0.500 (can't rank) |
  | BigCLAM F_a·F_b | 0.492 (CI 0.458–0.524) | **0.402** (CI 0.371–0.437) |
  | shared communities | 0.537 | 0.481 |
  | common neighbours | 0.450 | 0.348 |
  | activity (both still working) | **0.679** | **0.602** |

  - BigCLAM minus shows together: −0.128 (CI −0.155 to −0.096).
  - BigCLAM beats shows together in 0 of 18 strict windows and 5 of 18 loose windows. Loose mode is similar overall: BigCLAM 0.525 vs shows together 0.610.
- **Why BigCLAM is below chance on one-show pairs: team size.**
  - Pairs from small teams reunite far more often: 5.9% for teams of 2–3, 4.5% for 4–5, 1.5% for 6–8, 0.7% for 9+.
  - Larger teams also give a higher BigCLAM score (rank correlation 0.48) and more common neighbours (0.99).
  - Within each team-size band, BigCLAM is near chance (AUC 0.46–0.55). Activity stays informative in every band (0.56–0.68).
- **Reading:** in this data, who reunites is predicted by:
  1. having worked together more than once
  2. both people still working on Broadway
  3. having been on a small team

  Membership in a wider learned community adds nothing. This fits the step 11 finding that most communities are single show teams. It also fits H1's expectation that composer–lyricist pairs, the smallest teams, reunite most.
- **Why H3 failed:**
  - **In the data (the finding):**
    1. **Little group structure.** About 72% of people have one original credit, so few people link show teams, and most communities are a single show's team.
    2. **Every tested pair already shared a show.** A community that is basically a show team can't separate them.
    3. **Team size points the wrong way.** Big teams (revues, many writers) form dense communities and score high, but rarely reunite.
    4. **Reunions are pair-level.** They come from repeat partners who both stay active, in small teams. Communities blur those pairs into bigger groups.
  - **In the method and data (limitations):**
    5. **Edges are unweighted.** BigCLAM ignores how many shows a pair shared (the strongest predictor) and their roles.
    6. **K selection is unstable.** BIC is noisy between neighbouring K.
    7. **BigCLAM suits large social networks,** not a network that is mostly small, separate show teams.
    8. **Original Broadway only.** Recurring circles may sit in Off-Broadway, revivals, London or regional work.
    9. **Data gaps.** Missing credits (especially before 1930) and junk or split names remove links.
- **Caveats:**
  - BigCLAM uses unweighted edges.
  - K is chosen by BIC, and the curve is noisy.
  - The data covers original Broadway productions only.
  - Other community methods (Leiden, weighted BigCLAM) could do better. Any variant tried now is exploratory, because the primary test was fixed before results and has been run.

## 2026-11-12: H1 null model, step 10 (Trang)

- **New `scripts/10_null_model.py`**, following the null model in the Nov 3 update (feedback 5).
  - For each mode and cutoff, people are reassigned at random across the role slots of shows, separately in the training window [T−10, T) and the reunion window [T, T+10).
  - A slot is one person-show credit, and people only swap with others who held the same role set on their show (e.g. "composer|lyricist").
  - This keeps each person's credits per window and their roles, every show's team size and date. A person placed twice on one show is swapped away.
  - Checked on 21,600 shuffles across all windows: none changed a person's role credits or put anyone twice on a show.
  - The observed counts match `network_windows.csv` in all 36 windows.
  - It runs in about 16 s (1,000 shuffles per window) on `credits.json`.
  - `src/network.py` now also loads each credit's roles.
- **Fixed before results:**
  - primary test: strict mode, reunion rate pooled over the 18 cutoffs, against 1,000 shuffles, one-sided
  - secondary tests: by pair type (from the roles on the shared show), loose mode, each cutoff on its own
- **Result: H1 is supported.**

  | strict | pairs | observed | null mean (95%) | ratio |
  |---|---|---|---|---|
  | all pairs | 9,681 | **4.3%** | 1.2% (1.0–1.4%) | 3.6× |
  | composer–lyricist | 1,483 | **9.2%** | 2.4% (1.7–3.1%) | 3.9× |
  | other writer–writer | 3,802 | 4.6% | 1.1% | 4.2× |
  | writer–staging | 3,811 | 2.4% | 0.9% | 2.7× |
  | staging–staging | 585 | 2.6% | 0.6% | 4.6× |

  - p = 0.001 for every row, the smallest value 1,000 shuffles can give. The one exception is loose-mode staging–staging pairs: 0.8% vs 0.6%, p = 0.035.
  - The observed rate is above the null's 95% interval in all 18 cutoffs, in both modes.
  - Loose mode overall: 3.2% vs 1.0% (3.1×).
- **"Strongest for composer–lyricist pairs":** true for the reunion rate (9.2%, twice any other type) and for the excess over chance (+6.9 points, against +3.5 for other writer pairs). It's not true for the ratio: other writer pairs (4.2×) and staging pairs (4.6×, only 585 pairs) are similar or higher. Say which measure the claim uses.
- **For the views:** `processed/h1/show_reunions.parquet` gives, per training-window show, its reunited pairs against the null. In strict mode, 412 of 1,582 (show, cutoff) entries have any reunion, and 210 are above chance (p < 0.05). The cohort view can use this for "only reunions above the randomized baseline glow". Many small p-values are expected by chance across 1,582 tests, so treat this as a highlight, not a test.
- **Where the project stands:**
  - H1 (reunions beat chance): supported.
  - H3 (communities predict who reunites): not supported. Reunions are predicted by repeat work, both people staying active, and small teams.

## 2026-11-12: H1 flags exported for the cohort view (Trang)

- Step 10 now also writes **`viz/data/h1.json`** (32 KB). It contains:
  - per mode, the training-window shows whose team had a reunion, with their p-value against the null
  - the observed vs null reunion rate per cutoff, for the reunions-over-time chart in the proposal
- **`viz/js/data.js`:**
  - loads `h1.json` if it exists (`db.h1`; the page works without it)
  - adds `db.aboveChance(mode, cutoff, show)` and `db.glows(mode, reunionRow)`
- Checked: the JavaScript parses, and a Python version of the glow rule gives the counts below.
- **Glow counts:** 342 of 416 strict reunions glow (415 of 542 loose).
  - Reunions are rare by chance, so one reunited pair from a small team already beats the null. The filter mostly drops reunions from large teams.
  - **For Ruby to decide:** whether the cohort view glows on that, or on a stricter rule (e.g. p < 0.01, or teams with 2+ reunited pairs).

## 2026-11-12: Sanity check on well-known duos (Trang)

- Checked whether step 11's communities recover 20 well-known partnerships, across all strict windows where both people shared a show (105 duo-windows). The duos:
  - Rodgers & Hart, Rodgers & Hammerstein, Kern & Hammerstein
  - Lerner & Loewe, Comden & Green, Kander & Ebb, Bock & Harnick, Schwartz & Dietz, Strouse & Adams, Adler & Ross
  - Lloyd Webber & Rice, Boublil & Schönberg, Flaherty & Ahrens, the Gershwins, Coleman & Fields, Schmidt & Jones
  - Shaiman & Wittman, Lane & Harburg, Arlen & Harburg, Styne & Cahn
- **Duos share a community in 102 of 105 windows.**
  - The one clear miss is Kern & Hammerstein: separate communities in 3 of 4 windows.
  - In 1950, Rodgers's communities separate the Hart circle from the Hammerstein circle.
- **But this alone isn't evidence:** 98% of all co-worker pairs share a community.
- **A fairer test** is whether the shared community spans 2+ shows (a recurring circle, not one show's team):
  - famous duos: 82% (84 of 102)
  - ordinary pairs: 57%
  - ordinary pairs who shared 2+ shows: 99%
- **Reading:** BigCLAM does recover the famous partnerships as multi-show circles. But it does so because they shared several shows, which the shows-together count already shows. It adds no information beyond that, which is the H3 result again.
- **For the report:** the sanity check passes, so communities are a valid *descriptive* layer (the case studies look right), while H3 shows they're not *predictive* beyond repeat work.
## 2026-11-12: One map for every view (Ruby, views track)

- **Change:** the views are now modes of one page instead of separate pages. The Manhattan map is built once and stays on screen, and a mode bar above it switches between Shows, Career, Cohort, Birthplaces and Compare. Switching animates the theatre dots and swaps the side panel. The zoom and the year on the shared timeline carry over between modes.
- **Why:** jumping to a new page lost the context (zoom, year), and the views are about the same places and the same people.
- **How it works:** `viz/js/stage.js` holds the map, the timeline and the panel. Each view is a mode in `viz/js/modes/` with `enter`, `setYear` and `exit`. Links still work (`#cohort?year=1943`, and old ones such as `#showmap`), and the data check moved to a link in the footer.
- **Still to decide:** Birthplaces needs a US/world basemap; the plan is for the map to zoom out from Manhattan when that mode is entered. Compare (small multiples) will split the map into a grid of small copies.

## 2026-11-13: Career mode (trajectory view)

- **What:** the Career mode draws one person's strict-network credits as a transit line from theatre to theatre, in opening order, and zooms the map to fit. Stations grow with the number of shows at a theatre. The panel lists every show with role and theatre; hovering a row lights up its station. Collaborator names open that person's career on the same map.
- **Reunion in this view:** a show counts as a reunion when the person works again with a collaborator after **5 or more years apart** (the step between cutoffs). Collaborators from the last 5 years are shown as "still with" instead. Counting every repeat collaborator made almost every show gold (29 of Rodgers' 35, nearly all Hart).
- **Rodgers check:** 35 shows, 16 theatres, 5 reunions: Hart in 1925 (after *Poor Little Ritz Girl*, 1920), Joshua Logan on *South Pacific* (9 years after *Higher and Higher*), Sondheim in 1977 (12 years after *Do I Hear a Waltz?*), Martin Charnin in 1979 (9 years after *Two by Two*). All match the history.
- **Timeline in Career:** the year slider now works here too, limited to the person's career (1920–1979 for Rodgers). The line is drawn up to the chosen year with the rest dashed, theatres not reached yet are faded, the latest show's theatre is filled and labelled, and the list scrolls to it. Entering the mode shows the whole career unless the link names a year. Checked: 1935 = *Jumbo* at the Hippodrome, 1943 = *Oklahoma!* at the St. James, 1947 = *Allegro* at the Majestic.
- **Known limits:** most theatres sit within a few blocks of Times Square, so the line knots there until you zoom in (theatre names appear from zoom 4). 4 of Rodgers' 35 shows have no known theatre and are listed but not mapped.

## 2026-11-13: Compare careers (Career mode, up to 4 people)

- **What:** Career mode now shows up to four people at once on the shared map, each a transit line in their own colour and dash pattern. Lines share streets side by side (a small offset per person). The panel has a card per person (dates, birthplace, shows, theatres, reunions), a search box to add someone, a "shows together" summary for the selected people, and one list of shows in order with the people on each. Collaborator names add that person (when full, they replace the last one); × removes a person, and the others keep their colours.
- **Timeline:** back to the full range of the data (1900–2027), as Ruby asked, so careers line up on one calendar. Entering the mode, or adding someone while whole careers are shown, sets the year to the latest career end.
- **Colours:** validated with the dataviz palette script against the map land colour, all pairs, light and dark. Light: #9b2335 red, #2a78d6 blue, #0b7f63 teal, #b8459f magenta. Dark: #e8584a, #3987e5, #14907a, #c158b8. A fifth hue could not be separated from these even for normal vision, hence the cap of 4. The closest pair (red/teal, colour-blind ΔE 7.9) is in the band where a second cue is required: each person also has a dash pattern and is named in labels and the list. Gold stays reserved for reunions, now a halo around the station so the person's colour still shows.
- **Checked:** Rodgers and Hart 20 shows together, Rodgers and Hammerstein 9 (Oklahoma! to The Sound of Music), Rodgers and Sondheim 2. In 1943 Rodgers and Hammerstein are both at the St. James (Oklahoma!), shown as one label.

## 2026-11-13: Career comparisons limited to related people

- **Change (Ruby's request):** Career mode starts blank instead of on Rodgers. The first person chosen is the anchor; the "Compare with" dropdown lists only people who worked with the anchor on **2+ shows**, most shows first, tagged "reunion" when there was also a 5+ year reunion. Every person card has ×. Removing the anchor makes the next person the anchor and drops anyone unrelated to them; removing everyone returns to the blank state. Old links that mix unrelated people drop the unrelated ones.
- **Why 2+ shows rather than the 5-year reunion rule:** under the 5-year rule Rodgers' list would be Hart, Logan, Sondheim and Charnin only; Hammerstein (9 shows, one continuous partnership) would be missing.
- **Data note:** 1,666 of the 1,997 people with credits never worked with anyone on 2 shows, so for most people the dropdown is empty (the panel says so). The largest list is 13 (Sondheim). The first-person search lists only the 1,997 people with credits.

## 2026-11-13: Cohort mode on stand-in communities (Ruby, views track)

- **What:** the Cohort mode. Pick a cohort year; everyone on a show that opened then is a dot clustered at its theatre. Playing the timeline moves each dot to the theatre of the person's latest show (hollow when idle that year, faded after 10 idle years or after death; unknown theatres sit in a corner area). The panel lists every later show with 2+ cohort members as a **reunion** (starting teammates back together after 5+ years apart, the Career-mode rule), **still together**, or a **new pairing**; a gold halo marks reunion people in that year. Colour by starting show or by community. Clicking a dot opens the person's career.
- **Why 5+ years here too:** counting any later show with starting teammates made 22 of the 1943 cohort's 25 later shows "reunions" (Rodgers & Hammerstein's whole run). With the rule: Weill & Kazan on *Love Life* (1948), Lerner & Loewe on *My Fair Lady* (1956, 5 years after *Paint Your Wagon*) and *Gigi* (1973), Dorothy & Herbert Fields on *Redhead* (1959).
- **Stand-in communities:** `viz/js/communities.js` computes them in the browser, per step 08 window, by weighted label propagation (edge weight = shows shared; ties keep the current label so one shared person doesn't chain teams together). Same row format as step 11 (mode, cutoff, community_id, person_id, strength). When step 11's rows are exported as `db.communityRows`, the module uses them and the view is unchanged. Like BigCLAM, the stand-in separates Rodgers (Hart-era circle) from Hammerstein (*Oklahoma!*/*Carmen Jones* people) in 1935–1944.
- **Colours:** seven categorical slots (blue, orange, aqua, violet, magenta, green, red) plus grey for the rest, validated with the dataviz script on the map land colour in light and dark, in that order. Yellow was left out (too close to the reunion gold). A year has a median of 8 shows (max 17), so the 7 largest teams get colours.
- **Not built yet:** the community timeline panel (needs step 12's links between windows); H1 "above chance" glow (Trang's `h1.json` / `db.glows()` are on `bigclam-h3`, not merged into this branch yet).
- **Data problem found (for the team):** `outputs/tables/suspect_strict_credits.csv` lists 35 strict credits on 31 shows where the person was under 16 or not yet born. Mostly revival or rewrite credits marked original (Aaron Sorkin on *Camelot* 1960, Thomas Kail on *Sweeney Todd* 1979, John Weidman on *Anything Goes* 1934); *Operation Mincemeat* dated 1943 (its subject's year, not its opening); and a few wrong people or placeholder birth years (b. 2000). These also enter steps 08, 10 and 11. Not fixed yet.

## 2026-11-13: Web views published on GitHub Pages (Ruby)

- **Live site:** https://rubyngo1610.github.io/broadway-network-reunion/ (Shows, Career and Cohort modes; Birthplaces and Compare are placeholders).
- **How:** `main` was fast-forwarded to `single-map` (the six commits from "one map for every view" to "Cohort mode on stand-in communities") and pushed. The publish workflow (`.github/workflows/pages.yml`) ran on that push and succeeded; the deployed page was checked in headless Chrome (Cohort 1943 loads and plays, no console errors).
- **Why the Nov 10 run failed:** `actions/configure-pages` stopped with "Get Pages site failed": the repository's Pages source was not yet set to GitHub Actions. It is set now (Settings → Pages → Source: GitHub Actions). Every push to `main` that changes `viz/` now republishes the site in about a minute, so anything merged to `main` is public.
- **Not on the site yet:** Trang's `bigclam-h3` branch (H1 null model, BigCLAM, H3 test, `viz/data/h1.json`, `db.glows()`). It merges into `main` with one conflict, in `WORKLOG.md` (both branches added entries in the same place).

**For the Nov 13 team meeting:**

1. **Communities for the views:** who exports step 11's `communities.parquet` to `viz/data` (step 13), and whether step 12 (tracking communities across windows, `community_links.parquet`) is being built. The Cohort mode uses stand-in communities until then; `viz/js/communities.js` switches to the real rows without view changes. The community timeline panel waits on step 12.
2. **Glow rule for reunions (H1):** with `h1.json`, p < 0.05 makes 342 of 416 strict reunions glow (82%), which singles little out; p < 0.01 gives 237 (57%), p < 0.05 with 2+ reunited pairs 273 (66%), p < 0.05 with a team of 4 or fewer 204 (49%). Ruby's suggestion: p < 0.01.
3. **Suspect credits:** `outputs/tables/suspect_strict_credits.csv` (35 strict credits on 31 shows where the person was under 16 or not yet born). They also feed steps 08, 10, 11 and 15. Decide who fixes them (year and team overrides in `src/filters.py`, or a rule in step 05) and rerun 05 → 06 → 08 → 09 → 13 and Trang's steps afterwards.
4. **Merging `bigclam-h3`** into `main`, which also publishes it.

## Open items (as of 2026-11-09)

- **Original-production flag:** in the spotchecks, about 8 of 50 credits had an "unknown" flag the article answers. Surname-only names remain ("Kidd", "Robbins", "Hamlin").
- **Human review** of the AI-checked answers before quoting them:
  - the network-scope spotcheck (2%, `[AI]` notes)
  - the venue accuracy above
- **Optional venue review:** a quick pass over `show_venues_review.csv` (sort by `score`; the lowest scores are least certain) to add `VENUE_OVERRIDES` before the demo.

## Next steps (plan for Nov 9–22)

Milestones from the mid-term update: Nov 3–15 BigCLAM per window, community tracking and H1 against the null model; Nov 9–22 the cohort view (animated) and its small-multiples baseline, the trajectory view and the map. As of Nov 9 none of the method steps exist yet. Step 09 is now venues, so the method steps are numbered 10–12.

**How the views depend on each other:**

| View | Needs | Can start now? |
|---|---|---|
| Trajectory view (one person's career) | `network/person_show.parquet` + `shows.parquet` | ✅ Yes |
| Birthplace map | `people.parquet` (birthplace lat/lon: 84% of people with a Wikidata ID, 41% of all people) | ✅ Yes |
| **NYC show map** (new, for the demo) | `venues/show_venues.parquet` + `theatres.parquet` + `person_show.parquet` | ✅ Yes, data ready as of today |
| Cohort view (animated) + small multiples | communities per window (step 11) + links between windows (step 12) | ⚠️ Build the frame on stand-in data; plug in BigCLAM when ready |

**Methods track:**

1. **Step 10: H1 null model.**
   - Needs only `person_show.parquet`, so it can start now and run in parallel with BigCLAM.
   - Within each 10-year window and role, reassign people across role slots of shows. This keeps career length, role, team size and show timing, and breaks who works with whom.
   - Run 1,000 shuffles and compare the observed reunion rate with them, in both strict and loose modes.
2. **Step 11: BigCLAM per window.**
   - One person–person graph per cutoff from `edges_by_window.parquet` (about 150–400 people and 300–1,800 edges each, so it's cheap).
   - A small NumPy implementation instead of `karateclub` or `cdlib`, which pin old dependencies.
   - Choose K per window by held-out edge likelihood. Save the F matrices and memberships per (mode, cutoff).
   - **Sanity check first on two windows (1950, 1980):** do the communities span several shows, or is each one just a single show? Do they match the case studies (Rodgers with Hart, then Hammerstein; Lerner & Loewe)? A "one community per show" result would add nothing beyond the "number of past shows together" baseline H3 has to beat.
3. **Step 12: community tracking.**
   - The windows overlap by 5 years. Match communities between neighbouring cutoffs by Jaccard overlap of members, and label each step continue, split, merge, birth or death.
   - This is the data the cohort view uses.
4. H3 (prediction with time splits) stays in Nov 16–Dec 1. It reuses step 11's F matrices: the score for a pair is F_u · F_v, learned only from [T−10, T).

**Views track:**

1. **Agree on the data format today**, so both tracks build against the same columns:
   - `communities.parquet`: mode, cutoff, community_id, person_id, strength
   - `community_links.parquet`: from_cutoff, from_id, to_cutoff, to_id, jaccard, event
2. **Stand-in communities:** connected components or Louvain per window, written in that format. The animation, timeline slider and small-multiples grid get built on these, then the real step 11 file is swapped in.
3. **One data layer for both cohort views.** The animated view and the small multiples share one data loader and one encoding (colour = community, position = window), and differ only in layout, so the user-study comparison is fair.
4. **NYC show map:**
   - Theatre District at street level. Each show is a point at its opening theatre, and a time slider moves through the years.
   - Selecting a person or a community highlights the theatres their shows opened in, which shows where a team moved over time.
   - Demolished theatres (Ziegfeld, Center, Hippodrome, …) appear only while they stood (`opened_year`, `demolished_year`).
   - Link it to the trajectory view: clicking a person on the map opens their career, and the reverse.

**Suggested split:**

| | Nov 9–15 | Nov 15–22 |
|---|---|---|
| **Person A (methods)** | Step 10 (null model, H1); step 11 (BigCLAM) with the two-window check | Step 12 (tracking); deliver the real `communities.parquet` by about Nov 17 |
| **Person B (views)** | Trajectory view; birthplace map; NYC show map | Cohort view + small multiples on stand-in data (Nov 14–19); swap in the real BigCLAM output by Nov 22 |

**Extensions (after Nov 22):** step 04b cast; node2vec and aligning embeddings across windows; the Leiden comparison; later theatres in a run (transfers) on the show map.
