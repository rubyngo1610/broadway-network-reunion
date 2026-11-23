# Web views (`viz/`)

A static web page built with D3 v7: no build step and no npm install. D3 is loaded from the jsDelivr CDN at a pinned version (`d3@7.9.0`).

## Run it locally

The page loads JSON with `fetch`, so it has to be served over HTTP. Opening `index.html` straight from disk doesn't work.

```bash
cd viz
python3 -m http.server 8000
# open http://localhost:8000
```

After any rerun of pipeline steps 05, 08 or 09, refresh the data:

```bash
export BROADWAY_DATA_DIR=~/broadway-data
python scripts/13_export_viz_data.py      # writes viz/data/*.json
```

The basemap only needs rebuilding if you change its area or style rules (`python scripts/14_build_basemap.py`). Its sources are downloaded once into `data/raw/basemap/`.

## Publish (GitHub Pages)

`.github/workflows/pages.yml` publishes this folder on every push to `main` that touches `viz/`. It can also be run by hand from the Actions tab.

One-time setup on GitHub:

1. Open **Settings → Pages** and set **Source** to **GitHub Actions**.
2. Merge to `main`, or run the workflow from the **Actions** tab.

Live at **https://rubyngo1610.github.io/broadway-network-reunion/** (Pages source set to GitHub Actions on 2026-11-13). Every push to `main` that changes `viz/` republishes it, so whatever is merged to `main` is public. Free GitHub Pages needs a public repository.


**Before pushing a change to `js/` or `css/`, run `python3 viz/bump_version.py`.** It stamps a new version on every script and the stylesheet (an import map in `index.html`), so browsers never mix an old cached file with new ones. Without it, a browser can show new tab names with old layout code.

## Layout

| Path | What it is |
|---|---|
| `index.html` | Page shell: header, view navigation, one `<main>` the views render into, a shared tooltip |
| `css/style.css` | Design tokens (colours, type) as CSS custom properties for light and dark mode, then layout. Restyle the project by changing the tokens, not the views |
| `js/main.js` | Loads the data once, builds the stage, then switches mode when the URL hash changes (`#shows?year=1927`, `#cohort`, …). Old page names (`#showmap`, `#trajectory`) still work. Tabs: Shows, Cohort & Career, Chance, Predict; each tab link returns to that view as it was last left |
| `js/stage.js` | **One map for every view.** Builds the mode bar, the shared timeline (year slider and play), the map and the side panel once. Switching modes animates the map instead of loading a new page; zoom and year carry over. The comment at the top defines the mode interface (`enter`, `setYear`, `exit`, `tip`, `onParams`); a mode can narrow the timeline with `ctx.setRange`. A mode with `split: true` gets two maps side by side (`ctx.split.left` / `.right`, each with its own map, panel and theatre dots; the timeline and URL stay shared) and a wider page |
| `js/communities.js` | `communitiesFor(db, mode, cutoff, method)` returns communities in step 11's format. Methods: `bigclam` and `weighted` (step 11, from `models.json`, strict mode only) and `stand-in` (label propagation computed in the browser; used for loose mode or when `models.json` is missing). `showTeamCheck` counts the communities that are just one show's team |
| `js/modes/*.js` | One file per mode. `shows.js` is the NYC show map, `career.js` the trajectory, `cohort.js` the cohort view, `cohortCareer.js` runs cohort and career side by side (the Cohort & Career tab), `chance.js` the H1 view, `predict.js` the H3 view |
| `js/data.js` | `loadData()` returns a `db` object: the raw tables, lookup maps (`showById`, `personById`, `theatreById`, `creditsByPerson`, `creditsByShow`, `showsByTheatre`) and helpers (`theatreOf`, `standing`, `career`) |
| `js/manhattanMap.js` | **The shared zoomable map.** `createManhattanMap(container, db)` draws the Manhattan basemap (shoreline, parks, streets, squares), rotated to grid north. It handles zoom and pan (drag, scroll, or the + / − / ⌂ buttons) and returns `xy(lat, lon)`, `layer(name)`, `onZoom(fn)` and `zoomTo(points)`. Basemap lines keep their screen width; views re-place their dots on every zoom, so dots keep their size and spread apart as you zoom in. `drawTheatres(map, db)` adds every theatre |
| `js/grid.js` | `toGrid(lat, lon)` converts to Manhattan grid units (street number, avenue number). Used by the data-check plot; could also be used for the small multiples |
| `js/tooltip.js` | One shared tooltip |
| `js/views/dataCheck.js` | The data check (`#data`, linked from the footer), shown in place of the stage |
| `data/*.json` | Written by `scripts/13_export_viz_data.py` (`h1.json` by step 10, `models.json` by step 17). Don't edit by hand |

## Data files

| File | One entry per | Fields |
|---|---|---|
| `meta.json` | — | export date, counts, network settings (roles, window, horizon, cutoffs), coverage notes |
| `theatres.json` | theatre (86) | `id` (Wikidata QID), `name` (current name), `lat`, `lon`, `opened`, `demolished`, `first_show`, `last_show`, `n_shows` |
| `shows.json` | core show (1,234) | `id`, `title`, `year` (opening), `venue` (theatre id or null), `venue_basis`, `wiki` |
| `people.json` | person in the network (3,189) | `id`, `name`, `born`, `died`, `birthplace`, `lat`, `lon` (birthplace), `wiki` |
| `credits.json` | person–show pair (6,335) | `person`, `show`, `year`, `roles` (list), `original` (true/false/null), `strict`, `loose`, `posthumous` |
| `basemap.json` | — | Manhattan from the Battery to about 100th St: `land` (borough outlines), `parks`, `streets.major` / `streets.minor` (lines of [lon, lat]), `labels` (squares, landmarks, rivers), `attribution`. Written by `scripts/14_build_basemap.py` (OpenStreetMap + NYC Open Data), 530 KB |
| `reunions.json` | pair per cutoff, by mode | compact rows `[cutoff, person_a, person_b, shows_together, reunion_shows, first_reunion_year]`; `data.js` expands them to objects |
| `h1.json` | by mode | Written by `scripts/10_null_model.py`, not step 13. `shows`: training-window shows whose team had a reunion, `[cutoff, show, team_size, reunited_pairs, null_mean, p_value]`. `windows`: observed vs null reunion rate per cutoff, `[cutoff, pairs, reunited, observed_rate, null_mean, null_lo, null_hi]`, for the reunions-over-time chart. Optional: `db.h1` is null if the file is missing. `db.glows(mode, reunionRow)` says whether a reunion should glow (the pair shared a show whose team reunited above chance, p < 0.05). In strict mode 342 of 416 reunions glow, so the filter mainly drops reunions from large teams. `draws`: every shuffle's number of reunited pairs per cutoff (1,000 each), for the Shuffle careers button; `scripts/10_null_model.py --viz-only` rewrites the file from saved results without reshuffling |
| `models.json` | strict mode | Written by `scripts/17_export_model_viz.py` from steps 11 and 15 (nothing refitted). `communities.bigclam` / `communities.weighted`: `[cutoff, community_id, person_id, strength]`, members only. `pairs.rows`: every candidate pair per cutoff (shared a show in [T−10, T)), `[cutoff, person_a, person_b, shows_together, activity, common_neighbors, bigclam, weighted, reunion_shows]`; `weighted` is F_a·F_b from the weighted affiliations. `auc`: AUC per window and pooled for each score. 755 KB. Optional: `db.models` is null if missing |

**`strict` and `loose`** match the network modes of step 08. `strict` keeps credits confirmed as part of the original production; `loose` also keeps unknowns. Both drop posthumous credits. Views default to `strict`.

## Views (modes of one map)

The page is one map with a mode bar above it. Each mode restyles the same map; nothing reloads.

| Hash | Mode | Status |
|---|---|---|
| `#shows` (default) | Where each year's new musicals opened: theatres with an opening are filled, and the openings are listed. `#shows?year=1927` opens a year | working |
| `#cohort` | **Cohort & Career**, two maps side by side: cohort panel, cohort map, career map, career panel (on narrower screens each panel sits under its map). Left: pick a cohort year; everyone on a show that opened then is a dot that moves to the theatre of their latest show as the shared timeline plays, coloured by starting show; gold halo = starting teammates back together after 5+ years. Click a dot: their career is drawn on the right map up to the timeline year, and on the left that person is ringed and everyone they never worked with again is dimmed (the panel lists their later shows with cohort members). Right: everything Career mode does: compare with up to 3 people they did 2+ shows with (dropdown), × to remove, gold reunion marks between the selected people, a key box on the map, search anyone. `#cohort?from=1943&p=Q269094,Q319693&year=1956`; old `#career?p=` links open here | working |
| `#chance` | **H1.** Observed reunion rate per 10-year window against step 10's shuffled careers (line and 95% band), the pooled ratio, and for the window on the timeline every show on the map: gold where its team reunited more than chance (p < 0.05), gold ring where some reunited within chance, grey otherwise; the panel lists the reunited teams by p-value. **Shuffle careers** (`js/shuffle.js`, the same rule as step 10, run live in the browser): each press deals the window into random teams (same people, roles, team sizes and years) and the map shows that made-up Broadway (ring = a team with a reunion); a tally counts reunions per shuffle against the real number, "Shuffle 1,000×" shows step 10's stored shuffles, and the chart marks the window's slice of the grey band. `#chance?year=1945` | working |
| `#predict` | **H3.** Pick a score (shows together, both still working, common collaborators, BigCLAM, weighted BigCLAM). For the window on the timeline: AUC of every score (bar) with the pooled AUC (tick) and chance at 0.5; reunion rate by score level over all windows; "it's the pair, not the team": the score's average and the reunion rate by team size, side by side (plain BigCLAM rises with team size while reunions fall); "partnerships predict reunions": reunion rate by team size × shows together (heatmap); the top 20 pairs, hit or miss, and the reunited pairs the score ranked lowest. On the map, each top pair sits at the theatre of their last show together in the window, with a gold arc to where they reunited. Clicking a pair opens their careers. **Map: communities** instead shows what BigCLAM learned in the window: each person at the theatre of their last show in it, coloured by their strongest community (plain or weighted BigCLAM, switch in the panel), with the check of how many communities are just one show's team and a legend of the largest communities (hover to highlight). Picking the BigCLAM or weighted score switches the communities to match. `#predict?score=bigclam&map=communities&method=weighted&year=1945` | working |
| `#data` | Data check: counts, coverage notes, theatres on the street grid. Linked from the footer, not the mode bar | working |

## Style

Playbill / marquee for the page (cream paper, Playfair Display headings, Source Sans 3 text, a gold accent), a vintage atlas look for the map (tan blocks, sage parks, faded water, streets as paper showing through), and transit-diagram lines for careers. Colours are CSS custom properties in `css/style.css`, with a dark "marquee at night" mode. The four Career-mode colours (`--person-1` … `--person-4`) were checked with a colour-blindness validator in both modes; each also has a dash pattern, so colour is never the only cue. The Cohort dots use seven categorical colours (`--cat-1` … `--cat-7`, validated in this fixed order in both modes) plus grey for "other". Gold marks reunions and highlights and is never used for body text (`--accent-ink` is the text-safe gold).
