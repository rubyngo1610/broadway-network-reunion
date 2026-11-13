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
