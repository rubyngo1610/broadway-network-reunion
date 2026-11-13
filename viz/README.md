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

The site appears at `https://<owner>.github.io/<repo>/`. Free GitHub Pages needs a public repository.

## Layout

| Path | What it is |
|---|---|
| `index.html` | Page shell: header, view navigation, one `<main>` the views render into, a shared tooltip |
| `css/style.css` | Design tokens (colours, type) as CSS custom properties for light and dark mode, then layout. Restyle the project by changing the tokens, not the views |
| `js/main.js` | Loads the data once, builds the stage, then switches mode when the URL hash changes (`#shows?year=1927`, `#cohort`, …). Old page names (`#showmap`, `#trajectory`, `#multiples`) still work |
| `js/stage.js` | **One map for every view.** Builds the mode bar, the shared timeline (year slider and play), the map and the side panel once. Switching modes animates the map instead of loading a new page; zoom and year carry over. The comment at the top defines the mode interface (`enter`, `setYear`, `exit`, `tip`, `onParams`); a mode can narrow the timeline with `ctx.setRange` |
| `js/modes/*.js` | One file per mode. `shows.js` is the NYC show map, `career.js` the trajectory; `comingSoon.js` stands in for modes not built yet |
| `js/data.js` | `loadData()` returns a `db` object: the raw tables, lookup maps (`showById`, `personById`, `theatreById`, `creditsByPerson`, `creditsByShow`, `showsByTheatre`) and helpers (`theatreOf`, `standing`, `career`) |
| `js/manhattanMap.js` | **The shared zoomable map.** `createManhattanMap(container, db)` draws the Manhattan basemap (shoreline, parks, streets, squares), rotated to grid north. It handles zoom and pan (drag, scroll, or the + / − / ⌂ buttons) and returns `xy(lat, lon)`, `layer(name)`, `onZoom(fn)` and `zoomTo(points)`. Basemap lines keep their screen width; views re-place their dots on every zoom, so dots keep their size and spread apart as you zoom in. `drawTheatres(map, db)` adds every theatre |
| `js/grid.js` | `toGrid(lat, lon)` converts to Manhattan grid units (street number, avenue number). Used by the data-check plot; could also be used for the small multiples |
| `js/tooltip.js` | One shared tooltip |
| `js/views/dataCheck.js` | The data check (`#data`, linked from the footer), shown in place of the stage |
| `data/*.json` | Written by `scripts/13_export_viz_data.py`. Don't edit by hand |

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

**`strict` and `loose`** match the network modes of step 08. `strict` keeps credits confirmed as part of the original production; `loose` also keeps unknowns. Both drop posthumous credits. Views default to `strict`.

## Views (modes of one map)

The page is one map with a mode bar above it. Each mode restyles the same map; nothing reloads.

| Hash | Mode | Status |
|---|---|---|
| `#shows` (default) | Where each year's new musicals opened: theatres with an opening are filled, and the openings are listed. `#shows?year=1927` opens a year | working |
| `#career` | One person's career as a transit line between theatres, in opening order; the map zooms to fit it. Stations grow with the number of shows; gold stations are reunions (back with a collaborator after 5+ years apart). The panel has a name search and the show list; collaborator names open their career. The timeline covers just this career: the line is drawn up to the chosen year (the rest dashed), the latest show's theatre is filled, and Play steps through the career. `#career?p=Q269094&year=1943` is Richard Rodgers in 1943 (no year = the whole career) | working |
| `#cohort` | People as dots in their show's (or BigCLAM community's) colour, moving between theatres as the timeline plays | planned |
| `#birthplaces` | Birthplaces; the map zooms out from Manhattan to the US and the world | planned (needs a US/world basemap) |
| `#compare` | Small multiples: the map splits into a grid of five-year panels | planned |
| `#data` | Data check: counts, coverage notes, theatres on the street grid. Linked from the footer, not the mode bar | working |

## Style

Playbill / marquee for the page (cream paper, Playfair Display headings, Source Sans 3 text, a gold accent), a vintage atlas look for the map (tan blocks, sage parks, faded water, streets as paper showing through), and transit-diagram lines for careers. Colours are CSS custom properties in `css/style.css`, with a dark "marquee at night" mode. Gold marks reunions and highlights and is never used for body text (`--accent-ink` is the text-safe gold).
